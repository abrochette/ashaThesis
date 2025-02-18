from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect, Http404
from .models import ProcessingInput
from .forms import CreateNewList
import mimetypes
import yaml
from .forms import ParquetUploadForm
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
from django.shortcuts import render, redirect
import pyarrow.parquet as pq
from .models import SelectedGene


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

            scriptContent = scriptContent.replace("{filter}", filter)
            scriptContent = scriptContent.replace("{genome}", genome)
            scriptContent = scriptContent.replace("{transcriptome}", transcriptome)
            scriptContent = scriptContent.replace("{regions}", regions)
            scriptContent = scriptContent.replace("{transcriptLengths}", transcriptLengths)
            scriptContent = scriptContent.replace("{experimentName}", experimentName)
            scriptContent = scriptContent.replace("{filePaths}", filePaths)

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
    if request.method == "POST":
        form = ParquetUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.save()  # Saves file path in DB

            file_path = uploaded_file.file.path  # Full file path

            # Check if the file is valid
            try:
                df = pq.read_table(file_path).to_pandas()  # Load with PyArrow for speed

                # Ensure required columns exist
                required_columns = {"transcript_id", "gene_name", "start_position", "end_position",
                                    "strand", "read_id", "read_length", "read_count", "region", "source_file"}

                missing_columns = required_columns - set(df.columns)
                if missing_columns:
                    messages.error(request, f"Skipping missing columns: {', '.join(missing_columns)}")
                    return redirect("upload_parquet")

            except Exception as e:
                messages.error(request, f"Invalid Parquet file: {str(e)}")
                return redirect("upload_parquet")

            messages.success(request, f"File uploaded successfully: {uploaded_file.file.name}")
            return redirect("upload_parquet")

    else:
        form = ParquetUploadForm()

    return render(request, "riboApp/uploadParquet.html", {"form": form})




@csrf_exempt  # Temporarily allow AJAX requests without CSRF issues
def save_selected_genes(request):
    """
    Saves selected genes to the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            genes = data.get("genes", [])

            print(f"Received genes: {genes}")

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


# File Paths (Adjust as Needed)
PARQUET_FOLDER = "media/parquetFiles/"
OFFSET_CSV = "media/uorf_psite_offset.csv"
NBINS = 4
SKIP_5PRIME = 45
SKIP_3PRIME = 15

def load_selected_genes():
    selected_genes = SelectedGene.objects.values_list('gene_name', flat=True)
    return set(selected_genes)

def get_available_parquet_files():
    return [f for f in os.listdir(PARQUET_FOLDER) if f.endswith(".parquet")]

def get_bin_counts(selected_file):
    selected_genes = load_selected_genes()
    if not selected_genes:
        return None, "No selected genes found!"

    genes_key = "_".join(sorted(selected_genes))
    cache_key = f"bin_counts_{selected_file}_{genes_key}"
    cached_plots = cache.get(cache_key)
    if cached_plots is not None:
        print(f"✅ Loaded bin count plots from cache for {selected_file}")
        return cached_plots, None

    file_basename = os.path.splitext(selected_file)[0]
    offsets_df = pd.read_csv(OFFSET_CSV)
    offsets_df = offsets_df[offsets_df["Experiment"] == file_basename]
    if offsets_df.empty:
        return None, f"No P-site offsets found for {file_basename}!"

    length_to_offset = dict(zip(offsets_df["Read Length"], offsets_df["P-site Offset"]))

    # Load the selected Parquet file
    file_path = os.path.join(PARQUET_FOLDER, selected_file)
    df = pd.read_parquet(file_path)
    df = df[df["gene_name"].isin(selected_genes)]
    if df.empty:
        return None, f"No data found for selected genes in {selected_file}!"

    # Apply offsets to calculate the P-site positions
    df["offset"] = df["read_length"].map(length_to_offset)
    df.dropna(subset=["offset"], inplace=True)
    df["offset"] = df["offset"].astype(int)
    df["p_site"] = df["start_position"] + df["offset"]

    # Define custom hex colors for bins
    bin_colors = ["#0099c6", "#17becf", "#19d3f3", "#00b5f7"]

    plot_html = ""
    # For each gene in the selected set, generate a bar plot
    for gene_name in selected_genes:
        df_gene = df[df["gene_name"] == gene_name]
        if df_gene.empty:
            continue

        p_min = df_gene["p_site"].min()
        p_max = df_gene["p_site"].max()
        if p_max - p_min < (SKIP_5PRIME + SKIP_3PRIME):
            continue

        cds_start = p_min + SKIP_5PRIME
        cds_end = p_max - SKIP_3PRIME
        bin_edges = np.linspace(cds_start, cds_end + 1, NBINS + 1, dtype=int)
        bin_labels = [f"Bin{i}" for i in range(1, NBINS + 1)]

        df_filtered = df_gene[(df_gene["p_site"] >= cds_start) & (df_gene["p_site"] <= cds_end)].copy()
        df_filtered["bin"] = pd.cut(df_filtered["p_site"], bins=bin_edges, labels=bin_labels, right=False)
        bin_counts = df_filtered.groupby("bin")["read_id"].nunique()

        # Use as many colors as there are bins
        bar_colors = bin_colors[:len(bin_counts)]

        # Generate the Plotly bar graph
        fig = px.bar(
            x=bin_counts.index,
            y=bin_counts.values,
            labels={"x": "CDS Bins", "y": "Read Counts"},
            title=f"Read Distribution for {gene_name} in {file_basename}",
        )
        fig.update_traces(marker=dict(color=bar_colors))
        plot_html += fig.to_html(full_html=False)

    # Cache the generated plot HTML indefinitely (or set a timeout if desired)
    cache.set(cache_key, plot_html, timeout=None)
    print(f"✅ Stored bin count plots in cache for {selected_file}")
    return plot_html, None

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

    return render(request, "riboApp/binCounts.html", {
        "parquet_files": parquet_files,
        "plots": plots,
        "error_message": error_message,
        "selected_file": selected_file  # pass the selected file to the template
    })


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
    df = pd.read_parquet(file_path)
    if "gene_name" not in df.columns or "read_count" not in df.columns:
        raise ValueError(f"Missing required columns in {file_path}")
    gene_counts = df.groupby("gene_name", as_index=False)["read_count"].sum()
    gene_counts["file_name"] = os.path.basename(file_path)
    return gene_counts

def build_pca_cache_key():
    if not os.path.exists(GTF_FILE):
        return None
    gtf_mtime = os.path.getmtime(GTF_FILE)
    parquet_files = sorted(glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet")))
    parquet_key_parts = []
    for f in parquet_files:
        mtime = os.path.getmtime(f)
        basename = os.path.basename(f)
        parquet_key_parts.append(f"{basename}_{mtime}")
    # Join the parts into one key string
    key_string = f"pca_{int(gtf_mtime)}_" + "_".join(parquet_key_parts)
    return key_string

def pca_gene_counts(request):

    if not os.path.exists(GTF_FILE):
        return render(request, "riboApp/error.html", {"error_message": "GTF file not found!"})

    cache_key = build_pca_cache_key()
    if cache_key is None:
        return render(request, "riboApp/error.html", {"error_message": "Failed to build cache key!"})
    cached_plot = cache.get(cache_key)
    if cached_plot is not None:
        print("Loaded PCA plot from cache.")
        return render(request, "riboApp/pca_plot.html", {"pca_plot": cached_plot})

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
    cache.set(cache_key, pca_plot_html, timeout=None)
    print("✅ Stored PCA plot in cache.")
    return render(request, "riboApp/pca_plot.html", {"pca_plot": pca_plot_html})


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
                    print(f"⚠️ WARNING: No metagene data found for {experiment}, {site}, length {read_length}")
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
        print("❌ ERROR: No data collected from `read_multiple_files()`")

    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
def apply_psite_shift_and_average(metagene_data, psite_offsets, total_reads_dict):
    """Applies P-site shifts, averages counts, and normalizes by total reads."""

    if metagene_data.empty:
        print("❌ ERROR: metagene_data is EMPTY! Check previous functions!")
        return pd.DataFrame()

    # Ensure necessary columns exist
    expected_columns = {"experiment", "read_length", "position", "count"}
    missing_cols = expected_columns - set(metagene_data.columns)
    if missing_cols:
        print(f"❌ ERROR: Missing columns in metagene_data: {missing_cols}")
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
        print("❌ ERROR: 'experiment' column missing after processing!")
        return pd.DataFrame()

    return metagene_data.groupby(["shifted_position", "experiment"], as_index=False)["avg_count"].mean()


def plot_static_graph(data, title, x_label, y_label, filename, xlim=None, ylim=None):
    """Generates and saves a static matplotlib plot."""

    if data.empty:
        print(f"❌ ERROR: Data is EMPTY for {title}")
        return None  # Return None to prevent further errors

    # Ensure necessary columns exist
    required_columns = {"experiment", "shifted_position", "avg_count"}
    missing_cols = required_columns - set(data.columns)
    if missing_cols:
        print(f"❌ ERROR: Missing columns in data for {title}: {missing_cols}")
        print(data.head())
        return None

    plt.figure(figsize=(10, 5))

    # Define color scheme with correct color names
    color_palette = ["steelblue", "#FF1493", "darkviolet", "turquoise"]

    for i, (experiment, subset) in enumerate(data.groupby("experiment")):
        if subset.empty:
            print(f"⚠️ WARNING: No data for experiment {experiment} in {title}")
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