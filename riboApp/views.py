from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect, Http404
from .models import ProcessingInput
from .forms import CreateNewList
import mimetypes
import yaml
from .forms import ParquetUploadForm, MrnaParquetUploadForm, BulkParquetUploadForm, BulkMrnaParquetUploadForm
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
import json
import re
from sklearn.decomposition import PCA
import glob
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from ribopy import Ribo
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



def reformatFilepaths(file_content):
    """
    Reformats the user-provided file content into YAML-compatible structure.
    """
    yaml_data = {
        "fastq_base": "",
        "fastq": {}
    }

    for line in file_content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            # format: "experiment_name /path/to/file"
            experiment_name, filepath = line.split(' ', 1)
        except ValueError:
            raise ValueError(f"Line '{line}' is not formatted as 'experiment_name /path/to/file'.")
        if experiment_name not in yaml_data["fastq"]:
            yaml_data["fastq"][experiment_name] = []
        yaml_data["fastq"][experiment_name].append(filepath)

    return yaml.dump(yaml_data, default_flow_style=False)


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

            ProcessingInput.objects.create(
                experimentName=experimentName,
                adapter=adapter,
                sampleFile=sampleFile,
                humanGenome=humanGenome,
                mouseGenome=mouseGenome,
                useBarcode=useBarcode
            )

            # Read the contents of the uploaded sample file
            sample_file_content = sampleFile.read().decode('utf-8')

            # Process the sample file content: assuming "name (space) sample filepath" per line
            sample_data = []
            for line in sample_file_content.splitlines():
                if line.strip():  # Ignore empty lines
                    parts = line.split(' ', 1)  # Split at the first space
                    if len(parts) == 2:
                        sample_data.append((parts[0], parts[1]))  # (name, filepath)

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

            OGfilePaths = sampleFile.read().decode("utf-8")
            filePaths = reformatFilepaths(OGfilePaths)

            myScriptPath = os.path.join(os.path.dirname(__file__), 'scripts', 'outputScript.sh')
            if not os.path.exists(myScriptPath):
                raise Http404(f"Script file not found at {myScriptPath}")
            with open(myScriptPath, 'r') as template_file:
                scriptContent = template_file.read()

            # Generate barcode-specific clip arguments
            if useBarcode:
                clip_arguments = f'-u 1 -a {adapter} --overlap=4 --trimmed-only --maximum-length=40 --minimum-length=15 --quality-cutoff=28 --discard-untrimmed'
                barcode_comment = "# Barcode demultiplexing enabled - adapter trimming with barcode removal"
            else:
                clip_arguments = f'-u 1 -a {adapter} --overlap=4 --trimmed-only --maximum-length=40 --minimum-length=15 --quality-cutoff=28'
                barcode_comment = "# Standard adapter trimming without barcode demultiplexing"

            scriptContent = scriptContent.replace("{filter}", filter)
            scriptContent = scriptContent.replace("{genome}", genome)
            scriptContent = scriptContent.replace("{transcriptome}", transcriptome)
            scriptContent = scriptContent.replace("{regions}", regions)
            scriptContent = scriptContent.replace("{transcriptLengths}", transcriptLengths)
            scriptContent = scriptContent.replace("{experimentName}", experimentName)
            scriptContent = scriptContent.replace("{filePaths}", filePaths)
            scriptContent = scriptContent.replace("{clipArguments}", clip_arguments)
            scriptContent = scriptContent.replace("{barcodeComment}", barcode_comment)

            output_dir = os.path.join('media', 'generated_scripts')
            os.makedirs(output_dir, exist_ok=True)

            clean_experiment_name = experimentName.replace(" ", "")
            script_file_path = os.path.join(output_dir, f"{clean_experiment_name}Script.sh")

            with open(script_file_path, 'w') as output_file:
                output_file.write(scriptContent)

            script_file_url = f"generated_scripts/{clean_experiment_name}Script.sh"

            return render(response, "riboApp/preprocess.html", {
                "form": form,
                "script_file": script_file_url
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
    parquet_folder = "media/parquetFiles/"  # Adjust as needed
    files = os.listdir(parquet_folder)

    all_data = []

    for file in files:
        file_path = os.path.join(parquet_folder, file)

        # Load only relevant columns
        df = pq.read_table(file_path, columns=["gene_name", "read_count"]).to_pandas()

        # Filter for the requested gene
        filtered_df = df[df["gene_name"] == gene_name]
        all_data.append(filtered_df)

    return pd.concat(all_data, ignore_index=True)
# Upload and store all Parquet data
def upload_parquet(request):
    bulk_ribo_form = BulkParquetUploadForm()
    bulk_mrna_form = BulkMrnaParquetUploadForm()

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
                            # Create UploadedParquet instance
                            uploaded_file = UploadedParquet(file=file)
                            uploaded_file.save()

                            # Validate the file
                            file_path = uploaded_file.file.path
                            df = pq.read_table(file_path).to_pandas()

                            required_columns = {"transcript_id", "gene_name", "start_position", "end_position",
                                              "strand", "read_id", "read_length", "read_count", "region", "source_file"}

                            missing_columns = required_columns - set(df.columns)
                            if missing_columns:
                                uploaded_file.delete()  # Remove invalid file
                                failed_uploads.append(f"{file.name}: missing columns {', '.join(missing_columns)}")
                            else:
                                # 🚀 Create preprocessing cache for faster analysis
                                create_file_preprocessing_cache(file_path, "riboseq")
                                successful_uploads += 1

                        except Exception as e:
                            failed_uploads.append(f"{file.name}: {str(e)}")
                    else:
                        failed_uploads.append(f"{file.name}: not a .parquet file")

                if successful_uploads > 0:
                    messages.success(request, f"Successfully uploaded {successful_uploads} riboseq files")
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
                            # Create UploadedMrnaParquet instance
                            uploaded_file = UploadedMrnaParquet(file=file)
                            uploaded_file.save()

                            # Validate the file
                            file_path = uploaded_file.file.path
                            df = pq.read_table(file_path).to_pandas()

                            required_columns = {"transcript_id", "gene_name", "start_position", "end_position",
                                              "strand", "read_id", "read_length", "read_count", "region", "source_file"}

                            missing_columns = required_columns - set(df.columns)
                            if missing_columns:
                                uploaded_file.delete()  # Remove invalid file
                                failed_uploads.append(f"{file.name}: missing columns {', '.join(missing_columns)}")
                            else:
                                # 🚀 Create preprocessing cache for faster analysis
                                create_file_preprocessing_cache(file_path, "mrna")
                                successful_uploads += 1

                        except Exception as e:
                            failed_uploads.append(f"{file.name}: {str(e)}")
                    else:
                        failed_uploads.append(f"{file.name}: not a .parquet file")

                if successful_uploads > 0:
                    messages.success(request, f"Successfully uploaded {successful_uploads} mRNA files")
                if failed_uploads:
                    messages.error(request, f"Failed uploads: {'; '.join(failed_uploads)}")

                return redirect("upload_parquet")



    return render(request, "riboApp/uploadParquet.html", {
        "bulk_ribo_form": bulk_ribo_form,
        "bulk_mrna_form": bulk_mrna_form
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



def load_or_build_gene_counts_dict(parquet_filename):
    parquet_folder = "media/parquetFiles/"
    pickle_folder = "media/parquetPickles/"
    os.makedirs(pickle_folder, exist_ok=True)

    parquet_path = os.path.join(parquet_folder, parquet_filename)
    base_name = os.path.splitext(parquet_filename)[0]
    pickle_path = os.path.join(pickle_folder, f"{base_name}.pkl")

    if os.path.exists(pickle_path):
        parquet_mtime = os.path.getmtime(parquet_path)
        pickle_mtime = os.path.getmtime(pickle_path)
        if pickle_mtime > parquet_mtime:
            with open(pickle_path, "rb") as f:
                print(f"Loading gene_counts_dict from pickle for {parquet_filename}")
                return pickle.load(f)

    print(f"⏳ Building gene_counts_dict for {parquet_filename} ...")
    gene_counts = {}
    pq_file = pq.ParquetFile(parquet_path)
    for batch in pq_file.iter_batches(batch_size=100000, columns=["gene_name", "read_count"]):
        df_chunk = batch.to_pandas()
        for _, row in df_chunk.iterrows():
            gene = row["gene_name"]
            count = row["read_count"]
            gene_counts[gene] = gene_counts.get(gene, 0) + count

    with open(pickle_path, "wb") as f:
        pickle.dump(gene_counts, f)
        print(f"Saved pickle: {pickle_path}")
    return gene_counts

def get_gene_counts(file1, file2):
    """Get gene counts for two files - OPTIMIZED with preprocessing cache"""

    # 🚀 Try to use the new preprocessing cache first (much faster)
    df1_counts = get_cached_gene_counts(file1, "riboseq")
    df2_counts = get_cached_gene_counts(file2, "riboseq")

    if not df1_counts.empty and not df2_counts.empty:
        # Use cached data - convert to dict format for compatibility
        gene_counts_1 = dict(zip(df1_counts['gene_name'], df1_counts['total_count']))
        gene_counts_2 = dict(zip(df2_counts['gene_name'], df2_counts['total_count']))
        print(f"🚀 Using cached gene counts for {file1} and {file2}")
    else:
        # Fallback to existing pickle cache system
        print(f"⚠️ Cache miss, using pickle cache for {file1} and {file2}")
        gene_counts_1 = load_or_build_gene_counts_dict(file1)
        gene_counts_2 = load_or_build_gene_counts_dict(file2)

    common_genes = set(gene_counts_1.keys()) & set(gene_counts_2.keys())

    df_merged = pd.DataFrame({
        "gene_name": list(common_genes),
        "read_count_x": [gene_counts_1[g] for g in common_genes],
        "read_count_y": [gene_counts_2[g] for g in common_genes],
    })

    print(f"Processed {len(common_genes)} common genes for {file1} and {file2}")
    return df_merged

def geneCounts(request):
    selected_genes = SelectedGene.objects.all()
    parquet_files = get_available_parquet_files()
    plot_div = None
    file1 = None
    file2 = None

    if request.method == "POST":
        file1 = request.POST.get("file1")
        file2 = request.POST.get("file2")
        if file1 and file2:
            df = get_gene_counts(file1, file2)
            print(f"Generating scatter plot for {file1} vs {file2}")
            fig = px.scatter(
                df,
                x="read_count_x",
                y="read_count_y",
                hover_name="gene_name",
                title=f"Gene Read Counts: {file1} vs {file2}",
                labels={"read_count_x": file1, "read_count_y": file2},
            )
            plot_div = fig.to_html(full_html=False)

    return render(request, "riboApp/geneCounts.html", {
        "selected_genes": selected_genes,
        "parquet_files": parquet_files,
        "plot_div": plot_div,
        "file1": file1,
        "file2": file2,
    })


def plot_gene_counts(request):
    file1 = request.GET.get("file1")
    file2 = request.GET.get("file2")
    if not file1 or not file2:
        print("ERROR: No files selected!")
        return JsonResponse({"error": "No files selected."})

    cache_key = f"gene_counts_json_{file1}_{file2}"
    cached_json = cache.get(cache_key)
    if cached_json is not None:
        print("Loaded plot JSON from cache.")
        return JsonResponse(cached_json, safe=False)

    df = get_gene_counts(file1, file2)
    if df.empty:
        print("ERROR: DataFrame is empty!")
        return JsonResponse({"error": "No data for scatter plot."})

    fig = px.scatter(
        df,
        x="read_count_x",
        y="read_count_y",
        hover_name="gene_name",
        title=f"Gene Read Counts: {file1} vs {file2}",
        labels={"read_count_x": file1, "read_count_y": file2}
    )
    fig_json = fig.to_json()
    cache.set(cache_key, fig_json, timeout=None)
    print("Plot Generated Successfully")
    return JsonResponse(fig_json, safe=False)

# Function to list available Parquet files
def get_available_parquet_files():
    parquet_folder = "media/parquetFiles/"
    files = [f for f in os.listdir(parquet_folder) if f.endswith(".parquet")]
    print(f"Available Parquet Files: {files}")  # Debugging
    return files

# Function to list available mRNA Parquet files
def get_available_mrna_files():
    mrna_folder = "media/mrnaFiles/"
    if not os.path.exists(mrna_folder):
        return []
    files = [f for f in os.listdir(mrna_folder) if f.endswith(".parquet")]
    print(f"Available mRNA Files: {files}")  # Debugging
    return files


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


def load_selected_genes():
    selected_genes = SelectedGene.objects.values_list('gene_name', flat=True)
    return set(selected_genes)

def get_available_parquet_files():
    return [f for f in os.listdir(PARQUET_FOLDER) if f.endswith(".parquet")]

def get_available_mrna_parquet_files():
    if not os.path.exists(MRNA_FOLDER):
        return []
    return [f for f in os.listdir(MRNA_FOLDER) if f.endswith(".parquet")]

def get_bin_counts(selected_file):
    selected_genes = load_selected_genes()
    print("🔍 Selected genes:", selected_genes)

    if not selected_genes:
        return None, "No selected genes found!"

    # Use a cache key so we don't re-generate plots unnecessarily
    genes_key = "_".join(sorted(selected_genes))
    cache_key = f"bin_counts_{selected_file}_{genes_key}"

    cached_plots = cache.get(cache_key)
    if cached_plots is not None:
        print(f"Loaded bin count plots from cache for {selected_file}")
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

    # Cache the final HTML
    cache.set(cache_key, plot_html, timeout=None)
    print(f"Stored bin count plots in cache for {selected_file}")

    return plot_html, None



def combined_geneCounts(request):
    """Combined gene counts view for riboseq and mRNA files"""
    selected_genes = SelectedGene.objects.all()
    ribo_files = get_available_parquet_files()
    mrna_files = get_available_mrna_parquet_files()
    plot_div = None
    ribo_file = None
    mrna_file = None

    if request.method == "POST":
        ribo_file = request.POST.get("ribo_file")
        mrna_file = request.POST.get("mrna_file")
        if ribo_file and mrna_file:
            df = get_combined_gene_counts(ribo_file, mrna_file)
            print(f"Generating combined scatter plot for {ribo_file} (Ribo) vs {mrna_file} (mRNA)")
            fig = px.scatter(
                df,
                x="ribo_count",
                y="mrna_count",
                hover_name="gene_name",
                title=f"Gene Read Counts: {ribo_file} (Ribo) vs {mrna_file} (mRNA)",
                labels={"ribo_count": f"Riboseq: {ribo_file}", "mrna_count": f"mRNA: {mrna_file}"},
            )
            plot_div = fig.to_html(full_html=False)

    return render(request, "riboApp/combinedGeneCounts.html", {
        "selected_genes": selected_genes,
        "ribo_files": ribo_files,
        "mrna_files": mrna_files,
        "plot_div": plot_div,
        "ribo_file": ribo_file,
        "mrna_file": mrna_file,
    })




def bin_counts_view(request):
    parquet_files = get_available_parquet_files()
    plots = None
    error_message = None

    selected_file = request.GET.get("selected_file", "")

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

    cached_plots = cache.get(cache_key)
    if cached_plots is not None:
        print(f"Loaded read length distribution plots from cache for {files_key}")
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

    # Cache the final HTML
    cache.set(cache_key, plot_html, timeout=None)
    print(f"Stored read length distribution plots in cache for {files_key}")

    return plot_html, None


def read_length_distribution_view(request):
    """
    View for read length distribution analysis.
    """
    parquet_files = get_available_parquet_files()
    plots = None
    error_message = None
    selected_files = []

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
    if not selected_files:
        return None, "No files selected!"

    # Check cache first
    cache_key = f"psite_offset_{'_'.join(sorted(selected_files))}"
    cached_result = get_cached_plot(cache_key)
    if cached_result:
        print(f"🚀 Using cached P-site offset plot for {', '.join(selected_files)}")
        return cached_result, None

    # Load P-site offsets (needed for read length filtering)
    if not os.path.exists(OFFSET_CSV):
        return None, "P-site offset CSV file not found! Please configure P-site offsets first."

    offsets_df = pd.read_csv(OFFSET_CSV)
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

            # Look at positions from -20 to +60 relative to the adjusted reference
            position_range = range(-20, 61)

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
    parquet_files = get_available_parquet_files()
    plot_html = None
    error_message = None
    success_message = None
    selected_files = []
    current_offsets = {}

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


GTF_FILE = "media/gencode.vM25.annotation.gtf"  # Path to GTF file
PARQUET_FOLDER = "media/parquetFiles/"          # Path where Parquet files are stored

def calculate_gene_lengths(gtf_file):
    if not os.path.exists(gtf_file):
        print("ERROR: GTF file not found!")
        return pd.DataFrame()  # Return empty DataFrame to prevent crashes

    col_names = ["seqname", "source", "feature", "start", "end", "score", "strand", "frame", "attribute"]
    gtf_data = pd.read_csv(gtf_file, sep="\t", names=col_names, comment="#")

    # Keep only exons
    exon_data = gtf_data[gtf_data["feature"] == "exon"].copy()

    # Extract gene_name from attribute
    def extract_gene_name(attr):
        match = re.search(r'gene_name\s+"([^"]+)"', attr)
        return match.group(1) if match else None  # Return None if not found

    exon_data["gene_name"] = exon_data["attribute"].apply(extract_gene_name)
    exon_data.dropna(subset=["gene_name"], inplace=True)

    exon_data["length"] = exon_data["end"] - exon_data["start"] + 1
    gene_lengths = exon_data.groupby("gene_name", as_index=False)["length"].sum()
    gene_lengths["length_kb"] = gene_lengths["length"] / 1000
    print(f"Extracted gene lengths for {len(gene_lengths)} genes.")
    return gene_lengths[["gene_name", "length_kb"]]

def process_parquet_file_gene_counts(file_path):
    """Process parquet file for gene counts - OPTIMIZED with cache"""
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

def get_mrna_gene_counts_dict(mrna_filename):
    """Get or create gene counts dictionary for mRNA file with caching"""
    mrna_path = os.path.join(MRNA_FOLDER, mrna_filename)
    pickle_path = f"media/mrnaPickles/{mrna_filename.replace('.parquet', '.pkl')}"

    if os.path.exists(pickle_path):
        print(f"Loading cached mRNA gene counts: {pickle_path}")
        with open(pickle_path, "rb") as f:
            return pickle.load(f)

    print(f"⏳ Building gene_counts_dict for mRNA {mrna_filename} ...")
    gene_counts = {}
    pq_file = pq.ParquetFile(mrna_path)
    for batch in pq_file.iter_batches(batch_size=100000, columns=["gene_name", "read_count"]):
        df_chunk = batch.to_pandas()
        for _, row in df_chunk.iterrows():
            gene = row["gene_name"]
            count = row["read_count"]
            gene_counts[gene] = gene_counts.get(gene, 0) + count

    with open(pickle_path, "wb") as f:
        pickle.dump(gene_counts, f)
        print(f"Saved mRNA pickle: {pickle_path}")
    return gene_counts

def get_combined_gene_counts(ribo_file, mrna_file):
    """Get combined gene counts from riboseq and mRNA files - OPTIMIZED with cache"""

    # 🚀 Try to use preprocessing cache first
    ribo_df = get_cached_gene_counts(ribo_file, "riboseq")
    mrna_df = get_cached_gene_counts(mrna_file, "mrna")

    if not ribo_df.empty and not mrna_df.empty:
        # Use cached data
        ribo_counts = dict(zip(ribo_df['gene_name'], ribo_df['total_count']))
        mrna_counts = dict(zip(mrna_df['gene_name'], mrna_df['total_count']))
        print(f"🚀 Using cached data for combined analysis: {ribo_file} + {mrna_file}")
    else:
        # Fallback to existing method
        print(f"⚠️ Cache miss, using pickle cache for combined analysis")
        ribo_counts = load_or_build_gene_counts_dict(ribo_file)
        mrna_counts = get_mrna_gene_counts_dict(mrna_file)

    # Get all unique genes from both datasets
    all_genes = set(ribo_counts.keys()) | set(mrna_counts.keys())

    combined_data = []
    for gene in all_genes:
        ribo_count = ribo_counts.get(gene, 0)
        mrna_count = mrna_counts.get(gene, 0)
        combined_data.append({
            "gene_name": gene,
            "ribo_count": ribo_count,
            "mrna_count": mrna_count
        })

    return pd.DataFrame(combined_data)


import hashlib

import hashlib
import glob
import os
import plotly.io as pio


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

def pca_gene_counts(request):

    if not os.path.exists(GTF_FILE):
        return render(request, "riboApp/error.html", {"error_message": "GTF file not found!"})

    cache_key = build_pca_cache_key()
    if cache_key is None:
        return render(request, "riboApp/error.html", {"error_message": "Failed to build cache key!"})

    print(f"Checking cache for key: {cache_key}")

    cached_plot_json = cache.get(cache_key)
    if cached_plot_json is not None:
        print("Loaded PCA plot from cache.")

        # Correctly reconstruct the figure using plotly.io.from_json()
        fig = pio.from_json(cached_plot_json)  # 🔄 Fixed JSON deserialization
        pca_plot_html = fig.to_html(full_html=False)  # Ensure HTML rendering

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

    gene_lengths = calculate_gene_lengths(GTF_FILE)
    if gene_lengths.empty:
        return render(request, "riboApp/error.html", {"error_message": "No gene lengths extracted from GTF!"})
    print(gene_lengths.head())

    # Load all Parquet files
    parquet_files = glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
    if not parquet_files:
        return render(request, "riboApp/error.html", {"error_message": "No Parquet files found!"})

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
        return render(request, "riboApp/error.html", {"error_message": "'length_kb' column missing after merging!"})

    gene_counts_df.dropna(subset=["length_kb"], inplace=True)
    gene_counts_df["length_kb"] = pd.to_numeric(gene_counts_df["length_kb"], errors="coerce")
    print(f"After filtering, {len(gene_counts_df)} rows remain.")

    # Pivot the DataFrame so that each file's gene counts are a separate column.
    pivot_df = gene_counts_df.pivot_table(index="gene_name", columns="file_name", values="read_count", fill_value=0).reset_index()
    pivot_df = pivot_df.merge(gene_counts_df[["gene_name", "length_kb"]].drop_duplicates(), on="gene_name", how="left")
    pivot_df["length_kb"] = pd.to_numeric(pivot_df["length_kb"], errors="coerce")
    if pivot_df.empty:
        return render(request, "riboApp/error.html", {"error_message": "No valid gene count data after pivoting!"})

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

    # Generate the interactive PCA plot using Plotly
    fig = px.scatter(
        pca_df, x="PC1", y="PC2", text="file", color="PC1",
        title="PCA of Gene Counts (RPKM Normalized)"
    )
    fig.update_traces(textposition="top center")
    pca_plot_html = fig.to_html(full_html=False)

    # Cache the result indefinitely (or set a timeout if you prefer)
    # ✅ Store PCA plot as JSON before caching
    pca_plot_json = fig.to_json()  # 🔄 Corrected storage format
    cache.set(cache_key, pca_plot_json, timeout=None)
    print("Stored PCA plot in cache.")
    return render(request, "riboApp/pca_plot.html", {"pca_plot": pca_plot_html})

def combined_pca_gene_counts(request):
    """Combined PCA analysis for riboseq and mRNA files"""

    if not os.path.exists(GTF_FILE):
        return render(request, "riboApp/error.html", {"error_message": "GTF file not found!"})

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
        return render(request, "riboApp/error.html", {"error_message": "No Parquet files found!"})

    cache_key = f"combined_pca_{'_'.join(all_files)}"
    hashed_key = hashlib.md5(cache_key.encode()).hexdigest()
    cache_key = f"combined_pca_{hashed_key}"

    cached_plot_json = cache.get(cache_key)
    if cached_plot_json is not None:
        print("Loaded combined PCA plot from cache.")
        fig = pio.from_json(cached_plot_json)
        pca_plot_html = fig.to_html(full_html=False)
        return render(request, "riboApp/combinedPca.html", {"pca_plot": pca_plot_html})

    print("Combined PCA plot NOT found in cache. Recomputing...")

    gene_lengths = calculate_gene_lengths(GTF_FILE)
    if gene_lengths.empty:
        return render(request, "riboApp/error.html", {"error_message": "No gene lengths extracted from GTF!"})

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
        return render(request, "riboApp/error.html", {"error_message": "No valid files found!"})

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
        return render(request, "riboApp/error.html", {"error_message": "No valid gene count data after pivoting!"})

    # RPKM Normalization
    sample_cols = [col for col in pivot_df.columns if col not in ("gene_name", "length_kb")]
    for col in sample_cols:
        pivot_df[col] = (pivot_df[col] / pivot_df["length_kb"]) * 1e6 / pivot_df[col].sum()

    # Perform PCA
    pca = PCA(n_components=2)
    pca_results = pca.fit_transform(pivot_df[sample_cols].T)

    # Create PCA dataframe with file type information
    pca_df = pd.DataFrame({
        "PC1": pca_results[:, 0],
        "PC2": pca_results[:, 1],
        "file": sample_cols
    })
    pca_df["file_type"] = pca_df["file"].apply(lambda x: x.split("_")[0])

    # Generate the interactive PCA plot with color coding by file type
    fig = px.scatter(
        pca_df, x="PC1", y="PC2", text="file", color="file_type",
        title="Combined PCA of Gene Counts (RPKM Normalized): Riboseq vs mRNA",
        color_discrete_map={"Riboseq": "#1f77b4", "mRNA": "#ff7f0e"}
    )
    fig.update_traces(textposition="top center")
    pca_plot_html = fig.to_html(full_html=False)

    # Cache the result
    pca_plot_json = fig.to_json()
    cache.set(cache_key, pca_plot_json, timeout=None)
    print("Stored combined PCA plot in cache.")

    return render(request, "riboApp/combinedPca.html", {"pca_plot": pca_plot_html})


import os
import pandas as pd
import matplotlib.pyplot as plt
from ribopy import Ribo
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

def psite_metagene_plots(request):
    """Generate P-site offset metagene plots for parquet files"""
    parquet_files = get_available_parquet_files()
    selected_genes = load_selected_genes()
    start_plot = None
    stop_plot = None
    error_message = None

    if request.method == "POST":
        selected_files = request.POST.getlist("selected_files")
        use_selected_genes = request.POST.get("use_selected_genes") == "on"

        if not selected_files:
            error_message = "Please select at least one file."
        elif use_selected_genes and not selected_genes:
            error_message = "No genes selected. Please select genes first or uncheck 'Use Selected Genes Only'."
        else:
            try:
                # Generate metagene plots
                genes_to_use = selected_genes if use_selected_genes else None
                start_plot, stop_plot = generate_psite_metagene_plots(selected_files, genes_to_use)
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

        # Read parquet file
        df = pq.read_table(file_path, columns=[
            "gene_name", "start_position", "end_position", "read_length", "read_count", "region"
        ]).to_pandas()

        # Filter for CDS regions only (where ribosomes should be)
        df = df[df["region"] == "CDS"]

        if df.empty:
            print(f"Warning: No CDS data found in {file}")
            continue

        # Calculate total reads for normalization
        total_reads = df["read_count"].sum()

        # Process start codon data (positions around start codon)
        start_data = process_metagene_data(df, file_offsets, file_basename, total_reads, "start", selected_genes)
        if not start_data.empty:
            all_start_data.append(start_data)

        # Process stop codon data (positions around stop codon)
        stop_data = process_metagene_data(df, file_offsets, file_basename, total_reads, "stop", selected_genes)
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

def process_metagene_data(df, file_offsets, experiment_name, total_reads, site_type, selected_genes=None):
    """Process parquet data to create metagene coverage around start/stop codons"""

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

    # For start codon analysis, we want positions relative to start codon (position 0)
    # For stop codon analysis, we want positions relative to stop codon
    # Since we don't have explicit start/stop codon positions, we'll use gene boundaries
    # and assume start codon is at the beginning of CDS and stop codon at the end

    metagene_data = []

    # Group by gene to get start/stop positions
    for gene_name, gene_df in df_filtered.groupby("gene_name"):
        if len(gene_df) < 10:  # Skip genes with too few reads
            continue

        if site_type == "start":
            # Use the minimum P-site position as the start codon reference
            reference_pos = gene_df["p_site"].min()
            # Look at positions from -30 to +62 relative to start
            position_range = range(-30, 63)
        else:  # stop
            # For stop codon, we need to find the actual CDS end
            # Use P-site positions and find the end of the CDS region
            # The stop codon should be near the end of the CDS
            p_sites = gene_df["p_site"].sort_values()
            # Use a position that's likely to be near the stop codon
            # Take the 95th percentile of P-site positions as stop codon reference
            reference_pos = int(p_sites.quantile(0.95))
            # Look at positions from -2 to +60 relative to stop codon
            position_range = range(-2, 61)

        # Calculate relative positions
        gene_df = gene_df.copy()
        gene_df["relative_position"] = gene_df["p_site"] - reference_pos


        # Aggregate counts for each relative position
        for pos in position_range:
            pos_data = gene_df[gene_df["relative_position"] == pos]
            count = pos_data["read_count"].sum()

            if count > 0:  # Only include positions with reads
                metagene_data.append({
                    "experiment": experiment_name,
                    "shifted_position": pos,
                    "avg_count": (count / total_reads) * 1e6,  # Normalize to RPM
                    "gene_name": gene_name
                })

    if not metagene_data:
        return pd.DataFrame()

    # Convert to DataFrame and aggregate across genes for each experiment
    metagene_df = pd.DataFrame(metagene_data)

    if selected_genes:
        # When using selected genes, combine all genes into a single line per experiment
        # Sum the counts across all selected genes for each position
        result = metagene_df.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].sum()
        # Add a label to indicate this is selected genes
        result["experiment"] = result["experiment"] + " (Selected Genes)"
    else:
        # Average across all genes for each position and experiment (original behavior)
        result = metagene_df.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].mean()

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

            df = pq.read_table(file_path).to_pandas()
            total_reads = df["read_count"].sum()

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
        cache.set(f"{cache_key_base}_gene_counts", gene_counts.to_dict('records'), timeout=None)

        # Cache 2: Read length distribution
        read_length_dist = df.groupby("read_length")["read_count"].sum().reset_index()
        cache.set(f"{cache_key_base}_read_length", read_length_dist.to_dict('records'), timeout=None)

        # Cache 3: Region-based statistics
        if 'region' in df.columns:
            region_stats = df.groupby(['region', 'read_length']).agg({
                'read_count': ['sum', 'mean', 'count']
            }).reset_index()
            region_stats.columns = ['region', 'read_length', 'total_reads', 'mean_reads', 'num_positions']
            cache.set(f"{cache_key_base}_region_stats", region_stats.to_dict('records'), timeout=None)

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
                            cache.set(f"{cache_key_base}_psite_data", cds_df.to_dict('records'), timeout=None)
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
        cache.set(f"{cache_key_base}_metadata", file_metadata, timeout=None)

        processing_time = time.time() - start_time
        print(f"Preprocessing cache created in {processing_time:.2f}s for {filename}")

        return True

    except Exception as e:
        print(f"Error creating preprocessing cache for {filename}: {str(e)}")
        return False


def get_cached_gene_counts(filename, file_type="riboseq"):
    """Fast retrieval of gene counts from cache"""
    cache_key = f"preprocess_{file_type}_{filename}_gene_counts"
    cached_data = cache.get(cache_key)

    if cached_data:
        return pd.DataFrame(cached_data)

    # Fallback to file reading if cache miss
    print(f"Cache miss for {filename}, reading from file...")
    file_path = os.path.join(PARQUET_FOLDER if file_type == "riboseq" else MRNA_FOLDER, filename)
    if os.path.exists(file_path):
        create_file_preprocessing_cache(file_path, file_type)
        cached_data = cache.get(cache_key)
        if cached_data:
            return pd.DataFrame(cached_data)

    return pd.DataFrame()


def get_cached_file_metadata(filename, file_type="riboseq"):
    """Get file metadata from cache"""
    cache_key = f"preprocess_{file_type}_{filename}_metadata"
    return cache.get(cache_key, {})


def get_cached_read_length_data(filename, file_type="riboseq"):
    """Fast retrieval of read length distribution from cache"""
    cache_key = f"preprocess_{file_type}_{filename}_read_length"
    cached_data = cache.get(cache_key)

    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_cds_data(filename):
    """Fast retrieval of CDS data for metagene analysis"""
    cache_key = f"preprocess_riboseq_{filename}_cds_data"
    cached_data = cache.get(cache_key)

    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_region_stats(filename, file_type="riboseq"):
    """Fast retrieval of region statistics from cache"""
    cache_key = f"preprocess_{file_type}_{filename}_region_stats"
    cached_data = cache.get(cache_key)

    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_psite_data(filename):
    """Fast retrieval of P-site enhanced data for metagene analysis"""
    cache_key = f"preprocess_riboseq_{filename}_psite_data"
    cached_data = cache.get(cache_key)

    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_plot(cache_key):
    """Get cached plot HTML"""
    return cache.get(cache_key)


def set_cached_plot(cache_key, plot_html, timeout=3600):
    """Cache plot HTML for 1 hour by default"""
    cache.set(cache_key, plot_html, timeout)


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
    """View to trigger preprocessing of all uploaded files"""
    if request.method == "POST":
        try:
            preprocess_all_uploaded_files()
            messages.success(request, "All files have been preprocessed successfully! Analysis should now be much faster.")
        except Exception as e:
            messages.error(request, f"Error during preprocessing: {str(e)}")

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