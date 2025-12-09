from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect, Http404
from .models import ProcessingInput
from .forms import CreateNewList
import mimetypes
import yaml
from .forms import ParquetUploadForm, MrnaParquetUploadForm, BulkParquetUploadForm, BulkMrnaParquetUploadForm, PsiteOffsetUploadForm
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
import json
import re
import threading
# from sklearn.decomposition import PCA  # Temporarily disabled - scipy/sklearn too heavy for free tier
import glob
import numpy as np
# import matplotlib.pyplot as plt  # Temporarily disabled - too heavy for free tier
# import seaborn as sns  # Temporarily disabled - too heavy for free tier
try:
    from ribopy import Ribo
except ImportError:
    Ribo = None
import pickle
from django.core.cache import cache
from django.http import JsonResponse
import plotly.express as px
import pandas as pd
import os
import hashlib
import time
from django.shortcuts import render, redirect
import pyarrow.parquet as pq
from .models import SelectedGene, UploadedMrnaParquet, UploadedParquet
import shutil
from django.core.files.storage import default_storage



def reformatFilepaths(file_content):
    """
    Reformats the user-provided file content into YAML-compatible structure.
    Returns only the fastq section content for insertion into the template.
    Supports both space-separated and CSV formats.
    """
    fastq_data = {}
    lines = file_content.strip().splitlines()

    # Skip header line if it looks like CSV headers
    start_index = 0
    if lines and (',' in lines[0]) and ('sample' in lines[0].lower() or 'experiment' in lines[0].lower()):
        start_index = 1  # Skip header line

    for line in lines[start_index:]:
        line = line.strip()
        if not line:
            continue

        # Try CSV format first (comma-separated)
        if ',' in line:
            try:
                parts = [part.strip() for part in line.split(',')]
                if len(parts) >= 2:
                    experiment_name, filepath = parts[0], parts[1]
                else:
                    raise ValueError(f"CSV line '{line}' must have at least 2 columns.")
            except ValueError as e:
                raise ValueError(f"Line '{line}' is not formatted correctly. Expected 'experiment_name,/path/to/file' or 'experiment_name /path/to/file'.")
        else:
            # Try space-separated format
            try:
                experiment_name, filepath = line.split(' ', 1)
            except ValueError:
                raise ValueError(f"Line '{line}' is not formatted correctly. Each line must have either:\n  - Space-separated: 'experiment_name /path/to/file'\n  - Comma-separated: 'experiment_name,/path/to/file'\nExample: 'sample1_ribo /data/sample1.fastq.gz'")

        if experiment_name not in fastq_data:
            fastq_data[experiment_name] = []
        fastq_data[experiment_name].append(filepath)

    # Return only the fastq content with proper indentation for YAML insertion
    if not fastq_data:
        return ""

    yaml_lines = []
    for experiment_name, filepaths in fastq_data.items():
        yaml_lines.append(f"       {experiment_name}:")
        for filepath in filepaths:
            yaml_lines.append(f"       - {filepath}")

    return "\n".join(yaml_lines)


def preProcess(response):
    if response.method == "POST":
        form = CreateNewList(response.POST, response.FILES)
        if form.is_valid():
            experimentName = form.cleaned_data["experimentName"]
            adapter = form.cleaned_data["adapter"]
            sampleFile = response.FILES["sampleFile"]
            humanGenome = form.cleaned_data["humanGenome"]
            mouseGenome = form.cleaned_data["mouseGenome"]
            useBarcode = form.cleaned_data["useBarcode"]
            includeRnaSeq = form.cleaned_data["includeRnaSeq"]
            mrnaSeqFile = response.FILES.get("mrnaSeqFile")

            ProcessingInput.objects.create(
                experimentName=experimentName,
                adapter=adapter,
                sampleFile=sampleFile,
                humanGenome=humanGenome,
                mouseGenome=mouseGenome,
                useBarcode=useBarcode
            )

            # Read the contents of the uploaded ribosome profiling sample file
            if sampleFile:
                # Reset file pointer to beginning
                sampleFile.seek(0)
                sample_file_content = sampleFile.read().decode('utf-8')
            else:
                sample_file_content = ""

            # Process the ribosome profiling sample file content
            ribo_sample_data = []
            for line in sample_file_content.splitlines():
                if line.strip():  # Ignore empty lines
                    parts = line.split(' ', 1)  # Split at the first space
                    if len(parts) == 2:
                        ribo_sample_data.append((parts[0], parts[1]))  # (name, filepath)

            # Process mRNA-seq file if provided
            mrna_sample_data = []
            if includeRnaSeq and mrnaSeqFile:
                # Reset file pointer to beginning
                mrnaSeqFile.seek(0)
                mrna_file_content = mrnaSeqFile.read().decode('utf-8')
                for line in mrna_file_content.splitlines():
                    if line.strip():  # Ignore empty lines
                        parts = line.split(' ', 1)  # Split at the first space
                        if len(parts) == 2:
                            mrna_sample_data.append((parts[0], parts[1]))  # (name, filepath)

            # Determine the genome based on the user selectionb
            if mouseGenome:
                genome = "curl -L --output mus-musculus.tar.gz https://github.com/RiboBase/reference_mus-musculus/archive/refs/tags/v1.0.tar.gz"
                filter = "reference_mus-musculus-1.0/filter/mouse/mouse_rtRNA*"
                transcriptome = "reference_mus-musculus-1.0/transcriptome/mouse/appris_mouse_v2_selected*"
                regions = "appris_mouse_v2_actual_regions.bed"
                transcriptLengths = "appris_mouse_v2_transcript_lengths.tsv"
            else:
                genome = "curl -L --output homo-sapiens.tar.gz https://github.com/RiboBase/reference_homo-sapiens/archive/refs/tags/v1.0.tar.gz"
                filter = "reference_homo-sapiens-1.0/filter/human/human_rtRNA*"
                transcriptome = "reference_homo-sapiens-1.0/transcriptome/human/appris_human_v2_selected*"
                regions = "appris_human_v2_actual_regions.bed"
                transcriptLengths = "appris_human_v2_transcript_lengths.tsv"

            # Process ribosome profiling file paths (use already-read content)
            try:
                ribo_file_paths = reformatFilepaths(sample_file_content)
            except ValueError as e:
                form.add_error('sampleFile', f"Invalid sample file format: {str(e)}")
                return render(response, 'riboApp/preprocess.html', {'form': form})

            # Process mRNA-seq file paths if provided (use already-read content)
            if includeRnaSeq and mrnaSeqFile:
                # mrna_file_content was already read above
                try:
                    mrna_file_paths = reformatFilepaths(mrna_file_content)
                except ValueError as e:
                    form.add_error('mrnaSeqFile', f"Invalid mRNA-seq file format: {str(e)}")
                    return render(response, 'riboApp/preprocess.html', {'form': form})
            else:
                mrna_file_paths = ""

            # Set read length parameters for ribosome profiling (always short reads)
            ribo_read_length_min = 28   # Ribosome profiling reads are typically 28-32 nt
            ribo_read_length_max = 32   # Standard ribosome profiling range

            myScriptPath = os.path.join(os.path.dirname(__file__), 'scripts', 'outputScript.sh')
            if not os.path.exists(myScriptPath):
                raise Http404(f"Script file not found at {myScriptPath}")
            with open(myScriptPath, 'r') as template_file:
                scriptContent = template_file.read()

            # Generate ribosome profiling clip arguments (always short reads)
            if useBarcode:
                ribo_clip_arguments = f'-u 1 -a {adapter} --overlap=4 --trimmed-only --maximum-length=40 --minimum-length=15 --quality-cutoff=28 --discard-untrimmed'
                ribo_barcode_comment = "# Ribosome profiling with barcode demultiplexing - optimized for short reads"
            else:
                ribo_clip_arguments = f'-u 1 -a {adapter} --overlap=4 --trimmed-only --maximum-length=40 --minimum-length=15 --quality-cutoff=28'
                ribo_barcode_comment = "# Ribosome profiling adapter trimming - optimized for short reads (~28-32nt)"

            # Generate mRNA-seq clip arguments if mRNA data is included (always long reads)
            if includeRnaSeq:
                if useBarcode:
                    mrna_clip_arguments = f'-u 1 -a {adapter} --overlap=4 --minimum-length=50 --maximum-length=200 --quality-cutoff=20 --discard-untrimmed'
                    mrna_barcode_comment = "# mRNA-seq with barcode demultiplexing - optimized for longer reads"
                else:
                    mrna_clip_arguments = f'-u 1 -a {adapter} --overlap=4 --minimum-length=50 --maximum-length=200 --quality-cutoff=20'
                    mrna_barcode_comment = "# mRNA-seq adapter trimming - optimized for longer reads (~150nt)"
            else:
                mrna_clip_arguments = ""
                mrna_barcode_comment = ""

            scriptContent = scriptContent.replace("{filter}", filter)
            scriptContent = scriptContent.replace("{genome}", genome)
            scriptContent = scriptContent.replace("{transcriptome}", transcriptome)
            scriptContent = scriptContent.replace("{regions}", regions)
            scriptContent = scriptContent.replace("{transcriptLengths}", transcriptLengths)
            scriptContent = scriptContent.replace("{experimentName}", experimentName)
            scriptContent = scriptContent.replace("{riboFilePaths}", ribo_file_paths)
            scriptContent = scriptContent.replace("{mrnaFilePaths}", mrna_file_paths)
            scriptContent = scriptContent.replace("{riboClipArguments}", ribo_clip_arguments)
            scriptContent = scriptContent.replace("{mrnaClipArguments}", mrna_clip_arguments)
            scriptContent = scriptContent.replace("{riboBarcodeComment}", ribo_barcode_comment)
            scriptContent = scriptContent.replace("{mrnaBarcodeComment}", mrna_barcode_comment)
            scriptContent = scriptContent.replace("{includeRnaSeq}", "true" if includeRnaSeq else "false")
            scriptContent = scriptContent.replace("{readLengthMin}", str(ribo_read_length_min))
            scriptContent = scriptContent.replace("{readLengthMax}", str(ribo_read_length_max))

            output_dir = os.path.join('media', 'generated_scripts')
            os.makedirs(output_dir, exist_ok=True)

            clean_experiment_name = experimentName.replace(" ", "")
            script_file_path = os.path.join(output_dir, f"{clean_experiment_name}Script.sh")

            with open(script_file_path, 'w') as output_file:
                output_file.write(scriptContent)

            script_file_url = f"generated_scripts/{clean_experiment_name}Script.sh"

            # Create summary of processing parameters for user feedback
            processing_summary = {
                "include_rnaseq": includeRnaSeq,
                "ribo_read_length_range": f"{ribo_read_length_min}-{ribo_read_length_max} nucleotides",
                "ribo_clip_arguments": ribo_clip_arguments,
                "mrna_clip_arguments": mrna_clip_arguments if includeRnaSeq else "N/A",
                "barcode_enabled": useBarcode,
                "genome": "Mouse (GRCm39)" if mouseGenome else "Human (GRCh38)",
                "ribo_samples": len(ribo_sample_data),
                "mrna_samples": len(mrna_sample_data) if includeRnaSeq else 0
            }

            return render(response, "riboApp/preprocess.html", {
                "form": form,
                "script_file": script_file_url,
                "processing_summary": processing_summary
            })
    else:
        form = CreateNewList()

    # to delete at specified index
    # ProcessingInput.objects.filter(id="4").delete()


    all_inputs = ProcessingInput.objects.all()
    return render(response, "riboApp/preprocess.html", {"form": form, "all_inputs": all_inputs})
# def preProcess(response):
#     if response.method == "POST":
#         form = CreateNewList(response.POST, response.FILES)
#         if form.is_valid():
#             experimentName = form.cleaned_data["experimentName"]
#             adapter = form.cleaned_data["adapter"]
#             sampleFile = form.cleaned_data["sampleFile"]
#             humanGenome = form.cleaned_data["humanGenome"]
#             mouseGenome = form.cleaned_data["mouseGenome"]
#
#             ProcessingInput.objects.create(
#                 experimentName=experimentName,
#                 adapter=adapter,
#                 sampleFile=sampleFile,
#                 humanGenome=humanGenome,
#                 mouseGenome=mouseGenome
#             )
#
#             return HttpResponseRedirect('/preprocess/')
#     else:
#         form = CreateNewList()
#
#     all_inputs = ProcessingInput.objects.all()
#
#     return render(response, "riboApp/preprocess.html", {"form": form, "all_inputs": all_inputs})

def download_file(response, file_name):
    file_path = os.path.join('media/uploads', file_name)

    if not os.path.exists(file_path):
        raise Http404("File not found")

    mime_type, _ = mimetypes.guess_type(file_path)
    with open(file_path, 'rb') as f:
        response = HttpResponse(f, content_type=mime_type or 'application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename={file_name}'
        return response

def home(response):
    return render(response, 'riboApp/home.html')

def analyze(response):
    return render(response, 'riboApp/analyze.html')

def locatePsites(response):
    return render(response, 'riboApp/psites.html')


def get_gene_reads(gene_name):
    """Get reads for a specific gene from all parquet files"""
    from .analysis.data_getters import get_available_parquet_files

    parquet_folder = "media/parquetFiles/"
    files = get_available_parquet_files()

    all_data = []

    for file in files:
        file_path = os.path.join(parquet_folder, file)

        # Load only relevant columns
        df = pq.read_table(file_path, columns=["gene_name", "read_count"]).to_pandas()

        # Filter for the requested gene
        filtered_df = df[df["gene_name"] == gene_name]
        if not filtered_df.empty:
            all_data.append(filtered_df)

    return pd.concat(all_data, ignore_index=True)
def _cache_file_in_background(file_path, file_type):
    """Background thread function to validate file without blocking upload"""
    try:
        import time
        time.sleep(2)  # Wait a bit to ensure file is fully written

        # Validate file (just check schema, don't load entire file into memory)
        try:
            pq_file = pq.ParquetFile(file_path)
            columns = set(pq_file.schema.names)
            required_columns = {"transcript_id", "gene_name", "start_position", "end_position",
                              "strand", "read_id", "read_length", "read_count", "region", "source_file"}
            missing_columns = required_columns - columns

            if missing_columns:
                print(f"❌ Invalid file {os.path.basename(file_path)}: missing columns {', '.join(missing_columns)}")
                # Delete invalid file
                if os.path.exists(file_path):
                    os.remove(file_path)
                return
        except Exception as e:
            print(f"❌ Invalid parquet file {os.path.basename(file_path)}: {str(e)}")
            # Delete invalid file
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        # File is valid - don't create cache here to avoid OOM
        # User can trigger preprocessing manually if needed
        print(f"✅ File validation completed for {os.path.basename(file_path)}")
    except Exception as e:
        print(f"❌ Error during file validation of {file_path}: {str(e)}")

# Upload and store all Parquet data
def upload_parquet(request):
    bulk_ribo_form = BulkParquetUploadForm()
    bulk_mrna_form = BulkMrnaParquetUploadForm()
    psite_offset_form = PsiteOffsetUploadForm()

    if request.method == "POST":
        # Check which form was submitted
        if 'bulk_ribo_submit' in request.POST:
            bulk_ribo_form = BulkParquetUploadForm(request.POST, request.FILES)
            if bulk_ribo_form.is_valid():
                files = request.FILES.getlist('files')
                successful_uploads = 0
                failed_uploads = []

                for file in files:
                    if file.name.endswith('.parquet'):
                        try:
                            print(f"📥 Starting upload of {file.name} (size: {file.size} bytes)")

                            # Create the parquet files directory if it doesn't exist
                            parquet_dir = "parquetFiles"
                            os.makedirs(f"media/{parquet_dir}", exist_ok=True)

                            # Write file in chunks (1MB at a time)
                            file_path = f"{parquet_dir}/{file.name}"
                            chunk_size = 1024 * 1024  # 1MB chunks

                            with default_storage.open(file_path, 'wb') as destination:
                                for chunk in file.chunks(chunk_size=chunk_size):
                                    destination.write(chunk)

                            print(f"✅ File streamed to {file_path}")

                            # Create database record
                            uploaded_file = UploadedParquet(file=file_path)
                            uploaded_file.save()
                            full_file_path = uploaded_file.file.path
                            print(f"✅ Database record created for {file.name}")

                            # Skip validation during upload - validate in background thread
                            # This prevents timeout when uploading multiple large files
                            cache_thread = threading.Thread(
                                target=_cache_file_in_background,
                                args=(full_file_path, "riboseq"),
                                daemon=True
                            )
                            cache_thread.start()
                            successful_uploads += 1
                            print(f"✅ Background thread started for {file.name}")

                        except Exception as e:
                            print(f"❌ Error uploading {file.name}: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            failed_uploads.append(f"{file.name}: {str(e)}")
                    else:
                        failed_uploads.append(f"{file.name}: not a .parquet file")

                if successful_uploads > 0:
                    # Clear global caches since new files were uploaded
                    clear_global_caches()
                    messages.success(request, f"Successfully uploaded {successful_uploads} riboseq files. Preprocessing will continue in the background.")
                if failed_uploads:
                    messages.error(request, f"Failed uploads: {'; '.join(failed_uploads)}")

                return redirect("upload_parquet")

        elif 'bulk_mrna_submit' in request.POST:
            bulk_mrna_form = BulkMrnaParquetUploadForm(request.POST, request.FILES)
            if bulk_mrna_form.is_valid():
                files = request.FILES.getlist('files')
                successful_uploads = 0
                failed_uploads = []

                for file in files:
                    if file.name.endswith('.parquet'):
                        try:
                            print(f"📥 Starting upload of {file.name} (size: {file.size} bytes)")

                            # Create the mRNA files directory if it doesn't exist
                            mrna_dir = "mrnaFiles"
                            os.makedirs(f"media/{mrna_dir}", exist_ok=True)

                            # Write file in chunks (1MB at a time)
                            file_path = f"{mrna_dir}/{file.name}"
                            chunk_size = 1024 * 1024  # 1MB chunks

                            with default_storage.open(file_path, 'wb') as destination:
                                for chunk in file.chunks(chunk_size=chunk_size):
                                    destination.write(chunk)

                            print(f"✅ File streamed to {file_path}")

                            # Create database record
                            uploaded_file = UploadedMrnaParquet(file=file_path)
                            uploaded_file.save()
                            full_file_path = uploaded_file.file.path
                            print(f"✅ Database record created for {file.name}")

                            # Skip validation during upload - validate in background thread
                            # This prevents timeout when uploading multiple large files
                            cache_thread = threading.Thread(
                                target=_cache_file_in_background,
                                args=(full_file_path, "mrna"),
                                daemon=True
                            )
                            cache_thread.start()
                            successful_uploads += 1
                            print(f"✅ Background thread started for {file.name}")

                        except Exception as e:
                            print(f"❌ Error uploading {file.name}: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            failed_uploads.append(f"{file.name}: {str(e)}")
                    else:
                        failed_uploads.append(f"{file.name}: not a .parquet file")

                if successful_uploads > 0:
                    # Clear global caches since new files were uploaded
                    clear_global_caches()
                    messages.success(request, f"Successfully uploaded {successful_uploads} mRNA files. Preprocessing will continue in the background.")
                if failed_uploads:
                    messages.error(request, f"Failed uploads: {'; '.join(failed_uploads)}")

                return redirect("upload_parquet")

        elif 'psite_offset_submit' in request.POST:
            psite_offset_form = PsiteOffsetUploadForm(request.POST, request.FILES)
            if psite_offset_form.is_valid():
                uploaded_file = request.FILES.get('offset_csv')
                if uploaded_file:
                    try:
                        # Read and validate CSV
                        df = pd.read_csv(uploaded_file)
                        required_columns = {"Experiment", "Read Length", "P-site Offset"}
                        if not required_columns.issubset(set(df.columns)):
                            messages.error(request, f"CSV must contain columns: {', '.join(required_columns)}")
                        else:
                            # Save the CSV file
                            df.to_csv(OFFSET_CSV, index=False)
                            # Clear P-site offset cache
                            clear_global_caches()
                            messages.success(request, "P-site offset CSV uploaded successfully!")
                    except Exception as e:
                        messages.error(request, f"Error processing CSV: {str(e)}")
                else:
                    messages.error(request, "No file uploaded!")
                return redirect("upload_parquet")

    return render(request, "riboApp/uploadParquet.html", {
        "bulk_ribo_form": bulk_ribo_form,
        "bulk_mrna_form": bulk_mrna_form,
        "psite_offset_form": psite_offset_form
    })

def clear_parquet_files(request):
    """Clear all uploaded parquet files and related data"""
    if request.method == "POST":
        try:
            # Clear database records
            deleted_parquet = UploadedParquet.objects.all().delete()
            deleted_mrna = UploadedMrnaParquet.objects.all().delete()
            print(f"Deleted {deleted_parquet[0]} parquet records and {deleted_mrna[0]} mRNA records")

            # Clear file directories
            parquet_dir = "media/parquetFiles/"
            mrna_dir = "media/mrnaFiles/"
            pickle_dir = "media/parquetPickles/"
            mrna_pickle_dir = "media/mrnaPickles/"

            cleared_dirs = []
            # Remove and recreate directories to clear all files
            for directory in [parquet_dir, mrna_dir, pickle_dir, mrna_pickle_dir]:
                if os.path.exists(directory):
                    print(f"Clearing directory: {directory}")
                    # Remove all files in directory instead of removing directory
                    for filename in os.listdir(directory):
                        file_path = os.path.join(directory, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                os.unlink(file_path)
                                print(f"Deleted file: {file_path}")
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                                print(f"Deleted directory: {file_path}")
                        except Exception as e:
                            print(f"Failed to delete {file_path}: {e}")
                    cleared_dirs.append(directory)
                else:
                    print(f"Directory does not exist: {directory}")

            # Clear cache
            cache.clear()
            clear_global_caches()
            print("Cache cleared")

            messages.success(request, f"All parquet files and related data have been cleared successfully! Cleared directories: {', '.join(cleared_dirs)}")

        except Exception as e:
            print(f"Error in clear_parquet_files: {str(e)}")
            messages.error(request, f"Error clearing files: {str(e)}")

    return redirect("upload_parquet")






@csrf_exempt  # Temporarily allow AJAX requests without CSRF issues
def save_selected_genes(request):
    """
    Saves or clears selected genes in the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            genes = data.get("genes", [])

            print(f"Received genes: {genes}")

            if not genes:
                # ✅ If the list is empty, clear all selected genes from the database
                SelectedGene.objects.all().delete()
                return JsonResponse({"message": "All genes removed from database."})

            # ✅ Otherwise, store only the provided genes
            SelectedGene.objects.all().delete()  # Ensure previous genes are removed
            for gene in genes:
                SelectedGene.objects.get_or_create(gene_name=gene)

            return JsonResponse({"message": f"Saved {len(genes)} genes to database."})

        except json.JSONDecodeError:
            print("JSON decoding error")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

    print("Invalid request method")
    return JsonResponse({"error": "Invalid request"}, status=400)







def get_gene_counts(file1, file2, cds_only=False, normalize_by_total=False):
    """Get gene counts for two files - OPTIMIZED with preprocessing cache

    Args:
        file1: First parquet file name
        file2: Second parquet file name
        cds_only: If True, only include CDS region reads
    """
    from .analysis.data_getters import get_region_gene_counts, get_cached_gene_counts

    if not cds_only:
        # For total counts, use the fastest available method
        # 🚀 Try to use the new preprocessing cache first (much faster)
        df1_counts = get_cached_gene_counts(file1, "riboseq")
        df2_counts = get_cached_gene_counts(file2, "riboseq")

        if not df1_counts.empty and not df2_counts.empty:
            # Use cached data - convert to dict format for compatibility
            gene_counts_1 = dict(zip(df1_counts['gene_name'], df1_counts['total_count']))
            gene_counts_2 = dict(zip(df2_counts['gene_name'], df2_counts['total_count']))
            print(f"🚀 Using cached gene counts for {file1} and {file2}")
        else:
            # Try region-based cache (might be faster than rebuilding pickle)
            print(f"⚠️ Preprocessing cache miss, trying region cache for {file1} and {file2}")
            try:
                ribo_counts1 = get_region_gene_counts(file1, "riboseq")
                ribo_counts2 = get_region_gene_counts(file2, "riboseq")

                # Sum all regions for total counts
                gene_counts_1 = {}
                gene_counts_2 = {}

                for gene, regions in ribo_counts1.items():
                    gene_counts_1[gene] = sum(regions.values())

                for gene, regions in ribo_counts2.items():
                    gene_counts_2[gene] = sum(regions.values())

                print(f"✅ Using region-based total counts for {file1} and {file2}")
            except Exception as e:
                print(f"⚠️ Region cache also failed, using pickle cache for {file1} and {file2}")
                gene_counts_1 = load_or_build_gene_counts_dict(file1)
                gene_counts_2 = load_or_build_gene_counts_dict(file2)
    else:
        # For CDS-only, try the new cache first, then use region cache (fast!)
        df1_counts = get_cached_gene_counts(file1, "riboseq", cds_only=True)
        df2_counts = get_cached_gene_counts(file2, "riboseq", cds_only=True)

        if not df1_counts.empty and not df2_counts.empty:
            # Use cached CDS data
            gene_counts_1 = dict(zip(df1_counts['gene_name'], df1_counts['total_count']))
            gene_counts_2 = dict(zip(df2_counts['gene_name'], df2_counts['total_count']))
            print(f"🚀 Using cached CDS-only gene counts for {file1} and {file2}")
        else:
            print(f"⚠️ No CDS preprocessing cache, using region cache for {file1} and {file2}")
            # Use region cache (this should be fast now!)
            ribo_counts1 = get_region_gene_counts(file1, "riboseq")
            ribo_counts2 = get_region_gene_counts(file2, "riboseq")

            # Extract CDS counts only
            gene_counts_1 = {}
            gene_counts_2 = {}

            for gene, regions in ribo_counts1.items():
                if "CDS" in regions:
                    gene_counts_1[gene] = regions["CDS"]

            for gene, regions in ribo_counts2.items():
                if "CDS" in regions:
                    gene_counts_2[gene] = regions["CDS"]

            print(f"✅ Using region-based CDS counts for {file1} and {file2}")

    common_genes = set(gene_counts_1.keys()) & set(gene_counts_2.keys())

    df_merged = pd.DataFrame({
        "gene_name": list(common_genes),
        "read_count_x": [gene_counts_1[g] for g in common_genes],
        "read_count_y": [gene_counts_2[g] for g in common_genes],
    })

    # Apply normalization if requested
    if normalize_by_total:
        total_reads_1 = get_total_read_count(file1, "riboseq")
        total_reads_2 = get_total_read_count(file2, "riboseq")

        if total_reads_1 > 0 and total_reads_2 > 0:
            # Normalize to RPM (Reads Per Million)
            df_merged["read_count_x"] = (df_merged["read_count_x"] / total_reads_1) * 1e6
            df_merged["read_count_y"] = (df_merged["read_count_y"] / total_reads_2) * 1e6
            print(f"📊 Applied RPM normalization: {file1} ({total_reads_1:,} total reads), {file2} ({total_reads_2:,} total reads)")
        else:
            print(f"⚠️ Could not normalize - zero total reads found")

    region_text = "CDS-only" if cds_only else "total"
    norm_text = " (RPM normalized)" if normalize_by_total else ""
    print(f"Processed {len(common_genes)} common genes for {file1} and {file2} ({region_text}{norm_text})")
    return df_merged

def geneCounts(request):
    from .analysis.data_getters import get_available_parquet_files, get_gene_counts_with_regions, get_total_read_count
    selected_genes = SelectedGene.objects.all()
    parquet_files = get_available_parquet_files()
    plot_div = None
    file1 = None
    file2 = None

    # Check if any files are available
    if not parquet_files:
        return render(request, "riboApp/geneCounts.html", {"error_message": "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis.", "parquet_files": []})

    if request.method == "POST":
        file1 = request.POST.get("file1")
        file2 = request.POST.get("file2")
        cds_only = request.POST.get("cds_only") == "true"
        show_regions = request.POST.get("show_regions") == "true"
        normalize_by_total = request.POST.get("normalize_by_total") == "true"

        if file1 and file2:
            if show_regions:
                # Use region-aware function for colored plotting
                df = get_gene_counts_with_regions(file1, file2, cds_only=cds_only)

                # Apply normalization if requested
                if normalize_by_total:
                    total_reads_1 = get_total_read_count(file1, "riboseq")
                    total_reads_2 = get_total_read_count(file2, "riboseq")

                    if total_reads_1 > 0 and total_reads_2 > 0:
                        # Normalize to RPM (Reads Per Million)
                        df["read_count_x"] = (df["read_count_x"] / total_reads_1) * 1e6
                        df["read_count_y"] = (df["read_count_y"] / total_reads_2) * 1e6

                # Calculate correlation coefficient
                correlation = df["read_count_x"].corr(df["read_count_y"])
                r_squared = correlation ** 2

                # Define colors for different regions
                region_colors = {
                    'CDS': '#1f77b4',      # Blue
                    '5UTR': '#ff7f0e',     # Orange
                    '3UTR': '#2ca02c',     # Green
                    'UNKNOWN': '#9467bd',  # Purple
                }

                region_text = " (CDS only)" if cds_only else " by Region"
                norm_text = " (RPM Normalized)" if normalize_by_total else ""

                x_label = f"{file1} (RPM)" if normalize_by_total else file1
                y_label = f"{file2} (RPM)" if normalize_by_total else file2

                fig = px.scatter(
                    df,
                    x="read_count_x",
                    y="read_count_y",
                    color="region",
                    hover_name="gene_name",
                    hover_data=["region"],
                    title=f"Gene Read Counts{region_text}{norm_text}: {file1} vs {file2}<br><sub>Overall R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
                    labels={
                        "read_count_x": x_label,
                        "read_count_y": y_label,
                        "region": "Genomic Region"
                    },
                    color_discrete_map=region_colors
                )

                # Make 5UTR points transparent so underlying points are visible
                for trace in fig.data:
                    if trace.name == '5UTR':
                        trace.update(
                            marker=dict(
                                opacity=0.4,  # Make 5UTR points transparent
                                line=dict(width=1, color='#ff7f0e')  # Add border for visibility
                            )
                        )
            else:
                # Use traditional aggregated function for single-color plotting
                df = get_gene_counts(file1, file2, cds_only=cds_only, normalize_by_total=normalize_by_total)

                # Calculate correlation coefficient
                correlation = df["read_count_x"].corr(df["read_count_y"])
                r_squared = correlation ** 2

                region_text = " (CDS only)" if cds_only else ""
                norm_text = " (RPM Normalized)" if normalize_by_total else ""

                x_label = f"{file1} (RPM)" if normalize_by_total else file1
                y_label = f"{file2} (RPM)" if normalize_by_total else file2

                fig = px.scatter(
                    df,
                    x="read_count_x",
                    y="read_count_y",
                    hover_name="gene_name",
                    title=f"Gene Read Counts{region_text}{norm_text}: {file1} vs {file2}<br><sub>R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
                    labels={"read_count_x": x_label, "read_count_y": y_label},
                )

            plot_div = fig.to_html(full_html=False)

    return render(request, "riboApp/geneCounts.html", {
        "selected_genes": selected_genes,
        "parquet_files": parquet_files,
        "plot_div": plot_div,
        "file1": file1,
        "file2": file2,
    })


def log2_geneCounts(request):
    """Gene counts analysis with log2 scale on both axes"""
    from .analysis.data_getters import get_available_parquet_files, get_gene_counts_with_regions, get_total_read_count
    selected_genes = SelectedGene.objects.all()
    parquet_files = get_available_parquet_files()
    plot_div = None
    file1 = None
    file2 = None

    # Check if any files are available
    if not parquet_files:
        return render(request, "riboApp/log2GeneCounts.html", {"error_message": "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis.", "parquet_files": []})

    if request.method == "POST":
        file1 = request.POST.get("file1")
        file2 = request.POST.get("file2")
        cds_only = request.POST.get("cds_only") == "true"
        show_regions = request.POST.get("show_regions") == "true"
        normalize_by_total = request.POST.get("normalize_by_total") == "true"

        if file1 and file2:
            if show_regions:
                # Use region-aware function for colored plotting
                df = get_gene_counts_with_regions(file1, file2, cds_only=cds_only)

                # Apply normalization if requested
                if normalize_by_total:
                    total_reads_1 = get_total_read_count(file1, "riboseq")
                    total_reads_2 = get_total_read_count(file2, "riboseq")

                    if total_reads_1 > 0 and total_reads_2 > 0:
                        # Normalize to RPM (Reads Per Million)
                        df["read_count_x"] = (df["read_count_x"] / total_reads_1) * 1e6
                        df["read_count_y"] = (df["read_count_y"] / total_reads_2) * 1e6

                # Filter out zero values for log2 transformation
                df = df[(df["read_count_x"] > 0) & (df["read_count_y"] > 0)]

                # Calculate correlation coefficient
                correlation = df["read_count_x"].corr(df["read_count_y"])
                r_squared = correlation ** 2

                # Define colors for different regions
                region_colors = {
                    'CDS': '#1f77b4',      # Blue
                    '5UTR': '#ff7f0e',     # Orange
                    '3UTR': '#2ca02c',     # Green
                    'UNKNOWN': '#9467bd',  # Purple
                }

                region_text = " (CDS only)" if cds_only else " by Region"
                norm_text = " (RPM Normalized)" if normalize_by_total else ""

                x_label = f"{file1} (RPM, Log₂)" if normalize_by_total else f"{file1} (Log₂)"
                y_label = f"{file2} (RPM, Log₂)" if normalize_by_total else f"{file2} (Log₂)"

                fig = px.scatter(
                    df,
                    x="read_count_x",
                    y="read_count_y",
                    color="region",
                    hover_name="gene_name",
                    hover_data=["region"],
                    title=f"Gene Read Counts{region_text}{norm_text} (Log₂ Scale): {file1} vs {file2}<br><sub>Overall R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
                    labels={
                        "read_count_x": x_label,
                        "read_count_y": y_label,
                        "region": "Genomic Region"
                    },
                    color_discrete_map=region_colors,
                    log_x=True,
                    log_y=True
                )

                # Make 5UTR points transparent so underlying points are visible
                for trace in fig.data:
                    if trace.name == '5UTR':
                        trace.update(
                            marker=dict(
                                opacity=0.4,  # Make 5UTR points transparent
                                line=dict(width=1, color='#ff7f0e')  # Add border for visibility
                            )
                        )
            else:
                # Use traditional aggregated function for single-color plotting
                df = get_gene_counts(file1, file2, cds_only=cds_only, normalize_by_total=normalize_by_total)

                # Filter out zero values for log2 transformation
                df = df[(df["read_count_x"] > 0) & (df["read_count_y"] > 0)]

                # Calculate correlation coefficient
                correlation = df["read_count_x"].corr(df["read_count_y"])
                r_squared = correlation ** 2

                region_text = " (CDS only)" if cds_only else ""
                norm_text = " (RPM Normalized)" if normalize_by_total else ""

                x_label = f"{file1} (RPM, Log₂)" if normalize_by_total else f"{file1} (Log₂)"
                y_label = f"{file2} (RPM, Log₂)" if normalize_by_total else f"{file2} (Log₂)"

                fig = px.scatter(
                    df,
                    x="read_count_x",
                    y="read_count_y",
                    hover_name="gene_name",
                    title=f"Gene Read Counts{region_text}{norm_text} (Log₂ Scale): {file1} vs {file2}<br><sub>R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
                    labels={
                        "read_count_x": x_label,
                        "read_count_y": y_label
                    },
                    log_x=True,
                    log_y=True
                )

            plot_div = fig.to_html(full_html=False)

    return render(request, "riboApp/log2GeneCounts.html", {
        "selected_genes": selected_genes,
        "parquet_files": parquet_files,
        "plot_div": plot_div,
        "file1": file1,
        "file2": file2,
    })


def plot_gene_counts(request):
    from .analysis.data_getters import get_gene_counts_with_regions, get_gene_counts
    file1 = request.GET.get("file1")
    file2 = request.GET.get("file2")
    cds_only = request.GET.get("cds_only") == "true"
    show_regions = request.GET.get("show_regions") == "true"

    if not file1 or not file2:
        print("ERROR: No files selected!")
        return JsonResponse({"error": "No files selected."})

    cache_key = f"gene_counts_json_{file1}_{file2}_cds_{cds_only}_regions_{show_regions}"

    # 🚀 Try persistent cache first
    cached_json = get_persistent_cache(cache_key)
    if cached_json is not None:
        print("⚡ Loaded plot JSON from persistent cache.")
        return JsonResponse(cached_json, safe=False)

    # Fallback to in-memory cache
    cached_json = cache.get(cache_key)
    if cached_json is not None:
        print("⚡ Loaded plot JSON from in-memory cache.")
        return JsonResponse(cached_json, safe=False)

    if show_regions:
        # Use region-aware function for colored plotting
        df = get_gene_counts_with_regions(file1, file2, cds_only=cds_only)

        if df.empty:
            print("ERROR: DataFrame is empty!")
            return JsonResponse({"error": "No data for scatter plot."})

        # Calculate correlation coefficient
        correlation = df["read_count_x"].corr(df["read_count_y"])
        r_squared = correlation ** 2

        # Define colors for different regions
        region_colors = {
            'CDS': '#1f77b4',      # Blue
            '5UTR': '#ff7f0e',     # Orange
            '3UTR': '#2ca02c',     # Green
            'UNKNOWN': '#9467bd',  # Purple
        }

        region_text = " (CDS only)" if cds_only else " by Region"

        fig = px.scatter(
            df,
            x="read_count_x",
            y="read_count_y",
            color="region",
            hover_name="gene_name",
            hover_data=["region"],
            title=f"Gene Read Counts{region_text}: {file1} vs {file2}<br><sub>Overall R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
            labels={
                "read_count_x": file1,
                "read_count_y": file2,
                "region": "Genomic Region"
            },
            color_discrete_map=region_colors
        )

        # Make 5UTR points transparent so underlying points are visible
        for trace in fig.data:
            if trace.name == '5UTR':
                trace.update(
                    marker=dict(
                        opacity=0.4,  # Make 5UTR points transparent
                        line=dict(width=1, color='#ff7f0e')  # Add border for visibility
                    )
                )
    else:
        # Use traditional aggregated function for single-color plotting
        df = get_gene_counts(file1, file2, cds_only=cds_only)

        if df.empty:
            print("ERROR: DataFrame is empty!")
            return JsonResponse({"error": "No data for scatter plot."})

        # Calculate correlation coefficient
        correlation = df["read_count_x"].corr(df["read_count_y"])
        r_squared = correlation ** 2

        region_text = " (CDS only)" if cds_only else ""
        fig = px.scatter(
            df,
            x="read_count_x",
            y="read_count_y",
            hover_name="gene_name",
            title=f"Gene Read Counts{region_text}: {file1} vs {file2}<br><sub>R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
            labels={"read_count_x": file1, "read_count_y": file2}
        )

    fig_json = fig.to_json()
    set_persistent_cache(cache_key, fig_json)  # 🚀 Persistent cache
    cache.set(cache_key, fig_json, timeout=None)  # In-memory cache
    print("Plot Generated Successfully and cached")
    return JsonResponse(fig_json, safe=False)




# File Paths (Adjust as Needed)
PARQUET_FOLDER = "media/parquetFiles/"
MRNA_FOLDER = "media/mrnaFiles/"
OFFSET_CSV = "media/uorf_psite_offset.csv"
NBINS = 4
SKIP_5PRIME = 45
SKIP_3PRIME = 15

import os
import pandas as pd
import pyarrow.parquet as pq
import numpy as np
import plotly.express as px
from django.shortcuts import render
from django.core.cache import cache
import shutil




def get_bin_counts(selected_file):
    from .analysis.data_getters import load_selected_genes, get_cached_region_stats
    selected_genes = load_selected_genes()
    print("🔍 Selected genes:", selected_genes)

    if not selected_genes:
        return None, "No selected genes found!"

    # Use a cache key so we don't re-generate plots unnecessarily
    genes_key = "_".join(sorted(selected_genes))
    cache_key = f"bin_counts_{selected_file}_{genes_key}"

    # 🚀 Try persistent cache first
    cached_plots = get_persistent_cache(cache_key)
    if cached_plots is not None:
        print(f"⚡ Loaded bin count plots from persistent cache for {selected_file}")
        return cached_plots, None

    # Fallback to in-memory cache
    cached_plots = cache.get(cache_key)
    if cached_plots is not None:
        print(f"⚡ Loaded bin count plots from in-memory cache for {selected_file}")
        return cached_plots, None

    file_basename = os.path.splitext(selected_file)[0]
    offsets_df = pd.read_csv(OFFSET_CSV)
    offsets_df = offsets_df[offsets_df["Experiment"] == file_basename]

    if offsets_df.empty:
        return None, f"No P-site offsets found for {file_basename}!"

    length_to_offset = dict(zip(offsets_df["Read Length"], offsets_df["P-site Offset"]))

    # 🚀 Try to use cached region stats first
    cached_stats = get_cached_region_stats(selected_file)
    if not cached_stats.empty:
        print(f"🚀 Using cached region stats for bin counts: {selected_file}")
        # For bin counts, we still need the full data with positions, so fall back to file reading
        # This optimization would require more complex caching of position data
        file_path = os.path.join(PARQUET_FOLDER, selected_file)
        df = pq.read_table(file_path, columns=["gene_name", "read_length", "start_position"]).to_pandas()
    else:
        print(f"⚠️ Cache miss for bin counts, reading file: {selected_file}")
        file_path = os.path.join(PARQUET_FOLDER, selected_file)
        df = pq.read_table(file_path, columns=["gene_name", "read_length", "start_position"]).to_pandas()

    df = df.query("gene_name in @selected_genes")

    if df.empty:
        return None, f"No data found for selected genes in {selected_file}!"

    df["offset"] = df["read_length"].map(length_to_offset)
    df.dropna(subset=["offset"], inplace=True)
    df["p_site"] = df["start_position"] + df["offset"].astype(int)

    bin_colors = ["#0099c6", "#17becf", "#19d3f3", "#00b5f7"]
    combined_bin_colors = ["#fa0087", "rgb(247, 129, 191)", "#fc1cbf", "rgb(254, 136, 177)"]

    plot_html = ""

    # List to collect normalized bin counts across all genes
    combined_fractions = []

    for gene_name in selected_genes:
        df_gene = df.query("gene_name == @gene_name")

        if df_gene.empty:
            continue

        p_min, p_max = df_gene["p_site"].min(), df_gene["p_site"].max()
        # Skip if region is too short
        if p_max - p_min < (SKIP_5PRIME + SKIP_3PRIME):
            continue

        cds_start = p_min + SKIP_5PRIME
        cds_end   = p_max - SKIP_3PRIME

        # Create 4 bin edges across the CDS region
        bin_edges = np.linspace(cds_start, cds_end + 1, NBINS + 1, dtype=int)

        df_filtered = df_gene.query("p_site >= @cds_start and p_site <= @cds_end")

        # Label each p_site with a bin
        df_filtered["bin"] = pd.cut(
            df_filtered["p_site"],
            bins=bin_edges,
            labels=[f"Bin{i}" for i in range(1, NBINS + 1)],
            right=False
        )

        # Count reads per bin, ensuring we have 4 bins even if some are zero
        bin_counts = (
            df_filtered
            .groupby("bin")["gene_name"]
            .count()
            .reindex([f"Bin{i}" for i in range(1, NBINS + 1)], fill_value=0)
        )

        # Generate the individual bar chart for this gene
        fig = px.bar(
            x=bin_counts.index,
            y=bin_counts.values,
            labels={"x": "CDS Bins", "y": "Read Counts"},
            title=f"Read Distribution for {gene_name} in {file_basename}",
        )
        fig.update_traces(marker=dict(color=bin_colors[:len(bin_counts)]))
        plot_html += fig.to_html(full_html=False)

        # Normalize bin counts for this gene (turn into fractions)
        total_reads = bin_counts.sum()
        if total_reads > 0:
            bin_fractions = bin_counts / total_reads
            combined_fractions.append(bin_fractions.values)

    # After processing all genes, make a combined average fraction plot
    if combined_fractions:
        # Average each bin across all genes
        average_fractions = np.mean(combined_fractions, axis=0)

        fig_combined = px.bar(
            x=[f"Bin{i}" for i in range(1, NBINS + 1)],
            y=average_fractions,
            labels={"x": "CDS Bins", "y": "Average Fraction"},
            title=f"Average Normalized Read Distribution for All Selected Genes in {file_basename}",
        )
        fig_combined.update_traces(marker=dict(color=combined_bin_colors[:len(average_fractions)]))
        plot_html += fig_combined.to_html(full_html=False)

    # Cache the final HTML (both persistent and in-memory)
    set_persistent_cache(cache_key, plot_html)  # 🚀 Persistent cache
    cache.set(cache_key, plot_html, timeout=None)  # In-memory cache
    print(f"Stored bin count plots in both persistent and in-memory cache for {selected_file}")

    return plot_html, None



def delta_analysis(request):
    """Delta analysis view comparing differences between replicates"""
    from .analysis.data_getters import get_available_parquet_files, get_available_mrna_parquet_files, get_cached_plot, set_cached_plot
    ribo_files = get_available_parquet_files()
    mrna_files = get_available_mrna_parquet_files()
    plot_div = None
    ribo_file1 = None
    ribo_file2 = None
    mrna_file1 = None
    mrna_file2 = None
    error_message = None

    # Check if any files are available
    if not ribo_files or not mrna_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    if request.method == "POST":
        ribo_file1 = request.POST.get("ribo_file1")
        ribo_file2 = request.POST.get("ribo_file2")
        mrna_file1 = request.POST.get("mrna_file1")
        mrna_file2 = request.POST.get("mrna_file2")

        if ribo_file1 and ribo_file2 and mrna_file1 and mrna_file2:
            # Check cache first
            cache_key = f"delta_analysis_{ribo_file1}_{ribo_file2}_{mrna_file1}_{mrna_file2}"
            cached_plot = get_cached_plot(cache_key)
            if cached_plot:
                print(f"🚀 Using cached delta analysis plot for {ribo_file1}, {ribo_file2}, {mrna_file1}, {mrna_file2}")
                plot_div = cached_plot
            else:
                df = get_delta_analysis_data(ribo_file1, ribo_file2, mrna_file1, mrna_file2)
                if not df.empty:
                    print(f"Generating delta analysis plot with region coloring")

                    # Calculate overall correlation coefficient for delta values
                    correlation = df["ribo_delta"].corr(df["mrna_delta"])
                    r_squared = correlation ** 2

                    # Define colors for different regions (map UTR5/UTR3 to 5UTR/3UTR)
                    region_colors = {
                        'CDS': '#87CEEB',      # Light Bright Blue
                        'UTR5': '#FF1493',     # Darker Brighter Pink
                        '5UTR': '#FF1493',     # Darker Brighter Pink (alternative name)
                        'UTR3': '#90EE90',     # Light Green
                        '3UTR': '#90EE90',     # Light Green (alternative name)
                        'UNKNOWN': '#FFD580',  # Light Orange
                        'Total': '#87CEEB'     # Light Bright Blue (fallback)
                    }

                    # Separate CDS from other regions so we can draw it on top
                    df_cds = df[df["region"] == "CDS"]
                    df_other = df[df["region"] != "CDS"]

                    # Create figure with non-CDS regions first
                    fig = px.scatter(
                        df_other,
                        x="ribo_delta",
                        y="mrna_delta",
                        color="region",
                        hover_name="gene_name",
                        hover_data=["region"],
                        title=f"Delta Analysis by Region: Ribo ({ribo_file1} vs {ribo_file2}) vs mRNA ({mrna_file1} vs {mrna_file2})<br><sub>Overall R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
                        labels={
                            "ribo_delta": f"Ribo Log₂ Fold Change ({ribo_file1}/{ribo_file2})",
                            "mrna_delta": f"mRNA Log₂ Fold Change ({mrna_file1}/{mrna_file2})",
                            "region": "Genomic Region"
                        },
                        color_discrete_map=region_colors
                    )

                    # Add CDS points on top (drawn last = appears on top)
                    if not df_cds.empty:
                        fig.add_trace(
                            px.scatter(
                                df_cds,
                                x="ribo_delta",
                                y="mrna_delta",
                                hover_name="gene_name",
                                hover_data=["region"]
                            ).data[0]
                        )
                        # Update the CDS trace with proper styling
                        fig.data[-1].marker.color = region_colors['CDS']
                        fig.data[-1].name = "CDS"
                        fig.data[-1].legendgroup = "CDS"

                    # Add reference lines at x=0 and y=0
                    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.7)
                    fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.7)

                    # Add quadrant labels
                    fig.add_annotation(x=df["ribo_delta"].max() * 0.8, y=df["mrna_delta"].max() * 0.8,
                                     text="Both ↑", showarrow=False, font=dict(size=12, color="green"))
                    fig.add_annotation(x=df["ribo_delta"].min() * 0.8, y=df["mrna_delta"].min() * 0.8,
                                     text="Both ↓", showarrow=False, font=dict(size=12, color="red"))
                    fig.add_annotation(x=df["ribo_delta"].max() * 0.8, y=df["mrna_delta"].min() * 0.8,
                                     text="Ribo ↑, mRNA ↓", showarrow=False, font=dict(size=10, color="orange"))
                    fig.add_annotation(x=df["ribo_delta"].min() * 0.8, y=df["mrna_delta"].max() * 0.8,
                                     text="Ribo ↓, mRNA ↑", showarrow=False, font=dict(size=10, color="orange"))

                    plot_div = fig.to_html(full_html=False)

                    # Cache the plot
                    set_cached_plot(cache_key, plot_div, timeout=None)  # Cache indefinitely
                    print(f"💾 Cached delta analysis plot for {ribo_file1}, {ribo_file2}, {mrna_file1}, {mrna_file2}")

    return render(request, "riboApp/deltaAnalysis.html", {
        "ribo_files": ribo_files,
        "mrna_files": mrna_files,
        "plot_div": plot_div,
        "ribo_file1": ribo_file1,
        "ribo_file2": ribo_file2,
        "mrna_file1": mrna_file1,
        "mrna_file2": mrna_file2,
        "error_message": error_message,
    })



def combined_geneCounts(request):
    """Combined gene counts view for riboseq and mRNA files"""
    from .analysis.data_getters import get_available_parquet_files, get_available_mrna_parquet_files
    selected_genes = SelectedGene.objects.all()
    ribo_files = get_available_parquet_files()
    mrna_files = get_available_mrna_parquet_files()
    plot_div = None
    ribo_file = None
    mrna_file = None
    error_message = None

    # Check if any files are available
    if not ribo_files or not mrna_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    if request.method == "POST":
        ribo_file = request.POST.get("ribo_file")
        mrna_file = request.POST.get("mrna_file")
        if ribo_file and mrna_file:
            df = get_combined_gene_counts(ribo_file, mrna_file)
            print(f"Generating combined scatter plot with region coloring for {ribo_file} (Ribo) vs {mrna_file} (mRNA)")

            # Calculate overall correlation coefficient
            correlation = df["ribo_count"].corr(df["mrna_count"])
            r_squared = correlation ** 2

            # Define colors for different regions
            region_colors = {
                'CDS': '#1f77b4',      # Blue
                '5UTR': '#ff7f0e',     # Orange
                '3UTR': '#2ca02c',     # Green
                'Total': '#d62728'     # Red (fallback)
            }

            fig = px.scatter(
                df,
                x="ribo_count",
                y="mrna_count",
                color="region",
                hover_name="gene_name",
                hover_data=["region"],
                title=f"Gene Read Counts by Region: {ribo_file} (Ribo) vs {mrna_file} (mRNA)<br><sub>Overall R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
                labels={
                    "ribo_count": f"Riboseq: {ribo_file}",
                    "mrna_count": f"mRNA: {mrna_file}",
                    "region": "Genomic Region"
                },
                color_discrete_map=region_colors
            )
            plot_div = fig.to_html(full_html=False)

    return render(request, "riboApp/combinedGeneCounts.html", {
        "selected_genes": selected_genes,
        "ribo_files": ribo_files,
        "mrna_files": mrna_files,
        "plot_div": plot_div,
        "ribo_file": ribo_file,
        "mrna_file": mrna_file,
        "error_message": error_message,
    })




def bin_counts_view(request):
    from .analysis.data_getters import get_available_parquet_files
    parquet_files = get_available_parquet_files()
    plots = None
    error_message = None

    selected_file = request.GET.get("selected_file", "")

    # Check if any files are available
    if not parquet_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    if request.method == "POST":
        selected_file = request.POST.get("selected_file")
        if selected_file:
            plots, error_message = get_bin_counts(selected_file)
        else:
            error_message = "No file selected!"

    return render(
        request,
        "riboApp/binCounts.html",
        {
            "parquet_files": parquet_files,
            "plots": plots,
            "error_message": error_message,
            "selected_file": selected_file,
        },
    )


def get_read_length_distribution(selected_files):
    """
    Generate read length distribution plots for selected files.
    Returns combined normalized plot and individual plots.
    """
    if not selected_files:
        return None, "No files selected!"

    # Use cache key for the combination of files
    files_key = "_".join(sorted(selected_files))
    cache_key = f"read_length_dist_{files_key}"

    # 🚀 Try persistent cache first
    cached_plots = get_persistent_cache(cache_key)
    if cached_plots is not None:
        print(f"⚡ Loaded read length distribution plots from persistent cache for {files_key}")
        return cached_plots, None

    # Fallback to in-memory cache
    cached_plots = cache.get(cache_key)
    if cached_plots is not None:
        print(f"⚡ Loaded read length distribution plots from in-memory cache for {files_key}")
        return cached_plots, None

    plot_html = ""
    all_distributions = {}

    # Process each file
    for selected_file in selected_files:
        file_path = os.path.join(PARQUET_FOLDER, selected_file)
        if not os.path.exists(file_path):
            continue

        print(f"Processing read length distribution for {selected_file}")

        # Read the parquet file to get read lengths
        try:
            # Read in chunks to handle large files
            read_lengths = []
            pq_file = pq.ParquetFile(file_path)

            for batch in pq_file.iter_batches(batch_size=100000, columns=["read_length"]):
                df_chunk = batch.to_pandas()
                read_lengths.extend(df_chunk["read_length"].tolist())

            if not read_lengths:
                continue

            # Count occurrences of each read length
            read_length_counts = pd.Series(read_lengths).value_counts().sort_index()

            # Store for combined plot
            file_basename = os.path.splitext(selected_file)[0]
            all_distributions[file_basename] = {
                'lengths': read_length_counts.index.tolist(),
                'counts': read_length_counts.values.tolist(),
                'total_reads': sum(read_length_counts.values)
            }

            # Create individual plot for this file
            fig_individual = px.line(
                x=read_length_counts.index,
                y=read_length_counts.values,
                labels={"x": "Read Length (nt)", "y": "Count"},
                title=f"Read Length Distribution - {file_basename}",
            )
            fig_individual.update_traces(line=dict(width=2))
            fig_individual.update_layout(
                xaxis_title="Read Length (nt)",
                yaxis_title="Count",
                showlegend=False
            )
            plot_html += fig_individual.to_html(full_html=False)

        except Exception as e:
            print(f"Error processing {selected_file}: {str(e)}")
            continue

    # Create combined normalized plot
    if all_distributions:
        combined_data = []
        colors = px.colors.qualitative.Set1[:len(all_distributions)]

        for i, (file_name, data) in enumerate(all_distributions.items()):
            # Normalize by total reads
            normalized_counts = [count / data['total_reads'] for count in data['counts']]

            for length, norm_count in zip(data['lengths'], normalized_counts):
                combined_data.append({
                    'Read Length': length,
                    'Normalized Count': norm_count,
                    'Sample': file_name
                })

        combined_df = pd.DataFrame(combined_data)

        fig_combined = px.line(
            combined_df,
            x='Read Length',
            y='Normalized Count',
            color='Sample',
            title="Normalized Read Length Distribution - All Samples",
            labels={"Read Length": "Read Length (nt)", "Normalized Count": "Normalized Count (reads/total reads)"}
        )
        fig_combined.update_traces(line=dict(width=2))
        fig_combined.update_layout(
            xaxis_title="Read Length (nt)",
            yaxis_title="Normalized Count (reads/total reads)",
            legend_title="Sample"
        )

        # Add combined plot at the beginning
        plot_html = fig_combined.to_html(full_html=False) + plot_html

    # Cache the final HTML (both persistent and in-memory)
    set_persistent_cache(cache_key, plot_html)  # 🚀 Persistent cache
    cache.set(cache_key, plot_html, timeout=None)  # In-memory cache
    print(f"Stored read length distribution plots in both persistent and in-memory cache for {files_key}")

    return plot_html, None


def read_length_distribution_view(request):
    """
    View for read length distribution analysis.
    """
    from .analysis.data_getters import get_available_parquet_files
    parquet_files = get_available_parquet_files()
    plots = None
    error_message = None
    selected_files = []

    # Check if any files are available
    if not parquet_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    if request.method == "POST":
        selected_files = request.POST.getlist("selected_files")
        if selected_files:
            plots, error_message = get_read_length_distribution(selected_files)
        else:
            error_message = "No files selected!"

    return render(
        request,
        "riboApp/readLengthDistribution.html",
        {
            "parquet_files": parquet_files,
            "plots": plots,
            "error_message": error_message,
            "selected_files": selected_files,
        },
    )


def generate_stop_codon_periodicity(selected_files):
    """
    Generate stop codon periodicity plots WITHOUT P-site shifts.
    Uses the EXACT same logic as process_metagene_data but without applying P-site offsets.
    """
    from .analysis.data_getters import get_cached_plot, set_cached_plot, get_cached_psite_offsets

    if not selected_files:
        return None, "No files selected!"

    # Check cache first
    cache_key = f"psite_offset_{'_'.join(sorted(selected_files))}"
    cached_result = get_cached_plot(cache_key)
    if cached_result:
        print(f"🚀 Using cached P-site offset plot for {', '.join(selected_files)}")
        return cached_result, None

    # Load P-site offsets (needed for read length filtering)
    offsets_df = get_cached_psite_offsets()
    if offsets_df.empty:
        return None, "P-site offset CSV file not found! Please configure P-site offsets first."

    # Ensure correct column names
    if "P_site_offset" not in offsets_df.columns:
        offsets_df.columns = ["experiment", "read_length", "P_site_offset"]

    # Process each selected file using EXACT same logic as process_metagene_data
    all_stop_data = []

    for selected_file in selected_files:
        file_basename = os.path.splitext(selected_file)[0]
        file_path = os.path.join(PARQUET_FOLDER, selected_file)

        print(f"Processing stop codon periodicity for {selected_file}")

        # Get P-site offsets for this experiment
        file_offsets = offsets_df[offsets_df["experiment"] == file_basename]
        if file_offsets.empty:
            print(f"Warning: No P-site offsets found for {file_basename}")
            continue

        try:
            # Read parquet file - EXACT same as process_metagene_data
            df = pq.read_table(file_path, columns=[
                "gene_name", "start_position", "end_position", "read_length", "read_count", "region"
            ]).to_pandas()

            # Filter for CDS regions only - EXACT same as process_metagene_data
            df = df[df["region"] == "CDS"]

            if df.empty:
                print(f"Warning: No CDS data found in {selected_file}")
                continue

            # Calculate total reads for normalization - EXACT same as process_metagene_data
            total_reads = df["read_count"].sum()

            # Use the EXACT same logic as process_metagene_data but for stop codon only
            stop_data = process_metagene_data_no_shift(df, file_offsets, file_basename, total_reads, "stop", None)
            if not stop_data.empty:
                all_stop_data.append(stop_data)

        except Exception as e:
            print(f"Error processing {selected_file}: {str(e)}")
            continue

    if not all_stop_data:
        return None, "No valid data found for selected files"

    # Combine data from all files - EXACT same as existing
    combined_stop = pd.concat(all_stop_data, ignore_index=True)

    # Create the plot using the same function as existing metagene analysis
    plot_html = create_metagene_plot(
        combined_stop,
        "Stop Codon Periodicity (No P-site Shifts Applied)",
        xlim=(-20, 60)
    )

    # Cache the result for faster subsequent access
    set_cached_plot(cache_key, plot_html)
    print(f"💾 Cached P-site offset plot for {', '.join(selected_files)}")

    return plot_html, None


def process_metagene_data_no_shift(df, file_offsets, experiment_name, total_reads, site_type, selected_genes=None):
    """
    EXACT copy of process_metagene_data but WITHOUT applying P-site offsets.
    This is identical to the existing function except: df_filtered["p_site"] = df_filtered["start_position"]
    """

    # Filter by selected genes if provided - EXACT same as original
    if selected_genes:
        df = df[df["gene_name"].isin(selected_genes)]
        if df.empty:
            return pd.DataFrame()

    # Create offset mapping - EXACT same as original
    length_to_offset = dict(zip(file_offsets["read_length"], file_offsets["P_site_offset"]))

    # Filter for read lengths 28-32 (typical ribosome footprint sizes) - EXACT same as original
    df_filtered = df[df["read_length"].between(28, 32)].copy()

    if df_filtered.empty:
        return pd.DataFrame()

    # Apply P-site offsets - THIS IS THE ONLY DIFFERENCE
    df_filtered["offset"] = df_filtered["read_length"].map(length_to_offset)
    df_filtered = df_filtered.dropna(subset=["offset"])
    # ORIGINAL: df_filtered["p_site"] = df_filtered["start_position"] + df_filtered["offset"].astype(int)
    # NO SHIFT: df_filtered["p_site"] = df_filtered["start_position"]  # NO OFFSET APPLIED
    df_filtered["p_site"] = df_filtered["start_position"]  # NO OFFSET APPLIED

    metagene_data = []

    # Group by gene to get start/stop positions - EXACT same as original
    for gene_name, gene_df in df_filtered.groupby("gene_name"):
        if len(gene_df) < 10:  # Skip genes with too few reads - EXACT same as original
            continue

        if site_type == "start":
            # Use the minimum P-site position as the start codon reference - EXACT same as original
            reference_pos = gene_df["p_site"].min()
            # Look at positions from -30 to +62 relative to start - EXACT same as original
            position_range = range(-30, 63)
        else:  # stop - MODIFIED to show raw positions without P-site shifts
            # For the unshifted version, we need to find the actual stop codon position
            # Since we're not applying P-site shifts, we need to account for the fact that
            # the raw read positions will be offset from the actual stop codon

            # Find the end of the CDS region (this should be near the stop codon)
            p_sites = gene_df["p_site"].sort_values()
            # Use the 95th percentile as the reference, but adjust for the expected offset
            raw_reference_pos = int(p_sites.quantile(0.95))

            # Since we're not applying P-site shifts, the actual stop codon is likely
            # to be at a position that's offset from where the reads are mapping
            # For typical ribosome footprints, the P-site is usually ~12-15 nt from the 5' end
            # So the stop codon should be ~12-15 nt downstream from the raw read positions
            reference_pos = raw_reference_pos + 12  # Adjust reference to show raw offset pattern

            # Look at positions from -10 to +30 relative to the adjusted reference
            position_range = range(-10, 31)

        # Calculate relative positions - EXACT same as original
        gene_df = gene_df.copy()
        gene_df["relative_position"] = gene_df["p_site"] - reference_pos

        # Aggregate counts for each relative position - EXACT same as original
        for pos in position_range:
            pos_data = gene_df[gene_df["relative_position"] == pos]
            count = pos_data["read_count"].sum()

            if count > 0:  # Only include positions with reads - EXACT same as original
                metagene_data.append({
                    "experiment": experiment_name,
                    "shifted_position": pos,
                    "avg_count": (count / total_reads) * 1e6,  # Normalize to RPM - EXACT same as original
                    "gene_name": gene_name
                })

    if not metagene_data:
        return pd.DataFrame()

    # Convert to DataFrame and aggregate across genes for each experiment - EXACT same as original
    metagene_df = pd.DataFrame(metagene_data)

    if selected_genes:
        # When using selected genes, combine all genes into a single line per experiment - EXACT same as original
        # Sum the counts across all selected genes for each position - EXACT same as original
        result = metagene_df.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].sum()
        # Add a label to indicate this is selected genes - EXACT same as original
        result["experiment"] = result["experiment"] + " (Selected Genes)"
    else:
        # Average across all genes for each position and experiment (original behavior) - EXACT same as original
        result = metagene_df.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].mean()

    return result


def save_psite_offsets_csv(offset_data):
    """Save P-site offset data to CSV file"""
    try:
        # Convert offset data to DataFrame
        rows = []
        for experiment, read_lengths in offset_data.items():
            for read_length, offset in read_lengths.items():
                rows.append({
                    "Experiment": experiment,
                    "Read Length": int(read_length),
                    "P-site Offset": int(offset)
                })

        df = pd.DataFrame(rows)
        df = df.sort_values(["Experiment", "Read Length"])

        # Save to CSV
        df.to_csv(OFFSET_CSV, index=False)
        print(f"Saved P-site offsets to {OFFSET_CSV}")
        return True

    except Exception as e:
        print(f"Error saving P-site offsets: {str(e)}")
        return False


def psite_offset_view(request):
    """
    View for P-site offset analysis and configuration.
    Shows stop codon periodicity without P-site shifts and allows offset input.
    """
    from .analysis.data_getters import get_available_parquet_files, get_cached_plot, set_cached_plot
    parquet_files = get_available_parquet_files()
    plot_html = None
    error_message = None
    success_message = None
    selected_files = []
    current_offsets = {}

    # Check if any files are available
    if not parquet_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    # Load current P-site offsets if they exist
    if os.path.exists(OFFSET_CSV):
        try:
            offsets_df = pd.read_csv(OFFSET_CSV)
            for _, row in offsets_df.iterrows():
                exp = row["Experiment"]
                if exp not in current_offsets:
                    current_offsets[exp] = {}
                current_offsets[exp][str(row["Read Length"])] = row["P-site Offset"]
        except Exception as e:
            print(f"Error loading current offsets: {str(e)}")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "generate_plot":
            selected_files = request.POST.getlist("selected_files")
            if selected_files:
                plot_html, error_message = generate_stop_codon_periodicity(selected_files)
            else:
                error_message = "No files selected!"

        elif action == "upload_csv":
            uploaded_file = request.FILES.get("offset_csv")
            if uploaded_file:
                try:
                    # Read uploaded CSV
                    df = pd.read_csv(uploaded_file)

                    # Validate CSV format
                    required_columns = {"Experiment", "Read Length", "P-site Offset"}
                    if not required_columns.issubset(set(df.columns)):
                        error_message = f"CSV must contain columns: {', '.join(required_columns)}"
                    else:
                        # Save the uploaded file
                        df.to_csv(OFFSET_CSV, index=False)
                        success_message = "P-site offset CSV uploaded successfully!"

                        # Reload current offsets
                        current_offsets = {}
                        for _, row in df.iterrows():
                            exp = row["Experiment"]
                            if exp not in current_offsets:
                                current_offsets[exp] = {}
                            current_offsets[exp][str(row["Read Length"])] = row["P-site Offset"]

                except Exception as e:
                    error_message = f"Error processing uploaded CSV: {str(e)}"
            else:
                error_message = "No file uploaded!"

        elif action == "manual_input":
            # Process manual offset input
            try:
                offset_data = {}

                # Get all form data for manual offsets
                for key, value in request.POST.items():
                    if key.startswith("offset_") and value.strip():
                        # Parse key: offset_ExperimentName_ReadLength
                        # Remove "offset_" prefix and split by last underscore
                        key_without_prefix = key[7:]  # Remove "offset_"
                        parts = key_without_prefix.rsplit("_", 1)  # Split from right, only once

                        if len(parts) == 2:
                            experiment = parts[0]
                            read_length = parts[1]

                            if experiment not in offset_data:
                                offset_data[experiment] = {}
                            offset_data[experiment][read_length] = int(value)

                if offset_data:
                    if save_psite_offsets_csv(offset_data):
                        success_message = "P-site offsets saved successfully!"
                        current_offsets = offset_data
                    else:
                        error_message = "Error saving P-site offsets!"
                else:
                    error_message = "No offset values provided!"

            except Exception as e:
                error_message = f"Error processing manual input: {str(e)}"

    return render(
        request,
        "riboApp/psiteOffset.html",
        {
            "parquet_files": parquet_files,
            "plot_html": plot_html,
            "error_message": error_message,
            "success_message": success_message,
            "selected_files": selected_files,
            "current_offsets": current_offsets,
        },
    )


def stop_codon_readthrough(request):
    """Stop codon readthrough analysis separated by stop codon type (TAA/TAG/TGA)"""
    # Use new modular system
    from .analysis import stop_codon_readthrough as scr_module
    from .analysis.data_getters import get_available_parquet_files

    parquet_files = get_available_parquet_files()
    plot_html = None
    error_message = None
    selected_files = []

    has_csv_data = False

    # Check if any files are available
    if not parquet_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    if request.method == "POST":
        selected_files = request.POST.getlist("selected_files")

        if selected_files:
            # Generate plots using new modular system
            plot_html, error_message, csv_data = scr_module.generate_stop_codon_readthrough_plots(selected_files)

            # Store CSV data in session for download
            if csv_data is not None:
                request.session['stop_codon_csv_data'] = csv_data.to_json()
                has_csv_data = True
        else:
            error_message = "No files selected!"

    return render(
        request,
        "riboApp/stopCodonReadthrough.html",
        {
            "parquet_files": parquet_files,
            "plot_html": plot_html,
            "error_message": error_message,
            "selected_files": selected_files,
            "has_csv_data": has_csv_data,
        },
    )


def download_stop_codon_csv(request):
    """Download CSV data for stop codon readthrough analysis"""
    csv_json = request.session.get('stop_codon_csv_data')

    if not csv_json:
        return HttpResponse("No data available for download", status=404)

    # Convert JSON back to DataFrame
    df = pd.read_json(csv_json)

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="stop_codon_readthrough_data.csv"'

    # Write CSV
    df.to_csv(response, index=False)

    return response


def generate_stop_codon_readthrough_by_type(selected_files):
    """Generate stop codon periodicity plots separated by stop codon type"""
    if not selected_files:
        return None, "No files selected!"

    # Get stop codon types from cache
    stop_codon_types = get_cached_stop_codons()
    if not stop_codon_types:
        return None, "Could not extract stop codon types from FASTA file!"

    # Load P-site offsets
    offsets_df = get_cached_psite_offsets()
    if offsets_df.empty:
        return None, "P-site offset CSV file not found! Please configure P-site offsets first."

    # Ensure correct column names
    if "P_site_offset" not in offsets_df.columns:
        offsets_df.columns = ["experiment", "read_length", "P_site_offset"]

    # Process each selected file
    all_stop_data = {'TAA': [], 'TAG': [], 'TGA': []}

    for selected_file in selected_files:
        file_basename = os.path.splitext(selected_file)[0]
        file_path = os.path.join(PARQUET_FOLDER, selected_file)

        print(f"Processing stop codon readthrough for {selected_file}")

        # Get P-site offsets for this experiment
        file_offsets = offsets_df[offsets_df["experiment"] == file_basename]
        if file_offsets.empty:
            print(f"Warning: No P-site offsets found for {file_basename}")
            continue

        try:
            # Read parquet file
            df = pq.read_table(file_path, columns=[
                "gene_name", "start_position", "end_position", "read_length", "read_count", "region"
            ]).to_pandas()

            # Filter for CDS and UTR3 regions (UTR3 contains readthrough reads!)
            df = df[df["region"].isin(["CDS", "UTR3"])]

            if df.empty:
                print(f"Warning: No CDS/UTR3 data found in {selected_file}")
                continue

            # Calculate total reads for normalization
            total_reads = df["read_count"].sum()

            # Process stop codon data for each stop codon type
            for stop_type in ['TAA', 'TAG', 'TGA']:
                # Filter genes by stop codon type
                genes_with_stop_type = [gene for gene, sc in stop_codon_types.items() if sc == stop_type]

                if not genes_with_stop_type:
                    continue

                # Filter dataframe to only include genes with this stop codon type
                df_filtered = df[df["gene_name"].isin(genes_with_stop_type)]

                if df_filtered.empty:
                    continue

                # Process metagene data for this stop codon type
                stop_data = process_metagene_data(
                    df_filtered, file_offsets, file_basename, total_reads, "stop", None
                )

                if not stop_data.empty:
                    # Rename columns to match what the plot function expects
                    stop_data = stop_data.rename(columns={
                        'shifted_position': 'position',
                        'avg_count': 'normalized_count'
                    })
                    # Add stop codon type column
                    stop_data['stop_codon_type'] = stop_type
                    all_stop_data[stop_type].append(stop_data)

        except Exception as e:
            print(f"Error processing {selected_file}: {str(e)}")
            continue

    # Check if we have data for any stop codon type
    if not any(all_stop_data.values()):
        return None, "No valid data found for selected files", None

    # Create combined plot with all three stop codon types
    plot_html = create_stop_codon_comparison_plot(all_stop_data)

    # Combine all data for CSV export
    all_data_combined = []
    for stop_type in ['TAA', 'TAG', 'TGA']:
        if all_stop_data[stop_type]:
            combined = pd.concat(all_stop_data[stop_type], ignore_index=True)
            all_data_combined.append(combined)

    csv_data = pd.concat(all_data_combined, ignore_index=True) if all_data_combined else None

    return plot_html, None, csv_data


def create_stop_codon_comparison_plot(all_stop_data):
    """Create separate plots for each sample, with each plot showing TAA/TAG/TGA lines"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # Colors for each stop codon type
    colors = {
        'TAA': '#1f77b4',  # Blue (lowest readthrough expected)
        'TAG': '#ff7f0e',  # Orange (intermediate)
        'TGA': '#2ca02c',  # Green (highest readthrough expected)
    }

    # First, organize data by experiment
    experiments_data = {}

    for stop_type in ['TAA', 'TAG', 'TGA']:
        if not all_stop_data[stop_type]:
            continue

        for df in all_stop_data[stop_type]:
            # DEBUG: Print sample of data
            print(f"\n🔍 DEBUG {stop_type} data sample:")
            print(df[['position', 'experiment', 'normalized_count']].head(10))

            # Group by experiment
            for experiment in df['experiment'].unique():
                if experiment not in experiments_data:
                    experiments_data[experiment] = {}

                exp_data = df[df['experiment'] == experiment].copy()
                exp_data = exp_data.sort_values('position')

                # DEBUG: Print position range
                print(f"  {experiment} - {stop_type}: positions from {exp_data['position'].min()} to {exp_data['position'].max()}")

                experiments_data[experiment][stop_type] = exp_data

    # Get list of experiments
    experiments = sorted(experiments_data.keys())
    num_experiments = len(experiments)

    if num_experiments == 0:
        return "<p>No data available for plotting</p>"

    # Create subplots - one row per experiment
    fig = make_subplots(
        rows=num_experiments,
        cols=1,
        subplot_titles=[f"<b>{exp}</b>" for exp in experiments],
        vertical_spacing=0.08,
        shared_xaxes=True
    )

    # Add traces for each experiment
    for idx, experiment in enumerate(experiments, start=1):
        exp_data = experiments_data[experiment]

        for stop_type in ['TAA', 'TAG', 'TGA']:
            if stop_type not in exp_data:
                continue

            data = exp_data[stop_type]

            # Add trace
            fig.add_trace(
                go.Scatter(
                    x=data['position'],
                    y=data['normalized_count'],
                    mode='lines+markers',
                    name=stop_type,
                    line=dict(color=colors[stop_type], width=2),
                    marker=dict(size=3),
                    legendgroup=stop_type,  # Group legends by stop codon type
                    showlegend=(idx == 1),  # Only show legend for first subplot
                    hovertemplate=f'<b>{stop_type}</b><br>' +
                                 'Position: %{x}<br>' +
                                 'Count (RPM): %{y:.2f}<br>' +
                                 '<extra></extra>'
                ),
                row=idx, col=1
            )

        # Add vertical line at stop codon position (0) for each subplot
        fig.add_vline(
            x=0, line_dash="dash", line_color="red", line_width=1,
            row=idx, col=1
        )

        # Add shaded region for readthrough area
        fig.add_vrect(
            x0=0, x1=60,
            fillcolor="lightgray", opacity=0.15,
            layer="below", line_width=0,
            row=idx, col=1
        )

    # Update layout
    fig.update_layout(
        title="Stop Codon Readthrough Analysis by Sample<br><sub>Each panel shows TAA, TAG, and TGA for one sample</sub>",
        hovermode='x unified',
        template='plotly_white',
        height=400 * num_experiments,  # Scale height based on number of experiments
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        )
    )

    # Update x-axes
    fig.update_xaxes(title_text="Position Relative to Stop Codon (nt)", row=num_experiments, col=1)

    # Update y-axes
    for idx in range(1, num_experiments + 1):
        fig.update_yaxes(title_text="Count (RPM)", row=idx, col=1)

    return fig.to_html(full_html=False)


# Use persistent storage location for GTF file on Elastic Beanstalk
import os
if os.environ.get('DJANGO_SETTINGS_MODULE'):
    GTF_FILE = "/var/app/data/gencode.vM25.annotation.gtf"
else:
    GTF_FILE = "media/gencode.vM25.annotation.gtf"

PARQUET_FOLDER = "media/parquetFiles/"          # Path where Parquet files are stored
TRANSCRIPTS_FASTA = "media/gencode.vM25.transcripts.fa"  # Path to transcript sequences
GENOME_FASTA = "media/GRCm38.primary_assembly.genome.fa"  # Path to genome sequence
STOP_CODON_TSV = "media/stopcodons.gene_stopcodons.per_gene_majority.tsv"  # Path to stop codon annotations

# ========================================
# GLOBAL CACHE VARIABLES FOR OPTIMIZATION
# ========================================

# Cache for gene lengths (expensive GTF parsing)
_GENE_LENGTHS_CACHE = None
_GENE_LENGTHS_CACHE_TIMESTAMP = None

# Cache for P-site offsets (frequently accessed)
_PSITE_OFFSETS_CACHE = None
_PSITE_OFFSETS_CACHE_TIMESTAMP = None

# Cache for available files (avoid repeated directory scans)
_AVAILABLE_FILES_CACHE = {
    'parquet': None,
    'mrna': None,
    'timestamp': None
}

# Cache for GTF gene annotations (expensive parsing)
_GTF_ANNOTATIONS_CACHE = None
_GTF_ANNOTATIONS_CACHE_TIMESTAMP = None

# Cache for stop codon types (expensive FASTA parsing)
_STOP_CODON_CACHE = None
_STOP_CODON_CACHE_TIMESTAMP = None
_STOP_CODON_POSITIONS_CACHE = None
_STOP_CODON_POSITIONS_CACHE_TIMESTAMP = None

# Cache timeout in seconds (5 minutes)
CACHE_TIMEOUT = 300

# ========================================
# GLOBAL CACHE HELPER FUNCTIONS
# ========================================

def get_cached_gene_lengths():
    """Get gene lengths from genome cache or calculate if needed"""
    # Use the new genome_cache module which handles pickle caching
    from riboApp.analysis import genome_cache
    gene_lengths_dict = genome_cache.load_gene_lengths()

    if not gene_lengths_dict:
        return pd.DataFrame()

    # Convert dict to DataFrame format expected by callers
    gene_lengths = pd.DataFrame([
        {"gene_name": gene, "length_kb": length / 1000}
        for gene, length in gene_lengths_dict.items()
    ])

    return gene_lengths[["gene_name", "length_kb"]]

def get_cached_psite_offsets():
    """Get P-site offsets from global cache or load if needed"""
    global _PSITE_OFFSETS_CACHE, _PSITE_OFFSETS_CACHE_TIMESTAMP

    current_time = time.time()

    # Check if cache is valid
    if (_PSITE_OFFSETS_CACHE is not None and
        _PSITE_OFFSETS_CACHE_TIMESTAMP is not None and
        current_time - _PSITE_OFFSETS_CACHE_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached P-site offsets")
        return _PSITE_OFFSETS_CACHE

    # Load and cache P-site offsets
    print("📊 Loading P-site offsets from CSV...")
    if os.path.exists(OFFSET_CSV):
        offsets_df = pd.read_csv(OFFSET_CSV)
        _PSITE_OFFSETS_CACHE = offsets_df
        _PSITE_OFFSETS_CACHE_TIMESTAMP = current_time
        print(f"💾 Cached P-site offsets for {len(offsets_df)} entries")
        return offsets_df
    else:
        print("⚠️ P-site offset CSV not found")
        return pd.DataFrame()



def clear_global_caches():
    """Clear all global caches - call when files are uploaded/deleted"""
    global _GENE_LENGTHS_CACHE, _GENE_LENGTHS_CACHE_TIMESTAMP
    global _PSITE_OFFSETS_CACHE, _PSITE_OFFSETS_CACHE_TIMESTAMP
    global _AVAILABLE_FILES_CACHE, _GTF_ANNOTATIONS_CACHE, _GTF_ANNOTATIONS_CACHE_TIMESTAMP

    _GENE_LENGTHS_CACHE = None
    _GENE_LENGTHS_CACHE_TIMESTAMP = None
    _PSITE_OFFSETS_CACHE = None
    _PSITE_OFFSETS_CACHE_TIMESTAMP = None
    _AVAILABLE_FILES_CACHE = {'parquet': None, 'mrna': None, 'timestamp': None}
    _GTF_ANNOTATIONS_CACHE = None
    _GTF_ANNOTATIONS_CACHE_TIMESTAMP = None
    _STOP_CODON_CACHE = None
    _STOP_CODON_CACHE_TIMESTAMP = None

    print("🧹 Cleared all global caches")

def get_cached_stop_codons():
    """Get stop codon types from global cache or load from TSV if needed"""
    global _STOP_CODON_CACHE, _STOP_CODON_CACHE_TIMESTAMP

    current_time = time.time()

    # Check if cache is valid
    if (_STOP_CODON_CACHE is not None and
        _STOP_CODON_CACHE_TIMESTAMP is not None and
        current_time - _STOP_CODON_CACHE_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached stop codon types")
        return _STOP_CODON_CACHE

    # Load and cache stop codon types from TSV
    print("📊 Loading stop codon types from TSV...")
    stop_codons = load_stop_codons_from_tsv(STOP_CODON_TSV)
    _STOP_CODON_CACHE = stop_codons
    _STOP_CODON_CACHE_TIMESTAMP = current_time
    print(f"💾 Cached stop codon types for {len(stop_codons)} genes")
    return stop_codons

def load_stop_codons_from_tsv(tsv_file):
    """Load stop codon annotations from TSV file

    Returns a dictionary: {gene_name: stop_codon_type}
    where stop_codon_type is 'TAA', 'TAG', or 'TGA'

    TSV format: gene_name\tstop_codon (tab-separated, no header)
    """
    if not os.path.exists(tsv_file):
        print(f"❌ Stop codon TSV file not found: {tsv_file}")
        return {}

    stop_codons = {}
    valid_stop_codons = {'TAA', 'TAG', 'TGA'}

    print(f"📖 Reading stop codon annotations from: {tsv_file}")

    with open(tsv_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) != 2:
                continue

            gene_name = parts[0]
            stop_codon = parts[1].upper()

            # Only store valid stop codons
            if stop_codon in valid_stop_codons:
                stop_codons[gene_name] = stop_codon

    print(f"✅ Loaded stop codons for {len(stop_codons)} genes")

    # Print distribution
    taa_count = sum(1 for sc in stop_codons.values() if sc == 'TAA')
    tag_count = sum(1 for sc in stop_codons.values() if sc == 'TAG')
    tga_count = sum(1 for sc in stop_codons.values() if sc == 'TGA')
    print(f"   TAA: {taa_count}, TAG: {tag_count}, TGA: {tga_count}")

    return stop_codons


def get_cached_stop_codon_positions():
    """Get stop codon positions from cache or load from GTF"""
    global _STOP_CODON_POSITIONS_CACHE, _STOP_CODON_POSITIONS_CACHE_TIMESTAMP

    # Check if cache is valid (5 minutes)
    if _STOP_CODON_POSITIONS_CACHE is not None and _STOP_CODON_POSITIONS_CACHE_TIMESTAMP is not None:
        if time.time() - _STOP_CODON_POSITIONS_CACHE_TIMESTAMP < 300:
            print("🚀 Using cached stop codon positions")
            return _STOP_CODON_POSITIONS_CACHE

    # Load from GTF
    print("📊 Loading stop codon positions from GTF...")
    positions = load_stop_codon_positions_from_gtf()
    return positions


def load_stop_codon_positions_from_gtf():
    """Extract stop codon positions from GTF file (now uses genome cache)

    Returns a dictionary: {gene_name: stop_codon_position}
    where stop_codon_position is the genomic coordinate of the stop codon
    """
    from riboApp.analysis import genome_cache

    # Load GTF data from cache
    gtf_data = genome_cache.load_gtf_data()

    if gtf_data is None or gtf_data.empty:
        print("❌ Could not load GTF data")
        return {}

    stop_positions = {}

    # Filter for stop_codon features
    stop_codon_data = gtf_data[gtf_data["feature"] == "stop_codon"]

    for _, row in stop_codon_data.iterrows():
        # Extract gene_name from attributes
        gene_name = None
        attrs = row["attribute"]
        for attr in attrs.split(';'):
            attr = attr.strip()
            if attr.startswith('gene_name'):
                gene_name = attr.split('"')[1]
                break

        if not gene_name:
            continue

        # For stop codon, we want the position where the ribosome P-site would be
        # The stop codon is 3 nucleotides, we want the first nucleotide
        strand = row["strand"]
        if strand == '+':
            # For positive strand, stop codon starts at 'start'
            stop_pos = row["start"]
        else:
            # For negative strand, stop codon starts at 'end'
            stop_pos = row["end"]

        # Store the stop codon position for this gene
        # If gene has multiple transcripts, we'll use the first one we encounter
        if gene_name not in stop_positions:
            stop_positions[gene_name] = stop_pos

    print(f"✅ Loaded stop codon positions for {len(stop_positions)} genes")
    return stop_positions


def calculate_gene_lengths(gtf_file):
    """
    Get gene lengths from genome cache.
    This now uses the pickle-cached version for instant loading.
    """
    from riboApp.analysis import genome_cache

    gene_lengths_dict = genome_cache.load_gene_lengths()

    if not gene_lengths_dict:
        print("ERROR: Could not load gene lengths!")
        return pd.DataFrame()

    # Convert dict to DataFrame format expected by callers
    gene_lengths = pd.DataFrame([
        {"gene_name": gene, "length_kb": length / 1000}
        for gene, length in gene_lengths_dict.items()
    ])

    print(f"Loaded gene lengths for {len(gene_lengths)} genes from cache.")
    return gene_lengths[["gene_name", "length_kb"]]

def process_parquet_file_gene_counts(file_path):
    """Process parquet file for gene counts - OPTIMIZED with cache"""
    from .analysis.data_getters import get_cached_gene_counts
    filename = os.path.basename(file_path)

    # 🚀 Try to use cached gene counts first
    cached_counts = get_cached_gene_counts(filename, "riboseq")
    if not cached_counts.empty:
        cached_counts["file_name"] = filename
        cached_counts.columns = ["gene_name", "read_count", "file_name"]
        print(f"🚀 Using cached gene counts for PCA: {filename}")
        return cached_counts

    # Fallback to file reading if cache miss
    print(f"⚠️ Cache miss for PCA, reading file: {filename}")
    df = pd.read_parquet(file_path)
    if "gene_name" not in df.columns or "read_count" not in df.columns:
        raise ValueError(f"Missing required columns in {file_path}")
    gene_counts = df.groupby("gene_name", as_index=False)["read_count"].sum()
    gene_counts["file_name"] = filename
    return gene_counts

def process_mrna_file_gene_counts(file_path):
    """Process mRNA parquet file for gene counts - OPTIMIZED with cache"""
    from .analysis.data_getters import get_cached_gene_counts
    filename = os.path.basename(file_path)

    # 🚀 Try to use cached gene counts first
    cached_counts = get_cached_gene_counts(filename, "mrna")
    if not cached_counts.empty:
        cached_counts["file_name"] = f"mRNA_{filename}"
        cached_counts.columns = ["gene_name", "read_count", "file_name"]
        print(f"🚀 Using cached mRNA gene counts for PCA: {filename}")
        return cached_counts

    # Fallback to file reading if cache miss
    print(f"⚠️ Cache miss for mRNA PCA, reading file: {filename}")
    df = pd.read_parquet(file_path)
    if "gene_name" not in df.columns or "read_count" not in df.columns:
        raise ValueError(f"Missing required columns in {file_path}")
    gene_counts = df.groupby("gene_name", as_index=False)["read_count"].sum()
    gene_counts["file_name"] = f"mRNA_{filename}"
    return gene_counts





def get_delta_analysis_data(ribo_file1, ribo_file2, mrna_file1, mrna_file2):
    """Get delta analysis data comparing differences between replicates with region information"""
    from .analysis.data_getters import load_or_build_gene_counts_dict, get_mrna_gene_counts_dict, get_region_gene_counts, get_cached_gene_counts

    # Get region-specific gene counts for all files
    ribo_counts1 = get_region_gene_counts(ribo_file1, "riboseq")
    ribo_counts2 = get_region_gene_counts(ribo_file2, "riboseq")
    mrna_counts1 = get_region_gene_counts(mrna_file1, "mrna")
    mrna_counts2 = get_region_gene_counts(mrna_file2, "mrna")

    if not all([ribo_counts1, ribo_counts2, mrna_counts1, mrna_counts2]):
        print("❌ Could not load region data, falling back to total counts")
        # Fallback to existing method without region info
        ribo_df1 = get_cached_gene_counts(ribo_file1, "riboseq")
        ribo_df2 = get_cached_gene_counts(ribo_file2, "riboseq")
        mrna_df1 = get_cached_gene_counts(mrna_file1, "mrna")
        mrna_df2 = get_cached_gene_counts(mrna_file2, "mrna")

        if not ribo_df1.empty and not ribo_df2.empty and not mrna_df1.empty and not mrna_df2.empty:
            ribo_total1 = dict(zip(ribo_df1['gene_name'], ribo_df1['total_count']))
            ribo_total2 = dict(zip(ribo_df2['gene_name'], ribo_df2['total_count']))
            mrna_total1 = dict(zip(mrna_df1['gene_name'], mrna_df1['total_count']))
            mrna_total2 = dict(zip(mrna_df2['gene_name'], mrna_df2['total_count']))
        else:
            ribo_total1 = load_or_build_gene_counts_dict(ribo_file1)
            ribo_total2 = load_or_build_gene_counts_dict(ribo_file2)
            mrna_total1 = get_mrna_gene_counts_dict(mrna_file1)
            mrna_total2 = get_mrna_gene_counts_dict(mrna_file2)

        all_genes = set(ribo_total1.keys()) & set(ribo_total2.keys()) & set(mrna_total1.keys()) & set(mrna_total2.keys())
        delta_data = []
        for gene in all_genes:
            ribo_count1 = ribo_total1.get(gene, 0)
            ribo_count2 = ribo_total2.get(gene, 0)
            mrna_count1 = mrna_total1.get(gene, 0)
            mrna_count2 = mrna_total2.get(gene, 0)

            # Only include if all counts are positive (needed for log2 fold change)
            if ribo_count1 > 0 and ribo_count2 > 0 and mrna_count1 > 0 and mrna_count2 > 0:
                # Calculate log2 fold changes (add pseudocount to avoid log(0))
                pseudocount = 1
                ribo_delta = np.log2((ribo_count1 + pseudocount) / (ribo_count2 + pseudocount))
                mrna_delta = np.log2((mrna_count1 + pseudocount) / (mrna_count2 + pseudocount))
                delta_data.append({
                    "gene_name": gene,
                    "ribo_delta": ribo_delta,
                    "mrna_delta": mrna_delta,
                    "region": "Total"  # Default region when no region data available
                })
        result_df = pd.DataFrame(delta_data)
        print(f"✅ Delta analysis data (no regions): {len(result_df)} genes")
        return result_df

    # Get all unique genes from all datasets
    all_genes = set(ribo_counts1.keys()) | set(ribo_counts2.keys()) | set(mrna_counts1.keys()) | set(mrna_counts2.keys())

    # Get all unique regions
    all_regions = set()
    for counts_dict in [ribo_counts1, ribo_counts2, mrna_counts1, mrna_counts2]:
        for gene_regions in counts_dict.values():
            all_regions.update(gene_regions.keys())

    print(f"📊 Found regions: {sorted(all_regions)}")

    delta_data = []
    for gene in all_genes:
        for region in all_regions:
            # Get counts for this gene and region from each file
            ribo_count1 = ribo_counts1.get(gene, {}).get(region, 0)
            ribo_count2 = ribo_counts2.get(gene, {}).get(region, 0)
            mrna_count1 = mrna_counts1.get(gene, {}).get(region, 0)
            mrna_count2 = mrna_counts2.get(gene, {}).get(region, 0)

            # Only include if both files have data for this gene-region combination (needed for log2 fold change)
            if ribo_count1 > 0 and ribo_count2 > 0 and mrna_count1 > 0 and mrna_count2 > 0:
                # Calculate log2 fold changes (add pseudocount to avoid log(0))
                pseudocount = 1
                ribo_delta = np.log2((ribo_count1 + pseudocount) / (ribo_count2 + pseudocount))
                mrna_delta = np.log2((mrna_count1 + pseudocount) / (mrna_count2 + pseudocount))

                delta_data.append({
                    "gene_name": gene,
                    "ribo_delta": ribo_delta,
                    "mrna_delta": mrna_delta,
                    "region": region
                })

    result_df = pd.DataFrame(delta_data)
    print(f"✅ Delta analysis data with regions: {len(result_df)} gene-region combinations")
    return result_df

def get_combined_gene_counts(ribo_file, mrna_file):
    """Get combined gene counts from riboseq and mRNA files with region information"""
    from .analysis.data_getters import load_or_build_gene_counts_dict, get_mrna_gene_counts_dict, get_region_gene_counts, get_cached_gene_counts

    # Get region-specific gene counts
    ribo_counts = get_region_gene_counts(ribo_file, "riboseq")
    mrna_counts = get_region_gene_counts(mrna_file, "mrna")

    if not ribo_counts or not mrna_counts:
        print("❌ Could not load region data, falling back to total counts")
        # Fallback to existing method without region info
        ribo_df = get_cached_gene_counts(ribo_file, "riboseq")
        mrna_df = get_cached_gene_counts(mrna_file, "mrna")

        if not ribo_df.empty and not mrna_df.empty:
            ribo_total = dict(zip(ribo_df['gene_name'], ribo_df['total_count']))
            mrna_total = dict(zip(mrna_df['gene_name'], mrna_df['total_count']))
        else:
            ribo_total = load_or_build_gene_counts_dict(ribo_file)
            mrna_total = get_mrna_gene_counts_dict(mrna_file)

        all_genes = set(ribo_total.keys()) | set(mrna_total.keys())
        combined_data = []
        for gene in all_genes:
            ribo_count = ribo_total.get(gene, 0)
            mrna_count = mrna_total.get(gene, 0)
            combined_data.append({
                "gene_name": gene,
                "ribo_count": ribo_count,
                "mrna_count": mrna_count,
                "region": "Total"
            })
        return pd.DataFrame(combined_data)

    # Get all unique genes from both datasets
    all_genes = set(ribo_counts.keys()) | set(mrna_counts.keys())

    # Get all unique regions
    all_regions = set()
    for gene_regions in ribo_counts.values():
        all_regions.update(gene_regions.keys())
    for gene_regions in mrna_counts.values():
        all_regions.update(gene_regions.keys())

    print(f"📊 Found regions: {sorted(all_regions)}")

    combined_data = []
    for gene in all_genes:
        for region in all_regions:
            # Get counts for this gene and region from each file
            ribo_count = ribo_counts.get(gene, {}).get(region, 0)
            mrna_count = mrna_counts.get(gene, {}).get(region, 0)

            # Only include if at least one file has data for this gene-region combination
            if ribo_count > 0 or mrna_count > 0:
                combined_data.append({
                    "gene_name": gene,
                    "ribo_count": ribo_count,
                    "mrna_count": mrna_count,
                    "region": region
                })

    result_df = pd.DataFrame(combined_data)
    print(f"✅ Combined gene counts with regions: {len(result_df)} gene-region combinations")
    return result_df


import hashlib

import hashlib
import glob
import os
import plotly.io as pio
from pathlib import Path
from django.conf import settings

# 🚀 PERSISTENT CACHE DIRECTORY FOR ANALYSIS RESULTS (lazy initialization)
def _get_analysis_cache_dir():
    """Get or create the analysis cache directory"""
    cache_dir = Path(settings.MEDIA_ROOT) / ".analysis_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def build_pca_cache_key():
    """Generates a cache key based only on input Parquet filenames (ignoring timestamps)."""

    if not os.path.exists(GTF_FILE):
        return None

    parquet_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")  # Ignore hidden files
    ])

    if not parquet_files:
        return "pca_no_parquet_files"

    # ✅ Create a stable hash key using only the sorted filenames
    key_string = "pca_" + "_".join(parquet_files)
    hashed_key = hashlib.md5(key_string.encode()).hexdigest()

    return f"pca_{hashed_key}"


def get_persistent_cache(cache_key):
    """Load analysis result from persistent pickle cache"""
    cache_dir = _get_analysis_cache_dir()
    cache_file = cache_dir / f"{cache_key}.pkl"
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                result = pickle.load(f)
                print(f"⚡ Loaded {cache_key} from persistent cache")
                return result
        except Exception as e:
            print(f"⚠️ Error loading persistent cache: {e}")
    return None


def set_persistent_cache(cache_key, data):
    """Save analysis result to persistent pickle cache"""
    try:
        cache_dir = _get_analysis_cache_dir()
        cache_file = cache_dir / f"{cache_key}.pkl"
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
            print(f"💾 Saved {cache_key} to persistent cache")
    except Exception as e:
        print(f"⚠️ Error saving persistent cache: {e}")

def pca_gene_counts(request):

    # Check if any parquet files are available first
    parquet_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")
    ])
    if not parquet_files:
        return render(request, "riboApp/pca_plot.html", {"error_message": "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."})

    if not os.path.exists(GTF_FILE):
        return render(request, "riboApp/pca_plot.html", {"error_message": "GTF file not found!"})

    cache_key = build_pca_cache_key()
    if cache_key is None:
        return render(request, "riboApp/pca_plot.html", {"error_message": "Failed to build cache key!"})

    print(f"Checking cache for key: {cache_key}")

    # 🚀 Try persistent cache first (survives server restart)
    cached_plot_json = get_persistent_cache(cache_key)
    if cached_plot_json is not None:
        print("⚡ Loaded PCA plot from persistent cache.")
        fig = pio.from_json(cached_plot_json)
        pca_plot_html = fig.to_html(full_html=False)
        return render(request, "riboApp/pca_plot.html", {"pca_plot": pca_plot_html})

    # Fallback to in-memory cache
    cached_plot_json = cache.get(cache_key)
    if cached_plot_json is not None:
        print("⚡ Loaded PCA plot from in-memory cache.")
        fig = pio.from_json(cached_plot_json)
        pca_plot_html = fig.to_html(full_html=False)
        return render(request, "riboApp/pca_plot.html", {"pca_plot": pca_plot_html})

    # Now, recompute the PCA plot (fig is defined here)
    print("PCA plot NOT found in cache. Recomputing...")

    print("Stored PCA plot in cache.")
    #
    # cache_key = build_pca_cache_key()
    # if cache_key is None:
    #     return render(request, "riboApp/error.html", {"error_message": "Failed to build cache key!"})
    # cached_plot = cache.get(cache_key)
    # if cached_plot is not None:
    #     print("Loaded PCA plot from cache.")
    #     return render(request, "riboApp/pca_plot.html", {"pca_plot": cached_plot})

    gene_lengths = get_cached_gene_lengths()
    if gene_lengths.empty:
        return render(request, "riboApp/pca_plot.html", {"error_message": "No gene lengths extracted from GTF!"})
    print(gene_lengths.head())

    # Load all Parquet files
    parquet_files = glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
    if not parquet_files:
        return render(request, "riboApp/pca_plot.html", {"error_message": "No Parquet files found!"})

    all_counts = []
    for file in parquet_files:
        df_counts = process_parquet_file_gene_counts(file)
        all_counts.append(df_counts)
    gene_counts_df = pd.concat(all_counts, ignore_index=True)

    # Ensure gene names match in format
    gene_counts_df["gene_name"] = gene_counts_df["gene_name"].str.strip().str.lower()
    gene_lengths["gene_name"] = gene_lengths["gene_name"].str.strip().str.lower()

    # Merge with gene lengths
    gene_counts_df = pd.merge(gene_counts_df, gene_lengths, on="gene_name", how="left")
    print(f"Columns in merged DataFrame: {gene_counts_df.columns.tolist()}")
    if "length_kb" not in gene_counts_df.columns:
        return render(request, "riboApp/pca_plot.html", {"error_message": "'length_kb' column missing after merging!"})

    gene_counts_df.dropna(subset=["length_kb"], inplace=True)
    gene_counts_df["length_kb"] = pd.to_numeric(gene_counts_df["length_kb"], errors="coerce")
    print(f"After filtering, {len(gene_counts_df)} rows remain.")

    # Pivot the DataFrame so that each file's gene counts are a separate column.
    pivot_df = gene_counts_df.pivot_table(index="gene_name", columns="file_name", values="read_count", fill_value=0).reset_index()
    pivot_df = pivot_df.merge(gene_counts_df[["gene_name", "length_kb"]].drop_duplicates(), on="gene_name", how="left")
    pivot_df["length_kb"] = pd.to_numeric(pivot_df["length_kb"], errors="coerce")
    if pivot_df.empty:
        return render(request, "riboApp/pca_plot.html", {"error_message": "No valid gene count data after pivoting!"})

    print(f"Pivoted DataFrame shape: {pivot_df.shape}")
    print(f"Columns in fixed pivot_df: {pivot_df.columns.tolist()}")

    # RPKM Normalization: Normalize the counts by gene length and library size.
    sample_cols = [col for col in pivot_df.columns if col not in ("gene_name", "length_kb")]
    for col in sample_cols:
        pivot_df[col] = (pivot_df[col] / pivot_df["length_kb"]) * 1e6 / pivot_df[col].sum()

    # Perform PCA using the normalized counts (transpose so that files are observations)
    pca = PCA(n_components=2)
    pca_results = pca.fit_transform(pivot_df[sample_cols].T)
    pca_df = pd.DataFrame({"PC1": pca_results[:, 0], "PC2": pca_results[:, 1], "file": sample_cols})

    # Get explained variance ratios
    pc1_var = pca.explained_variance_ratio_[0] * 100
    pc2_var = pca.explained_variance_ratio_[1] * 100

    # Generate the interactive PCA plot using Plotly
    fig = px.scatter(
        pca_df, x="PC1", y="PC2", hover_name="file", color="PC1",
        title=f"PCA of Gene Counts (RPKM Normalized)<br><sub>PC1: {pc1_var:.1f}% variance, PC2: {pc2_var:.1f}% variance</sub>",
        labels={"PC1": f"PC1 ({pc1_var:.1f}%)", "PC2": f"PC2 ({pc2_var:.1f}%)"}
    )
    pca_plot_html = fig.to_html(full_html=False)

    # Cache the result (both persistent and in-memory)
    pca_plot_json = fig.to_json()
    set_persistent_cache(cache_key, pca_plot_json)  # 🚀 Persistent cache
    cache.set(cache_key, pca_plot_json, timeout=None)  # In-memory cache
    print("Stored PCA plot in both persistent and in-memory cache.")
    return render(request, "riboApp/pca_plot.html", {"pca_plot": pca_plot_html})

def combined_pca_gene_counts(request):
    """Combined PCA analysis for riboseq and mRNA files"""

    # Build cache key for combined analysis
    ribo_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")
    ])
    mrna_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(MRNA_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")
    ])

    all_files = ribo_files + mrna_files
    if not all_files:
        return render(request, "riboApp/combinedPca.html", {"error_message": "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."})

    if not os.path.exists(GTF_FILE):
        return render(request, "riboApp/combinedPca.html", {"error_message": "GTF file not found!"})

    cache_key = f"combined_pca_{'_'.join(all_files)}"
    hashed_key = hashlib.md5(cache_key.encode()).hexdigest()
    cache_key = f"combined_pca_{hashed_key}"

    # 🚀 Try persistent cache first (survives server restart)
    cached_plot_json = get_persistent_cache(cache_key)
    if cached_plot_json is not None:
        print("⚡ Loaded combined PCA plot from persistent cache.")
        fig = pio.from_json(cached_plot_json)
        pca_plot_html = fig.to_html(full_html=False)
        return render(request, "riboApp/combinedPca.html", {"pca_plot": pca_plot_html})

    # Fallback to in-memory cache
    cached_plot_json = cache.get(cache_key)
    if cached_plot_json is not None:
        print("⚡ Loaded combined PCA plot from in-memory cache.")
        fig = pio.from_json(cached_plot_json)
        pca_plot_html = fig.to_html(full_html=False)
        return render(request, "riboApp/combinedPca.html", {"pca_plot": pca_plot_html})

    print("Combined PCA plot NOT found in cache. Recomputing...")

    gene_lengths = get_cached_gene_lengths()
    if gene_lengths.empty:
        return render(request, "riboApp/combinedPca.html", {"error_message": "No gene lengths extracted from GTF!"})

    # Load all Riboseq files
    all_counts = []
    ribo_parquet_files = glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
    for file in ribo_parquet_files:
        df_counts = process_parquet_file_gene_counts(file)
        df_counts["file_type"] = "Riboseq"
        all_counts.append(df_counts)

    # Load all mRNA files
    mrna_parquet_files = glob.glob(os.path.join(MRNA_FOLDER, "*.parquet"))
    for file in mrna_parquet_files:
        df_counts = process_mrna_file_gene_counts(file)
        df_counts["file_type"] = "mRNA"
        all_counts.append(df_counts)

    if not all_counts:
        return render(request, "riboApp/combinedPca.html", {"error_message": "No valid files found!"})

    gene_counts_df = pd.concat(all_counts, ignore_index=True)

    # Ensure gene names match in format
    gene_counts_df["gene_name"] = gene_counts_df["gene_name"].str.strip().str.lower()
    gene_lengths["gene_name"] = gene_lengths["gene_name"].str.strip().str.lower()

    # Merge with gene lengths
    gene_counts_df = pd.merge(gene_counts_df, gene_lengths, on="gene_name", how="left")
    gene_counts_df.dropna(subset=["length_kb"], inplace=True)
    gene_counts_df["length_kb"] = pd.to_numeric(gene_counts_df["length_kb"], errors="coerce")

    # Create a combined file identifier with type
    gene_counts_df["file_id"] = gene_counts_df["file_type"] + "_" + gene_counts_df["file_name"]

    # Pivot the DataFrame so that each file's gene counts are a separate column
    pivot_df = gene_counts_df.pivot_table(index="gene_name", columns="file_id", values="read_count", fill_value=0).reset_index()
    pivot_df = pivot_df.merge(gene_counts_df[["gene_name", "length_kb"]].drop_duplicates(), on="gene_name", how="left")
    pivot_df["length_kb"] = pd.to_numeric(pivot_df["length_kb"], errors="coerce")

    if pivot_df.empty:
        return render(request, "riboApp/combinedPca.html", {"error_message": "No valid gene count data after pivoting!"})

    # RPKM Normalization
    sample_cols = [col for col in pivot_df.columns if col not in ("gene_name", "length_kb")]
    for col in sample_cols:
        pivot_df[col] = (pivot_df[col] / pivot_df["length_kb"]) * 1e6 / pivot_df[col].sum()

    # Perform PCA
    pca = PCA(n_components=2)
    pca_results = pca.fit_transform(pivot_df[sample_cols].T)

    # Get explained variance ratios
    pc1_var = pca.explained_variance_ratio_[0] * 100
    pc2_var = pca.explained_variance_ratio_[1] * 100

    # Create PCA dataframe with file type information
    pca_df = pd.DataFrame({
        "PC1": pca_results[:, 0],
        "PC2": pca_results[:, 1],
        "file": sample_cols
    })
    pca_df["file_type"] = pca_df["file"].apply(lambda x: x.split("_")[0])

    # Generate the interactive PCA plot with color coding by file type
    fig = px.scatter(
        pca_df, x="PC1", y="PC2", hover_name="file", color="file_type",
        title=f"Combined PCA of Gene Counts (RPKM Normalized): Riboseq vs mRNA<br><sub>PC1: {pc1_var:.1f}% variance, PC2: {pc2_var:.1f}% variance</sub>",
        labels={"PC1": f"PC1 ({pc1_var:.1f}%)", "PC2": f"PC2 ({pc2_var:.1f}%)"},
        color_discrete_map={"Riboseq": "#1f77b4", "mRNA": "#ff7f0e"}
    )
    pca_plot_html = fig.to_html(full_html=False)

    # Cache the result (both persistent and in-memory)
    pca_plot_json = fig.to_json()
    set_persistent_cache(cache_key, pca_plot_json)  # 🚀 Persistent cache
    cache.set(cache_key, pca_plot_json, timeout=None)  # In-memory cache
    print("Stored combined PCA plot in both persistent and in-memory cache.")

    return render(request, "riboApp/combinedPca.html", {"pca_plot": pca_plot_html})


import os
import pandas as pd
# import matplotlib.pyplot as plt  # Temporarily disabled - too heavy for free tier
try:
    from ribopy import Ribo
except ImportError:
    Ribo = None
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse

# Define paths
RIBO_DIR = os.path.join(settings.MEDIA_ROOT, "ribo")
PSITE_OFFSETS_PATH = os.path.join(settings.MEDIA_ROOT, "uorf_psite_offset.csv")


def get_total_reads(ribo_obj):
    """Retrieve total read counts for each experiment in a .ribo file."""
    total_reads = {}

    for experiment in ribo_obj.experiments:  # Get list of experiments
        metadata = ribo_obj.get_metadata(experiment=experiment)

        if metadata is None:
            total_reads[experiment] = 0  # Default to 0 if no metadata
        else:
            total_reads[experiment] = metadata.get("total_reads", 0)

    return total_reads


def read_multiple_files(ribo_files, site, range_lower=28, range_upper=32):
    """Reads multiple .ribo files and extracts metagene data for each read length."""
    df_list = []

    for ribo_path in ribo_files:
        ribo_obj = Ribo(ribo_path)
        experiment_names = ribo_obj.experiments  # List of experiments

        for experiment in experiment_names:
            for read_length in range(range_lower, range_upper + 1):
                df = ribo_obj.get_metagene(
                    site_type=site,
                    experiments=[experiment],
                    range_lower=read_length,
                    range_upper=read_length,
                    sum_lengths=False,  # Keep per-read-length data
                    sum_references=False  # Keep per-transcript data
                )

                if df.empty:
                    print(f"No metagene data found for {experiment}, {site}, length {read_length}")
                    continue  # Skip empty data

                # Reset index to bring transcript and experiment into columns
                df = df.reset_index()

                # Ensure experiment name is retained
                df["experiment"] = experiment
                df["read_length"] = read_length

                # Convert wide format (-50, -49, ..., 0, 1, ..., 50) to long format
                df_melted = df.melt(id_vars=["experiment", "transcript", "read_length"],
                                    var_name="position",
                                    value_name="count")

                # Convert "position" column from string to integer
                df_melted["position"] = df_melted["position"].astype(int)

                df_list.append(df_melted)

    if not df_list:
        print("ERROR: No data collected from `read_multiple_files()`")

    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
def apply_psite_shift_and_average(metagene_data, psite_offsets, total_reads_dict):
    """Applies P-site shifts, averages counts, and normalizes by total reads."""

    if metagene_data.empty:
        return pd.DataFrame()

    # Ensure necessary columns exist
    expected_columns = {"experiment", "read_length", "position", "count"}
    missing_cols = expected_columns - set(metagene_data.columns)
    if missing_cols:
        print(metagene_data.head())  # Print first few rows for debugging
        return pd.DataFrame()

    # Merge with P-site offsets
    metagene_data = metagene_data.merge(psite_offsets, on=["experiment", "read_length"], how="left")

    # Merge with total reads
    total_reads_df = pd.DataFrame(list(total_reads_dict.items()), columns=["experiment", "total_reads"])
    metagene_data = metagene_data.merge(total_reads_df, on="experiment", how="left")

    # Apply P-site shifts
    metagene_data["shifted_position"] = metagene_data["position"] + metagene_data["P_site_offset"]
    metagene_data = metagene_data.dropna(subset=["shifted_position"])

    # Normalize read counts
    metagene_data["avg_count"] = (metagene_data["count"] / metagene_data["total_reads"]) * 1e6

    # Ensure "experiment" exists before returning
    if "experiment" not in metagene_data.columns:
        print("ERROR: 'experiment' column missing after processing!")
        return pd.DataFrame()

    return metagene_data.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].mean()


def plot_static_graph(data, title, x_label, y_label, filename, xlim=None, ylim=None):
    """Generates and saves a static matplotlib plot."""

    if data.empty:
        print(f"ERROR: Data is EMPTY for {title}")
        return None  # Return None to prevent further errors

    # Ensure necessary columns exist
    required_columns = {"experiment", "shifted_position", "avg_count"}
    missing_cols = required_columns - set(data.columns)
    if missing_cols:
        print(f"ERROR: Missing columns in data for {title}: {missing_cols}")
        print(data.head())
        return None

    plt.figure(figsize=(10, 5))

    # Define color scheme with correct color names
    color_palette = ["steelblue", "#FF1493", "darkviolet", "turquoise"]

    for i, (experiment, subset) in enumerate(data.groupby("experiment")):
        if subset.empty:
            print(f"WARNING: No data for experiment {experiment} in {title}")
            continue

        color = color_palette[i % len(color_palette)]  # Assign color
        plt.plot(subset["shifted_position"], subset["avg_count"], label=experiment, color=color)

    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.legend()
    plt.grid(True)

    if xlim:
        plt.xlim(xlim)
    if ylim:
        plt.ylim(ylim)

    plot_path = os.path.join(settings.MEDIA_ROOT, filename)
    plt.savefig(plot_path)
    plt.close()

    return plot_path

def process_ribo_files(request):
    """Main Django view to process .ribo files and return static plots."""
    # Load P-site offsets
    psite_offsets = pd.read_csv(PSITE_OFFSETS_PATH)
    psite_offsets.columns = ["experiment", "read_length", "P_site_offset"]

    # Get all .ribo files
    ribo_files = [os.path.join(RIBO_DIR, f) for f in os.listdir(RIBO_DIR) if f.endswith(".ribo")]

    if not ribo_files:
        return HttpResponse("No .ribo files found", status=400)

    # Create Ribo objects and retrieve total reads
    total_reads_dict = {}
    for ribo_path in ribo_files:
        ribo_obj = Ribo(ribo_path)
        total_reads_dict.update(get_total_reads(ribo_obj))

    # Process start codon metagene data
    start_data = read_multiple_files(ribo_files, site="start")
    start_shifted = apply_psite_shift_and_average(start_data, psite_offsets, total_reads_dict)

    # Process stop codon metagene data
    stop_data = read_multiple_files(ribo_files, site="stop")
    stop_shifted = apply_psite_shift_and_average(stop_data, psite_offsets, total_reads_dict)

    # Generate static matplotlib plots
    start_plot_path = plot_static_graph(start_shifted, "Start Codon Coverage After Shifts",
                                        "Shifted Position", "Normalized Read Count", "start_codon_plot.png",
                                        xlim=(-30, 62))

    stop_plot_path = plot_static_graph(stop_shifted, "Stop Codon Coverage After Shifts",
                                       "Shifted Position", "Normalized Read Count", "stop_codon_plot.png", xlim=(0, 20),
                                       ylim=(0, 50))

    return render(request, "riboApp/coverageGraphs.html", {"start_plot": start_plot_path, "stop_plot": stop_plot_path})

def _generate_metagene_cache_key(selected_files, selected_genes=None):
    """Generate a cache key for metagene plots based on selected files and genes"""
    import hashlib
    files_str = "_".join(sorted(selected_files))
    genes_str = "_".join(sorted(selected_genes)) if selected_genes else "all_genes"
    combined = f"{files_str}_{genes_str}"
    cache_hash = hashlib.md5(combined.encode()).hexdigest()
    return f"psite_metagene_{cache_hash}"


def psite_metagene_plots(request):
    """Generate P-site offset metagene plots for parquet files"""
    from .analysis.data_getters import get_available_parquet_files, load_selected_genes
    parquet_files = get_available_parquet_files()
    selected_genes = load_selected_genes()
    start_plot = None
    stop_plot = None
    error_message = None

    # Check if any files are available
    if not parquet_files:
        error_message = "No parquet files uploaded yet. Please upload preprocessed data files to begin analysis."

    if request.method == "POST":
        selected_files = request.POST.getlist("selected_files")
        use_selected_genes = request.POST.get("use_selected_genes") == "on"

        if not selected_files:
            error_message = "Please select at least one file."
        elif use_selected_genes and not selected_genes:
            error_message = "No genes selected. Please select genes first or uncheck 'Use Selected Genes Only'."
        else:
            try:
                # 🚀 Check persistent cache first
                genes_to_use = selected_genes if use_selected_genes else None
                cache_key = _generate_metagene_cache_key(selected_files, genes_to_use)

                cached_plots = get_persistent_cache(cache_key)
                if cached_plots is not None:
                    print(f"⚡ Loaded metagene plots from persistent cache")
                    start_plot, stop_plot = cached_plots
                else:
                    # Generate metagene plots
                    start_plot, stop_plot = generate_psite_metagene_plots(selected_files, genes_to_use)
                    # 💾 Save to persistent cache
                    set_persistent_cache(cache_key, (start_plot, stop_plot))
                    print(f"💾 Saved metagene plots to persistent cache")
            except Exception as e:
                error_message = f"Error generating plots: {str(e)}"



    return render(request, "riboApp/psiteMetagene.html", {
        "parquet_files": parquet_files,
        "selected_genes": selected_genes,
        "selected_genes_count": len(selected_genes),
        "start_plot": start_plot,
        "stop_plot": stop_plot,
        "error_message": error_message,
    })

def generate_psite_metagene_plots(selected_files, selected_genes=None):
    """Generate start and stop codon metagene plots with P-site offsets"""
    from .analysis.data_getters import get_cached_psite_data, get_cached_file_metadata

    # Load P-site offsets
    if not os.path.exists(OFFSET_CSV):
        raise ValueError("P-site offset CSV file not found!")

    offsets_df = pd.read_csv(OFFSET_CSV)
    offsets_df.columns = ["experiment", "read_length", "P_site_offset"]

    # Process each selected file
    all_start_data = []
    all_stop_data = []

    for file in selected_files:
        file_basename = os.path.splitext(file)[0]
        file_path = os.path.join(PARQUET_FOLDER, file)

        # Get P-site offsets for this experiment
        file_offsets = offsets_df[offsets_df["experiment"] == file_basename]
        if file_offsets.empty:
            print(f"Warning: No P-site offsets found for {file_basename}")
            continue

        # 🚀 Try to use cached P-site data first (much faster!)
        df = get_cached_psite_data(file)

        if df.empty:
            print(f"⚠️ P-site cache miss for {file}, reading parquet file...")
            # Fallback: Read parquet file
            df = pq.read_table(file_path, columns=[
                "gene_name", "start_position", "end_position", "read_length", "read_count", "region"
            ]).to_pandas()

            # Filter for CDS regions only (where ribosomes should be)
            df = df[df["region"] == "CDS"]
        else:
            print(f"⚡ Using cached P-site data for {file}")

        if df.empty:
            print(f"Warning: No CDS data found in {file}")
            continue

        # Get total reads from metadata cache if available
        metadata = get_cached_file_metadata(file)
        total_reads = metadata.get('total_reads', df["read_count"].sum())

        # 🚀 OPTIMIZATION: Process BOTH start and stop in a single pass through the data
        # This avoids processing the same dataframe twice
        start_data, stop_data = process_metagene_data_both_sites(df, file_offsets, file_basename, total_reads, selected_genes)

        if not start_data.empty:
            all_start_data.append(start_data)
        if not stop_data.empty:
            all_stop_data.append(stop_data)

    if not all_start_data and not all_stop_data:
        raise ValueError("No valid data found for selected files")

    # Combine data from all files
    combined_start = pd.concat(all_start_data, ignore_index=True) if all_start_data else pd.DataFrame()
    combined_stop = pd.concat(all_stop_data, ignore_index=True) if all_stop_data else pd.DataFrame()

    # Generate plots
    start_plot_html = None
    stop_plot_html = None

    if not combined_start.empty:
        start_plot_html = create_metagene_plot(
            combined_start,
            "Start Codon Coverage After P-site Shifts",
            xlim=(-30, 62)
        )

    if not combined_stop.empty:
        # Let the stop codon plot auto-scale its y-axis
        stop_plot_html = create_metagene_plot(
            combined_stop,
            "Stop Codon Coverage After P-site Shifts",
            xlim=(-2, 60)
        )

    return start_plot_html, stop_plot_html

def process_metagene_data_both_sites(df, file_offsets, experiment_name, total_reads, selected_genes=None):
    """Process BOTH start and stop codon data in a single pass - OPTIMIZED

    This is much faster than calling process_metagene_data twice because we only
    process the dataframe once instead of twice.
    """

    # Filter by selected genes if provided
    if selected_genes:
        df = df[df["gene_name"].isin(selected_genes)]
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

    # Create offset mapping
    length_to_offset = dict(zip(file_offsets["read_length"], file_offsets["P_site_offset"]))

    # Filter for read lengths 28-32 (typical ribosome footprint sizes)
    df_filtered = df[df["read_length"].between(28, 32)].copy()

    if df_filtered.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Apply P-site offsets
    df_filtered["offset"] = df_filtered["read_length"].map(length_to_offset)
    df_filtered = df_filtered.dropna(subset=["offset"])
    df_filtered["p_site"] = df_filtered["start_position"] + df_filtered["offset"].astype(int)

    # Pre-calculate reference positions for all genes at once
    start_reference_positions = df_filtered.groupby("gene_name")["p_site"].min()
    # For stop codon: use 95th percentile of P-site positions (where stop codon is likely located)
    stop_reference_positions = df_filtered.groupby("gene_name")["p_site"].quantile(0.95)

    # Filter genes with at least 10 reads
    gene_read_counts = df_filtered.groupby("gene_name").size()
    valid_genes = gene_read_counts[gene_read_counts >= 10].index

    df_filtered = df_filtered[df_filtered["gene_name"].isin(valid_genes)].copy()
    start_reference_positions = start_reference_positions[valid_genes]
    stop_reference_positions = stop_reference_positions[valid_genes]

    if df_filtered.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 🚀 PROCESS START CODON DATA
    start_position_range = range(-30, 63)
    df_start = df_filtered.copy()
    df_start["relative_position"] = df_start.apply(
        lambda row: row["p_site"] - start_reference_positions[row["gene_name"]], axis=1
    )
    df_start = df_start[df_start["relative_position"].isin(start_position_range)]
    start_position_counts = df_start.groupby("relative_position")["read_count"].sum()

    start_metagene_data = []
    for pos, count in start_position_counts.items():
        if count > 0:
            start_metagene_data.append({
                "experiment": experiment_name,
                "shifted_position": pos,
                "avg_count": (count / total_reads) * 1e6,  # Normalize to RPM
            })

    start_metagene_df = pd.DataFrame(start_metagene_data) if start_metagene_data else pd.DataFrame()

    # 🚀 PROCESS STOP CODON DATA
    stop_position_range = range(-10, 31)
    df_stop = df_filtered.copy()
    # For stop codon: calculate relative position as (stop_position - p_site)
    # This gives negative values upstream and positive values downstream of stop
    df_stop["relative_position"] = df_stop.apply(
        lambda row: stop_reference_positions[row["gene_name"]] - row["p_site"], axis=1
    )
    df_stop = df_stop[df_stop["relative_position"].isin(stop_position_range)]
    stop_position_counts = df_stop.groupby("relative_position")["read_count"].sum()

    stop_metagene_data = []
    for pos, count in stop_position_counts.items():
        if count > 0:
            stop_metagene_data.append({
                "experiment": experiment_name,
                "shifted_position": pos,
                "avg_count": (count / total_reads) * 1e6,  # Normalize to RPM
            })

    stop_metagene_df = pd.DataFrame(stop_metagene_data) if stop_metagene_data else pd.DataFrame()

    return start_metagene_df, stop_metagene_df


def process_metagene_data(df, file_offsets, experiment_name, total_reads, site_type, selected_genes=None):
    """Process parquet data to create metagene coverage around start/stop codons - OPTIMIZED

    Note: Parquet files use transcript coordinates (not genomic coordinates).
    For stop codon analysis, we find the CDS end boundary for each gene.
    """

    # Filter by selected genes if provided
    if selected_genes:
        df = df[df["gene_name"].isin(selected_genes)]
        if df.empty:
            return pd.DataFrame()

    # Create offset mapping
    length_to_offset = dict(zip(file_offsets["read_length"], file_offsets["P_site_offset"]))

    # Filter for read lengths 28-32 (typical ribosome footprint sizes)
    df_filtered = df[df["read_length"].between(28, 32)].copy()

    if df_filtered.empty:
        return pd.DataFrame()

    # Apply P-site offsets
    df_filtered["offset"] = df_filtered["read_length"].map(length_to_offset)
    df_filtered = df_filtered.dropna(subset=["offset"])
    df_filtered["p_site"] = df_filtered["start_position"] + df_filtered["offset"].astype(int)

    # 🚀 MAJOR OPTIMIZATION: Pre-calculate reference positions for all genes at once
    if site_type == "start":
        # For start codon: use minimum P-site position per gene
        reference_positions = df_filtered.groupby("gene_name")["p_site"].min()
        position_range = range(-30, 63)
    else:  # stop
        # For stop codon: use 95th percentile of P-site positions per gene
        # This represents where the stop codon is likely located
        reference_positions = df_filtered.groupby("gene_name")["p_site"].quantile(0.95)
        position_range = range(-10, 31)

    # Filter genes with at least 10 reads
    gene_read_counts = df_filtered.groupby("gene_name").size()
    valid_genes = gene_read_counts[gene_read_counts >= 10].index

    df_filtered = df_filtered[df_filtered["gene_name"].isin(valid_genes)].copy()
    reference_positions = reference_positions[valid_genes]

    if df_filtered.empty:
        return pd.DataFrame()

    # 🚀 VECTORIZED: Calculate relative positions for ALL genes at once
    if site_type == "start":
        # For start codon: p_site - start_position (positive downstream)
        df_filtered["relative_position"] = df_filtered.apply(
            lambda row: row["p_site"] - reference_positions[row["gene_name"]], axis=1
        )
    else:  # stop
        # For stop codon: stop_position - p_site (positive upstream, negative downstream)
        df_filtered["relative_position"] = df_filtered.apply(
            lambda row: reference_positions[row["gene_name"]] - row["p_site"], axis=1
        )

    # 🚀 VECTORIZED: Filter to position range and aggregate in one step
    df_filtered = df_filtered[df_filtered["relative_position"].isin(position_range)]

    # Aggregate by position across all genes
    position_counts = df_filtered.groupby("relative_position")["read_count"].sum()

    # Convert to metagene format
    metagene_data = []
    for pos, count in position_counts.items():
        if count > 0:
            metagene_data.append({
                "experiment": experiment_name,
                "shifted_position": pos,
                "avg_count": (count / total_reads) * 1e6,  # Normalize to RPM
            })

    if not metagene_data:
        return pd.DataFrame()

    # Convert to DataFrame
    metagene_df = pd.DataFrame(metagene_data)

    # DEBUG: Print sample of metagene data before aggregation
    print(f"\n🔍 DEBUG process_metagene_data - site_type={site_type}, experiment={experiment_name}")
    print(f"  Total genes processed: {len(valid_genes)}")
    print(f"  Total data points: {len(metagene_df)}")
    if not metagene_df.empty:
        print(f"  Position range: {metagene_df['shifted_position'].min()} to {metagene_df['shifted_position'].max()}")

    if selected_genes:
        # When using selected genes, combine all genes into a single line per experiment
        # Sum the counts across all selected genes for each position
        result = metagene_df.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].sum()
        # Add a label to indicate this is selected genes
        result["experiment"] = result["experiment"] + " (Selected Genes)"
    else:
        # Sum across all genes for each position and experiment
        # This is the correct way to do metagene analysis - sum the normalized counts
        result = metagene_df.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].sum()

    return result

def create_metagene_plot(data, title, xlim=None, ylim=None):
    """Create interactive metagene plot using Plotly"""

    if data.empty:
        return "<p>No data available for plotting</p>"

    # Define custom colors (using valid CSS color names)
    custom_colors = ["steelblue", "mediumvioletred", "darkviolet", "turquoise"]

    fig = px.line(
        data,
        x="shifted_position",
        y="avg_count",
        color="experiment",
        title=title,
        labels={
            "shifted_position": "Shifted Position",
            "avg_count": "Normalized Read Count (RPM)"
        },
        color_discrete_sequence=custom_colors
    )

    # Apply axis limits if specified
    if xlim:
        fig.update_xaxes(range=xlim)
    if ylim:
        fig.update_yaxes(range=ylim)

    fig.update_layout(
        template="plotly_white",
        hovermode="x unified"
    )

    return fig.to_html(full_html=False)


def download_csv(request, analysis_type):
    """General CSV download function for different analysis types"""

    if analysis_type == "gene_counts":
        return download_gene_counts_csv(request)
    elif analysis_type == "combined_gene_counts":
        return download_combined_gene_counts_csv(request)
    elif analysis_type == "pca":
        return download_pca_csv(request)
    elif analysis_type == "combined_pca":
        return download_combined_pca_csv(request)
    elif analysis_type == "psite_metagene_start":
        return download_psite_metagene_csv(request, "start")
    elif analysis_type == "psite_metagene_stop":
        return download_psite_metagene_csv(request, "stop")
    elif analysis_type == "bin_counts":
        return download_bin_counts_csv(request)
    elif analysis_type == "read_length":
        return download_read_length_csv(request)
    elif analysis_type == "delta_analysis":
        return download_delta_analysis_csv(request)
    else:
        return HttpResponse("Invalid analysis type", status=400)


def download_gene_counts_csv(request):
    """Download CSV for gene counts scatter plot"""
    file1 = request.GET.get("file1")
    file2 = request.GET.get("file2")

    if not file1 or not file2:
        return HttpResponse("Missing file parameters", status=400)

    df = get_gene_counts(file1, file2)

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="gene_counts_{file1}_vs_{file2}.csv"'

    df.to_csv(response, index=False)
    return response


def download_combined_gene_counts_csv(request):
    """Download CSV for combined gene counts (riboseq vs mRNA)"""
    ribo_file = request.GET.get("ribo_file")
    mrna_file = request.GET.get("mrna_file")

    if not ribo_file or not mrna_file:
        return HttpResponse("Missing file parameters", status=400)

    df = get_combined_gene_counts(ribo_file, mrna_file)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="combined_gene_counts_{ribo_file}_vs_{mrna_file}.csv"'

    df.to_csv(response, index=False)
    return response


def download_delta_analysis_csv(request):
    """Download CSV for delta analysis"""
    ribo_file1 = request.GET.get("ribo_file1")
    ribo_file2 = request.GET.get("ribo_file2")
    mrna_file1 = request.GET.get("mrna_file1")
    mrna_file2 = request.GET.get("mrna_file2")

    if not all([ribo_file1, ribo_file2, mrna_file1, mrna_file2]):
        return HttpResponse("Missing file parameters", status=400)

    df = get_delta_analysis_data(ribo_file1, ribo_file2, mrna_file1, mrna_file2)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="delta_analysis_{ribo_file1}_vs_{ribo_file2}_and_{mrna_file1}_vs_{mrna_file2}.csv"'

    df.to_csv(response, index=False)
    return response


def download_pca_csv(request):
    """Download CSV for PCA analysis"""
    # Regenerate PCA data
    gene_lengths = calculate_gene_lengths(GTF_FILE)
    if gene_lengths.empty:
        return HttpResponse("No gene lengths available", status=400)

    parquet_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")
    ])

    if not parquet_files:
        return HttpResponse("No parquet files found", status=400)

    # Process files and create PCA data
    all_data = []
    for file in parquet_files:
        file_path = os.path.join(PARQUET_FOLDER, file)
        df = pq.read_table(file_path, columns=["gene_name", "read_count"]).to_pandas()
        df = df.groupby("gene_name", as_index=False)["read_count"].sum()
        df["file_name"] = os.path.basename(file)
        all_data.append(df)

    combined_df = pd.concat(all_data, ignore_index=True)
    pivot_df = combined_df.pivot(index="gene_name", columns="file_name", values="read_count").fillna(0)

    # Merge with gene lengths and calculate RPKM
    pivot_df = pivot_df.merge(gene_lengths, left_index=True, right_on="gene_name", how="inner")
    pivot_df.set_index("gene_name", inplace=True)

    sample_cols = [col for col in pivot_df.columns if col != "length_kb"]
    for col in sample_cols:
        pivot_df[col] = (pivot_df[col] * 1e9) / (pivot_df["length_kb"] * pivot_df[sample_cols].sum().sum())

    # Perform PCA
    from sklearn.decomposition import PCA
    pca = PCA(n_components=2)
    pca_results = pca.fit_transform(pivot_df[sample_cols].T)
    pca_df = pd.DataFrame({
        "PC1": pca_results[:, 0],
        "PC2": pca_results[:, 1],
        "file": sample_cols,
        "explained_variance_PC1": pca.explained_variance_ratio_[0],
        "explained_variance_PC2": pca.explained_variance_ratio_[1]
    })

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pca_analysis.csv"'

    pca_df.to_csv(response, index=False)
    return response


def download_combined_pca_csv(request):
    """Download CSV for combined PCA analysis (riboseq + mRNA)"""
    gene_lengths = calculate_gene_lengths(GTF_FILE)
    if gene_lengths.empty:
        return HttpResponse("No gene lengths available", status=400)

    # Get both riboseq and mRNA files
    ribo_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")
    ])
    mrna_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(MRNA_FOLDER, "*.parquet"))
        if not os.path.basename(f).startswith(".")
    ])

    all_data = []

    # Process riboseq files
    for file in ribo_files:
        file_path = os.path.join(PARQUET_FOLDER, file)
        df = pq.read_table(file_path, columns=["gene_name", "read_count"]).to_pandas()
        df = df.groupby("gene_name", as_index=False)["read_count"].sum()
        df["file_name"] = f"Riboseq_{os.path.basename(file)}"
        all_data.append(df)

    # Process mRNA files
    for file in mrna_files:
        file_path = os.path.join(MRNA_FOLDER, file)
        df = pq.read_table(file_path, columns=["gene_name", "read_count"]).to_pandas()
        df = df.groupby("gene_name", as_index=False)["read_count"].sum()
        df["file_name"] = f"mRNA_{os.path.basename(file)}"
        all_data.append(df)

    if not all_data:
        return HttpResponse("No data files found", status=400)

    combined_df = pd.concat(all_data, ignore_index=True)
    pivot_df = combined_df.pivot(index="gene_name", columns="file_name", values="read_count").fillna(0)

    # Merge with gene lengths and calculate RPKM
    pivot_df = pivot_df.merge(gene_lengths, left_index=True, right_on="gene_name", how="inner")
    pivot_df.set_index("gene_name", inplace=True)

    sample_cols = [col for col in pivot_df.columns if col != "length"]
    for col in sample_cols:
        pivot_df[col] = (pivot_df[col] * 1e9) / (pivot_df["length"] * pivot_df[sample_cols].sum().sum())

    # Perform PCA
    from sklearn.decomposition import PCA
    pca = PCA(n_components=2)
    pca_results = pca.fit_transform(pivot_df[sample_cols].T)

    pca_df = pd.DataFrame({
        "PC1": pca_results[:, 0],
        "PC2": pca_results[:, 1],
        "file": sample_cols,
        "file_type": [f.split("_")[0] for f in sample_cols],
        "explained_variance_PC1": pca.explained_variance_ratio_[0],
        "explained_variance_PC2": pca.explained_variance_ratio_[1]
    })

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="combined_pca_analysis.csv"'

    pca_df.to_csv(response, index=False)
    return response


def download_psite_metagene_csv(request, plot_type):
    """Download CSV for P-site metagene plots"""
    from .analysis.data_getters import get_cached_psite_data, get_cached_file_metadata

    selected_files = request.GET.getlist("selected_files")
    use_selected_genes = request.GET.get("use_selected_genes") == "true"

    if not selected_files:
        return HttpResponse("No files selected", status=400)

    # Load selected genes if needed
    selected_genes = None
    if use_selected_genes:
        selected_genes = [gene.gene_name for gene in SelectedGene.objects.all()]
        if not selected_genes:
            return HttpResponse("No genes selected", status=400)

    # Generate the data (same as in the plot generation)
    try:
        start_plot_html, stop_plot_html = generate_psite_metagene_plots(selected_files, selected_genes)

        # We need to regenerate the data for CSV export
        # Load P-site offsets
        if not os.path.exists(OFFSET_CSV):
            return HttpResponse("P-site offset CSV file not found", status=400)

        offsets_df = pd.read_csv(OFFSET_CSV)
        offsets_df.columns = ["experiment", "read_length", "P_site_offset"]

        # Process each selected file
        all_start_data = []
        all_stop_data = []

        for selected_file in selected_files:
            file_path = os.path.join(PARQUET_FOLDER, selected_file)
            if not os.path.exists(file_path):
                continue

            experiment_name = os.path.splitext(selected_file)[0]
            file_offsets = offsets_df[offsets_df["experiment"] == experiment_name]

            if file_offsets.empty:
                continue

            # 🚀 Try to use cached P-site data first
            df = get_cached_psite_data(selected_file)

            if df.empty:
                print(f"⚠️ P-site cache miss for CSV export, reading parquet file...")
                df = pq.read_table(file_path).to_pandas()
            else:
                print(f"⚡ Using cached P-site data for CSV export: {selected_file}")

            # Get total reads from metadata cache if available
            metadata = get_cached_file_metadata(selected_file)
            total_reads = metadata.get('total_reads', df["read_count"].sum())

            # Process start codon data
            start_data = process_metagene_data(df, file_offsets, experiment_name, total_reads, "start", selected_genes)
            if not start_data.empty:
                all_start_data.append(start_data)

            # Process stop codon data
            stop_data = process_metagene_data(df, file_offsets, experiment_name, total_reads, "stop", selected_genes)
            if not stop_data.empty:
                all_stop_data.append(stop_data)

        # Combine data
        if plot_type == "start" and all_start_data:
            combined_data = pd.concat(all_start_data, ignore_index=True)
            filename = "psite_metagene_start_codon.csv"
        elif plot_type == "stop" and all_stop_data:
            combined_data = pd.concat(all_stop_data, ignore_index=True)
            filename = "psite_metagene_stop_codon.csv"
        else:
            return HttpResponse("No data available for the requested plot type", status=400)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        combined_data.to_csv(response, index=False)
        return response

    except Exception as e:
        return HttpResponse(f"Error generating CSV: {str(e)}", status=500)


def download_bin_counts_csv(request):
    """Download CSV for bin counts analysis"""
    selected_file = request.GET.get("selected_file")

    if not selected_file:
        return HttpResponse("No file selected", status=400)

    # Generate bin counts data (reuse existing function)
    plots, error_message = get_bin_counts(selected_file)

    if error_message:
        return HttpResponse(f"Error: {error_message}", status=400)

    # Extract data from the plots (this is a simplified approach)
    # In a real implementation, you'd want to store the data separately
    file_path = os.path.join(PARQUET_FOLDER, selected_file)
    df = pq.read_table(file_path).to_pandas()

    # Create summary statistics
    summary_data = df.groupby(['region', 'read_length']).agg({
        'read_count': ['sum', 'mean', 'count']
    }).reset_index()

    # Flatten column names
    summary_data.columns = ['region', 'read_length', 'total_reads', 'mean_reads', 'num_positions']

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="bin_counts_{selected_file}.csv"'

    summary_data.to_csv(response, index=False)
    return response


def download_read_length_csv(request):
    """Download CSV for read length distribution"""
    selected_file = request.GET.get("selected_file")

    if not selected_file:
        return HttpResponse("No file selected", status=400)

    file_path = os.path.join(PARQUET_FOLDER, selected_file)
    if not os.path.exists(file_path):
        return HttpResponse("File not found", status=400)

    df = pq.read_table(file_path, columns=["read_length", "read_count"]).to_pandas()

    # Group by read length and sum counts
    read_length_data = df.groupby("read_length")["read_count"].sum().reset_index()
    read_length_data.columns = ["read_length", "total_count"]

    # Calculate percentages
    total_reads = read_length_data["total_count"].sum()
    read_length_data["percentage"] = (read_length_data["total_count"] / total_reads) * 100

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="read_length_distribution_{selected_file}.csv"'

    read_length_data.to_csv(response, index=False)
    return response


# ============================================================================
# PERFORMANCE OPTIMIZATION: PREPROCESSING CACHE SYSTEM
# ============================================================================

def create_file_preprocessing_cache(file_path, file_type="riboseq"):
    """
    Create comprehensive preprocessing cache for uploaded files.
    This dramatically speeds up all subsequent analyses.
    """
    print(f"Creating preprocessing cache for {file_path}")
    start_time = time.time()

    filename = os.path.basename(file_path)
    cache_key_base = f"preprocess_{file_type}_{filename}"

    try:
        # Read the full parquet file once
        df = pq.read_table(file_path).to_pandas()
        print(f"Loaded {len(df)} rows from {filename}")

        # Cache 1: Basic gene counts (most common operation)
        gene_counts = df.groupby("gene_name")["read_count"].sum().reset_index()
        gene_counts.columns = ["gene_name", "total_count"]
        gene_counts_data = gene_counts.to_dict('records')
        from riboApp.analysis.data_getters import _save_persistent_cache
        _save_persistent_cache(f"{cache_key_base}_gene_counts", gene_counts_data)  # 🚀 Persistent
        cache.set(f"{cache_key_base}_gene_counts", gene_counts_data, timeout=None)

        # Cache 2: Read length distribution
        read_length_dist = df.groupby("read_length")["read_count"].sum().reset_index()
        read_length_data = read_length_dist.to_dict('records')
        _save_persistent_cache(f"{cache_key_base}_read_length", read_length_data)  # 🚀 Persistent
        cache.set(f"{cache_key_base}_read_length", read_length_data, timeout=None)

        # Cache 3: Region-based statistics
        if 'region' in df.columns:
            region_stats = df.groupby(['region', 'read_length']).agg({
                'read_count': ['sum', 'mean', 'count']
            }).reset_index()
            region_stats.columns = ['region', 'read_length', 'total_reads', 'mean_reads', 'num_positions']
            region_stats_data = region_stats.to_dict('records')
            _save_persistent_cache(f"{cache_key_base}_region_stats", region_stats_data)  # 🚀 Persistent
            cache.set(f"{cache_key_base}_region_stats", region_stats_data, timeout=None)

            # Cache 3b: CDS-only gene counts (for fast CDS-only analysis)
            cds_df = df[df['region'] == 'CDS']
            if not cds_df.empty:
                cds_gene_counts = cds_df.groupby("gene_name")["read_count"].sum().reset_index()
                cds_gene_counts.columns = ["gene_name", "cds_count"]
                cds_data = cds_gene_counts.to_dict('records')
                _save_persistent_cache(f"{cache_key_base}_cds_gene_counts", cds_data)  # 🚀 Persistent
                cache.set(f"{cache_key_base}_cds_gene_counts", cds_data, timeout=None)
                print(f"Cached CDS-only gene counts for {len(cds_gene_counts)} genes")

        # Cache 4: For riboseq files - P-site ready data
        if file_type == "riboseq" and all(col in df.columns for col in ['start_position', 'gene_name', 'region']):
            # Pre-filter for CDS regions and typical read lengths
            # Make sure we have all required columns for metagene analysis
            required_cols = ['gene_name', 'start_position', 'read_length', 'read_count', 'region']
            if 'end_position' in df.columns:
                required_cols.append('end_position')

            cds_df = df[(df['region'] == 'CDS') & (df['read_length'].between(28, 32))].copy()
            if not cds_df.empty:
                # Only cache the columns we need
                cds_cache_data = cds_df[required_cols].to_dict('records')
                _save_persistent_cache(f"{cache_key_base}_cds_data", cds_cache_data)  # 🚀 Persistent
                cache.set(f"{cache_key_base}_cds_data", cds_cache_data, timeout=None)

                # Cache 4b: Pre-calculate metagene data if P-site offsets are available
                try:
                    if os.path.exists(OFFSET_CSV):
                        offsets_df = pd.read_csv(OFFSET_CSV)
                        offsets_df.columns = ["experiment", "read_length", "P_site_offset"]
                        experiment_name = os.path.splitext(filename)[0]
                        file_offsets = offsets_df[offsets_df["experiment"] == experiment_name]

                        if not file_offsets.empty:
                            # Pre-calculate P-site positions
                            length_to_offset = dict(zip(file_offsets["read_length"], file_offsets["P_site_offset"]))
                            cds_df["offset"] = cds_df["read_length"].map(length_to_offset)
                            cds_df = cds_df.dropna(subset=["offset"])
                            cds_df["p_site"] = cds_df["start_position"] + cds_df["offset"].astype(int)

                            # Cache the P-site enhanced data
                            psite_data = cds_df.to_dict('records')
                            _save_persistent_cache(f"{cache_key_base}_psite_data", psite_data)  # 🚀 Persistent
                            cache.set(f"{cache_key_base}_psite_data", psite_data, timeout=None)
                            print(f"📍 Pre-calculated P-site data for {filename}")
                except Exception as e:
                    print(f"⚠️ Could not pre-calculate P-site data for {filename}: {str(e)}")
                    pass

        # Cache 5: Basic file metadata
        file_metadata = {
            'total_reads': int(df['read_count'].sum()),
            'unique_genes': int(df['gene_name'].nunique()),
            'read_length_range': [int(df['read_length'].min()), int(df['read_length'].max())],
            'regions': list(df['region'].unique()) if 'region' in df.columns else [],
            'cached_at': time.time()
        }
        _save_persistent_cache(f"{cache_key_base}_metadata", file_metadata)  # 🚀 Persistent
        cache.set(f"{cache_key_base}_metadata", file_metadata, timeout=None)

        processing_time = time.time() - start_time
        print(f"Preprocessing cache created in {processing_time:.2f}s for {filename}")

        return True

    except Exception as e:
        print(f"Error creating preprocessing cache for {filename}: {str(e)}")
        return False








def preprocess_all_uploaded_files():
    """
    Preprocess all uploaded files to create caches.
    Call this when files are uploaded or as a maintenance task.
    """
    print("🔄 Starting bulk preprocessing of all uploaded files...")

    # Process riboseq files
    ribo_files = glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
    for file_path in ribo_files:
        if not os.path.basename(file_path).startswith('.'):
            create_file_preprocessing_cache(file_path, "riboseq")

    # Process mRNA files
    mrna_files = glob.glob(os.path.join(MRNA_FOLDER, "*.parquet"))
    for file_path in mrna_files:
        if not os.path.basename(file_path).startswith('.'):
            create_file_preprocessing_cache(file_path, "mrna")

    print("Bulk preprocessing completed!")


def update_psite_caches():
    """Update existing caches with P-site enhanced data"""
    from .analysis.data_getters import get_cached_psite_data
    print("🔄 Updating P-site caches for existing files...")

    ribo_files = glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
    for file_path in ribo_files:
        if not os.path.basename(file_path).startswith('.'):
            filename = os.path.basename(file_path)

            # Check if we already have P-site cache
            psite_cache = get_cached_psite_data(filename)
            if psite_cache.empty:
                print(f"🔄 Updating P-site cache for {filename}")
                create_file_preprocessing_cache(file_path, "riboseq")
            else:
                print(f"✅ P-site cache already exists for {filename}")

    print("✅ P-site cache update completed!")


def clear_file_cache(filename, file_type="riboseq"):
    """Clear all cached data for a specific file"""
    cache_key_base = f"preprocess_{file_type}_{filename}"
    cache_keys = [
        f"{cache_key_base}_gene_counts",
        f"{cache_key_base}_read_length",
        f"{cache_key_base}_region_stats",
        f"{cache_key_base}_cds_data",
        f"{cache_key_base}_metadata"
    ]

    for key in cache_keys:
        cache.delete(key)

    print(f"Cleared cache for {filename}")


def preprocess_all_files_view(request):
    """View to trigger preprocessing of all uploaded files AND preload all data"""
    if request.method == "POST":
        try:
            # Import the new data loader
            from .analysis import data_loader

            # Step 1: Preload ALL raw data (caches GTF/FASTA only)
            # This is fast: ~45 seconds
            data_loader.preload_all_data()

            # REMOVED: precompute_all_analyses()
            # We don't precompute all analyses anymore!
            # Instead, analyses are computed on-demand when user requests plots.
            # This keeps preprocessing fast (45 seconds instead of 15+ minutes).

            # Also trigger old preprocessing for compatibility
            preprocess_all_uploaded_files()

            messages.success(request, "All files have been preprocessed! GTF data is cached. Analyses will be computed on-demand when you generate plots.")
        except Exception as e:
            messages.error(request, f"Error during preprocessing: {str(e)}")
            import traceback
            traceback.print_exc()

    return redirect('upload_parquet')


def update_psite_caches_view(request):
    """View to trigger P-site cache updates"""
    if request.method == "POST":
        try:
            update_psite_caches()
            messages.success(request, "P-site caches have been updated successfully! Metagene analysis should now be much faster.")
        except Exception as e:
            messages.error(request, f"Error updating P-site caches: {str(e)}")

    return redirect('upload_parquet')


def clear_delta_analysis_cache_view(request):
    """View to clear delta analysis cached plots only"""
    if request.method == "POST":
        try:
            from .analysis.data_getters import clear_delta_analysis_cache
            clear_delta_analysis_cache()
            messages.success(request, "Delta analysis cache has been cleared.")
        except Exception as e:
            messages.error(request, f"Error clearing delta analysis cache: {str(e)}")

    return redirect('delta_analysis')


def clear_all_cache_view(request):
    """View to clear all preprocessing caches"""
    if request.method == "POST":
        try:
            # Clear all cache keys that start with "preprocess_"
            from django.core.cache import cache
            cache.clear()  # This clears all cache - you might want to be more selective
            messages.success(request, "All preprocessing caches have been cleared.")
        except Exception as e:
            messages.error(request, f"Error clearing cache: {str(e)}")

    return redirect('upload_parquet')