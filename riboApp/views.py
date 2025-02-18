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
import numpy as np
from django.shortcuts import render, redirect
from django.http import JsonResponse
import plotly.express as px
import pandas as pd
import os
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

import pyarrow.parquet as pq
import os
import pandas as pd

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


from django.shortcuts import render
from django.http import JsonResponse
import plotly.express as px
import pandas as pd
import pyarrow.parquet as pq
import os
from riboApp.models import SelectedGene, ParquetData


from django.views.decorators.csrf import csrf_exempt
import json
from django.http import JsonResponse

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import SelectedGene


@csrf_exempt  # Temporarily allow AJAX requests without CSRF issues
def save_selected_genes(request):
    """
    Saves selected genes to the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            genes = data.get("genes", [])

            print(f"✅ Received genes: {genes}")  # ✅ Debugging

            for gene in genes:
                SelectedGene.objects.get_or_create(gene_name=gene)

            return JsonResponse({"message": f"Saved {len(genes)} genes to database."})

        except json.JSONDecodeError:
            print("❌ JSON decoding error")  # ✅ Debugging
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

    print("❌ Invalid request method")  # ✅ Debugging
    return JsonResponse({"error": "Invalid request"}, status=400)



from django.shortcuts import render
import plotly.express as px
import pandas as pd
import os
import pyarrow.parquet as pq
from .models import SelectedGene

from django.shortcuts import render, redirect
from django.http import JsonResponse
import plotly.express as px
import pandas as pd
import os
import pyarrow.parquet as pq
from .models import SelectedGene

# ✅ Function to list available Parquet files
def get_available_parquet_files():
    parquet_folder = "media/parquetFiles/"
    files = [f for f in os.listdir(parquet_folder) if f.endswith(".parquet")]
    print(f"Available Parquet Files: {files}")  # ✅ Debugging
    return files

# ✅ Function to read and merge selected Parquet files
def get_gene_counts(file1, file2):
    """
    Efficiently reads two selected Parquet files in chunks, merges data on `gene_name`,
    and returns a Pandas DataFrame containing only genes that exist in both files.
    """
    parquet_folder = "media/parquetFiles/"
    file1_path = os.path.join(parquet_folder, file1)
    file2_path = os.path.join(parquet_folder, file2)

    # ✅ Store gene read counts in dictionaries for quick lookups
    gene_counts_1 = {}
    gene_counts_2 = {}

    # ✅ Read only "gene_name" and "read_count" columns in small chunks
    for batch in pq.ParquetFile(file1_path).iter_batches(batch_size=100000, columns=["gene_name", "read_count"]):
        df_chunk = batch.to_pandas()
        for _, row in df_chunk.iterrows():
            gene_counts_1[row["gene_name"]] = gene_counts_1.get(row["gene_name"], 0) + row["read_count"]

    for batch in pq.ParquetFile(file2_path).iter_batches(batch_size=100000, columns=["gene_name", "read_count"]):
        df_chunk = batch.to_pandas()
        for _, row in df_chunk.iterrows():
            gene_counts_2[row["gene_name"]] = gene_counts_2.get(row["gene_name"], 0) + row["read_count"]

    # ✅ Find common genes (only keep genes present in both files)
    common_genes = set(gene_counts_1.keys()) & set(gene_counts_2.keys())

    # ✅ Build final DataFrame (only for common genes)
    df_merged = pd.DataFrame({
        "gene_name": list(common_genes),
        "read_count_x": [gene_counts_1[g] for g in common_genes],
        "read_count_y": [gene_counts_2[g] for g in common_genes],
    })

    print(f"✅ Processed {len(common_genes)} common genes for {file1} and {file2}")

    return df_merged
# ✅ Main View: Render the page with dropdowns for file selection
def geneCounts(request):
    """
    Renders the gene counts page with dropdowns for file selection and generates a scatter plot.
    """
    selected_genes = SelectedGene.objects.all()
    parquet_files = get_available_parquet_files()
    plot_div = None

    if request.method == "POST":
        file1 = request.POST.get("file1")
        file2 = request.POST.get("file2")

        if file1 and file2:
            df = get_gene_counts(file1, file2)
            print(f"✅ Generating scatter plot for {file1} (X-axis) vs {file2} (Y-axis)")

            fig = px.scatter(
                df,
                x="read_count_x",
                y="read_count_y",
                hover_name="gene_name",
                title=f"Gene Read Counts: {file1} vs {file2}",
                labels={"read_count_x": file1, "read_count_y": file2},
            )

            plot_div = fig.to_html(full_html=False)  # Convert to HTML for rendering

    return render(request, "riboApp/geneCounts.html", {
        "selected_genes": selected_genes,
        "parquet_files": parquet_files,
        "plot_div": plot_div
    })
def plot_gene_counts(request):
    file1 = request.GET.get("file1")
    file2 = request.GET.get("file2")

    if not file1 or not file2:
        print("ERROR: No files selected!")  # ✅ Debugging
        return JsonResponse({"error": "No files selected."})

    df = get_gene_counts(file1, file2)

    print(f"DataFrame Shape: {df.shape}")  # ✅ Debugging
    print(df.head())  # ✅ Debugging

    if df["source_file"].nunique() < 2:
        print("ERROR: Not enough data!")  # ✅ Debugging
        return JsonResponse({"error": "Not enough data for scatter plot."})

    df_pivot = df.pivot(index="gene_name", columns="source_file", values="read_count").reset_index()

    if df_pivot.empty:
        print("ERROR: Pivot table is empty!")  # ✅ Debugging
        return JsonResponse({"error": "Pivot table is empty!"})

    df_pivot.columns = ["gene_name", "X_Axis", "Y_Axis"]

    fig = px.scatter(
        df_pivot,
        x="X_Axis",
        y="Y_Axis",
        hover_name="gene_name",
        title=f"Gene Read Counts: {file1} vs {file2}",
        labels={"X_Axis": file1, "Y_Axis": file2}
    )

    print("✅ Plot Generated Successfully")  # ✅ Debugging

    return JsonResponse(fig.to_json(), safe=False)


from django.shortcuts import render, redirect

import pyarrow.parquet as pq
from .models import SelectedGene

# Function to list available Parquet files
def get_available_parquet_files():
    parquet_folder = "media/parquetFiles/"
    files = [f for f in os.listdir(parquet_folder) if f.endswith(".parquet")]
    print(f"Available Parquet Files: {files}")  # Debugging
    return files

# Function to read and merge selected Parquet files
import os
import pyarrow.parquet as pq
import pandas as pd

import os
import pyarrow.parquet as pq
import pandas as pd




def load_selected_genes():
    """Loads selected genes from the Django database."""
    selected_genes = SelectedGene.objects.values_list('gene_name', flat=True)
    return set(selected_genes)


# File Paths (Adjust as Needed)
PARQUET_FOLDER = "media/parquetFiles/"
OFFSET_CSV = "media/uorf_psite_offset.csv"
NBINS = 4
SKIP_5PRIME = 45
SKIP_3PRIME = 15


def get_available_parquet_files():
    """List all available Parquet files in the storage folder."""
    return [f for f in os.listdir(PARQUET_FOLDER) if f.endswith(".parquet")]


def get_bin_counts(selected_file):
    """Generates bar plots for selected genes from the selected Parquet file."""
    selected_genes = load_selected_genes()
    if not selected_genes:
        return None, "No selected genes found!"

    file_basename = os.path.splitext(selected_file)[0]

    # Load the P-site offsets
    offsets_df = pd.read_csv(OFFSET_CSV)
    offsets_df = offsets_df[offsets_df["Experiment"] == file_basename]

    if offsets_df.empty:
        return None, f"No P-site offsets found for {file_basename}!"

    length_to_offset = dict(zip(offsets_df["Read Length"], offsets_df["P-site Offset"]))

    # Load selected Parquet file
    file_path = os.path.join(PARQUET_FOLDER, selected_file)
    df = pd.read_parquet(file_path)
    df = df[df["gene_name"].isin(selected_genes)]
    if df.empty:
        return None, f"No data found for selected genes in {selected_file}!"

    # Apply offsets
    df["offset"] = df["read_length"].map(length_to_offset)
    df.dropna(subset=["offset"], inplace=True)
    df["offset"] = df["offset"].astype(int)
    df["p_site"] = df["start_position"] + df["offset"]

    # Define custom hex colors for bins
    bin_colors = ["#0099c6", "#17becf", "#19d3f3", "#00b5f7"]  # Customize these!

    plot_html = ""
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

        # Get the color list matching the number of bins
        bar_colors = bin_colors[:len(bin_counts)]  # Assign colors to bins

        fig = px.bar(
            x=bin_counts.index,
            y=bin_counts.values,
            labels={"x": "CDS Bins", "y": "Read Counts"},
            title=f"Read Distribution for {gene_name} in {file_basename}",
        )
        fig.update_traces(marker=dict(color=bar_colors))  # Apply custom colors

        plot_html += fig.to_html(full_html=False)

    return plot_html, None

def bin_counts_view(request):
    """Renders the webpage with selectable Parquet files and corresponding bin count plots."""
    parquet_files = get_available_parquet_files()
    plots = None
    error_message = None

    if request.method == "POST":
        selected_file = request.POST.get("selected_file")

        if selected_file:
            plots, error_message = get_bin_counts(selected_file)
        else:
            error_message = "No file selected!"

    return render(request, "riboApp/binCounts.html", {
        "parquet_files": parquet_files,
        "plots": plots,
        "error_message": error_message
    })


import os
import glob
import pandas as pd
import numpy as np
from django.shortcuts import render
import plotly.express as px
from sklearn.decomposition import PCA

# ----------------- CONFIG -----------------
GTF_FILE = "media/gencode.vM25.annotation.gtf"  # Path to GTF file
PARQUET_FOLDER = "media/parquetFiles/"         # Path where Parquet files are stored


def calculate_gene_lengths(gtf_file):
    """Reads a GTF file and calculates gene lengths based on exon data."""
    if not os.path.exists(gtf_file):
        print("ERROR: GTF file not found!")
        return pd.DataFrame()  # Return empty DataFrame to prevent crashes

    col_names = ["seqname", "source", "feature", "start", "end", "score", "strand", "frame", "attribute"]
    gtf_data = pd.read_csv(gtf_file, sep="\t", names=col_names, comment="#")

    # Keep only exons
    exon_data = gtf_data[gtf_data["feature"] == "exon"].copy()

    # Extract gene_name from attribute
    import re
    def extract_gene_name(attr):
        match = re.search(r'gene_name\s+"([^"]+)"', attr)
        return match.group(1) if match else None  # Return None instead of UNKNOWN

    exon_data["gene_name"] = exon_data["attribute"].apply(extract_gene_name)

    # Remove rows where gene_name extraction failed
    exon_data.dropna(subset=["gene_name"], inplace=True)

    exon_data["length"] = exon_data["end"] - exon_data["start"] + 1

    gene_lengths = exon_data.groupby("gene_name", as_index=False)["length"].sum()
    gene_lengths["length_kb"] = gene_lengths["length"] / 1000
    print(f"Extracted gene lengths for {len(gene_lengths)} genes.")
    return gene_lengths[["gene_name", "length_kb"]]


def process_parquet_file_gene_counts(file_path):
    """Reads a Parquet file, sums read counts per gene."""
    df = pd.read_parquet(file_path)

    if "gene_name" not in df.columns or "read_count" not in df.columns:
        raise ValueError(f"Missing required columns in {file_path}")

    gene_counts = df.groupby("gene_name", as_index=False)["read_count"].sum()
    gene_counts["file_name"] = os.path.basename(file_path)
    return gene_counts


def pca_gene_counts(request):
    """
    View to process gene counts from all Parquet files, normalize using RPKM,
    perform PCA, and display the interactive PCA plot on the webpage.
    """
    if not os.path.exists(GTF_FILE):
        return render(request, "riboApp/error.html", {"error_message": "GTF file not found!"})

    # Compute gene lengths
    gene_lengths = calculate_gene_lengths(GTF_FILE)

    if gene_lengths.empty:
        return render(request, "riboApp/error.html", {"error_message": "No gene lengths extracted from GTF!"})

    print(gene_lengths.head())  # Debugging output

    # Load all Parquet files
    parquet_files = glob.glob(os.path.join(PARQUET_FOLDER, "*.parquet"))
    if not parquet_files:
        return render(request, "riboApp/error.html", {"error_message": "No Parquet files found!"})

    all_counts = []
    for file in parquet_files:
        df_counts = process_parquet_file_gene_counts(file)
        all_counts.append(df_counts)

    # Merge all files into one DataFrame
    gene_counts_df = pd.concat(all_counts, ignore_index=True)

    # Ensure gene names match in format
    gene_counts_df["gene_name"] = gene_counts_df["gene_name"].str.strip().str.lower()
    gene_lengths["gene_name"] = gene_lengths["gene_name"].str.strip().str.lower()

    # Merge with gene lengths
    gene_counts_df = pd.merge(gene_counts_df, gene_lengths, on="gene_name", how="left")

    # Debugging: Check if 'length_kb' column exists
    print(f"Columns in merged DataFrame: {gene_counts_df.columns.tolist()}")

    if "length_kb" not in gene_counts_df.columns:
        return render(request, "riboApp/error.html", {"error_message": "'length_kb' column missing after merging!"})

    # Drop genes with missing length info
    gene_counts_df.dropna(subset=["length_kb"], inplace=True)

    # Ensure 'length_kb' is numeric
    gene_counts_df["length_kb"] = pd.to_numeric(gene_counts_df["length_kb"], errors="coerce")

    print(f"After filtering, {len(gene_counts_df)} rows remain.")

    # Fix: Pivot & Ensure `length_kb` Stays
    pivot_df = gene_counts_df.pivot_table(index="gene_name", columns="file_name", values="read_count", fill_value=0).reset_index()

    # Reattach `length_kb`
    pivot_df = pivot_df.merge(gene_counts_df[["gene_name", "length_kb"]].drop_duplicates(), on="gene_name", how="left")

    # Ensure 'length_kb' is numeric after merging again
    pivot_df["length_kb"] = pd.to_numeric(pivot_df["length_kb"], errors="coerce")

    if pivot_df.empty:
        return render(request, "riboApp/error.html", {"error_message": "No valid gene count data after pivoting!"})

    print(f"Pivoted DataFrame shape: {pivot_df.shape}")
    print(f"Columns in fixed pivot_df: {pivot_df.columns.tolist()}")  # Debugging

    # RPKM Normalization
    sample_cols = [col for col in pivot_df.columns if col not in ("gene_name", "length_kb")]

    for col in sample_cols:
        pivot_df[col] = (pivot_df[col] / pivot_df["length_kb"]) * 1e6 / pivot_df[col].sum()

    # Perform PCA
    pca = PCA(n_components=2)
    pca_results = pca.fit_transform(pivot_df[sample_cols].T)

    # Create DataFrame for PCA plot
    pca_df = pd.DataFrame({"PC1": pca_results[:, 0], "PC2": pca_results[:, 1], "file": sample_cols})

    # Generate interactive PCA plot
    fig = px.scatter(
        pca_df, x="PC1", y="PC2", text="file", color="PC1",
        title="PCA of Gene Counts (RPKM Normalized)"
    )
    fig.update_traces(textposition="top center")
    pca_plot_html = fig.to_html(full_html=False)

    return render(request, "riboApp/pca_plot.html", {"pca_plot": pca_plot_html})

def metagene_analysis(request):
    """View to display start and stop codon metagene analysis."""
    start_plot_path = "downloads/start_codon_coverage.png"
    stop_plot_path = "downloads/stop_codon_coverage.png"

    context = {
        "start_plot": start_plot_path,
        "stop_plot": stop_plot_path
    }

    return render(request, "riboApp/coverageGraphs.html", context)

import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from ribopy import Ribo
from django.shortcuts import render
from django.http import JsonResponse

# Paths
RIBO_DIR = "media/ribo"
PSITE_OFFSETS_PATH = "media/uorf_psite_offset.csv"

def get_available_ribo_files():
    """Returns a list of available ribo files."""
    return [os.path.basename(f) for f in glob.glob(os.path.join(RIBO_DIR, "*.ribo"))]

def get_total_reads(ribo_obj):
    """Retrieve total read count for a Ribo object."""
    return ribo_obj.get_info()["experiment_info"]["total_reads"]

def read_metagene_data(ribo_obj, site, range_lower, range_upper):
    """Extracts metagene coverage for start/stop codons within length range."""
    metagene_data = []

    for read_length in range(range_lower, range_upper + 1):
        data = ribo_obj.get_metagene_data(site, length=read_length)
        df = pd.DataFrame(data, columns=["position", "count"])
        df["experiment"] = ribo_obj.experiment_name
        df["read_length"] = read_length
        metagene_data.append(df)

    return pd.concat(metagene_data, ignore_index=True)

def apply_psite_shifts(metagene_data, psite_offsets, total_reads):
    """Applies P-site shifts, normalizes by total reads, and averages across lengths."""
    metagene_data = metagene_data.merge(psite_offsets, on=["experiment", "read_length"], how="left")
    metagene_data["shifted_position"] = metagene_data["position"] + metagene_data["P_site_offset"]
    metagene_data["normalized_count"] = (metagene_data["count"] / total_reads) * 1e6

    return (metagene_data
            .groupby(["shifted_position", "experiment"])
            .agg(avg_count=("normalized_count", "mean"))
            .reset_index())

def generate_plots(start_shifted, stop_shifted):
    """Generates and saves plots for start and stop codon coverage."""
    custom_colors = ["#4682B4", "#EE82EE", "#9400D3", "#40E0D0"]  # Custom colors

    # Start Codon Coverage Plot
    plt.figure(figsize=(10, 5))
    sns.lineplot(data=start_shifted, x="shifted_position", y="avg_count", hue="experiment", palette=custom_colors)
    plt.title("Start Codon Coverage After Shifts")
    plt.xlabel("Shifted Position")
    plt.ylabel("Normalized Read Count (CPM)")
    plt.xlim(-30, 62)
    plt.legend(title="Experiment")
    plt.grid()
    plt.savefig("media/plots/start_codon_coverage.png")
    plt.close()

    # Stop Codon Coverage Plot
    plt.figure(figsize=(10, 5))
    sns.lineplot(data=stop_shifted, x="shifted_position", y="avg_count", hue="experiment", palette=custom_colors)
    plt.title("Stop Codon Coverage After Shifts")
    plt.xlabel("Shifted Position")
    plt.ylabel("Normalized Read Count (CPM)")
    plt.xlim(0, 20)
    plt.ylim(0, 50)
    plt.legend(title="Experiment")
    plt.grid()
    plt.savefig("media/plots/stop_codon_coverage.png")
    plt.close()

def analyze_ribo(request):
    """Handles user input for selecting a ribo file and generates plots accordingly."""
    ribo_files = get_available_ribo_files()
    selected_file = request.GET.get("ribo_file", "")

    if selected_file:
        ribo_path = os.path.join(RIBO_DIR, selected_file)
        ribo_obj = Ribo(ribo_path)

        # Load P-site offsets
        psite_offsets = pd.read_csv(PSITE_OFFSETS_PATH)
        psite_offsets.columns = ["experiment", "read_length", "P_site_offset"]
        psite_offsets = psite_offsets.drop_duplicates(subset=["experiment", "read_length"])

        total_reads = get_total_reads(ribo_obj)

        # Retrieve metagene coverage
        start_coverage = read_metagene_data(ribo_obj, "start", 28, 32)
        stop_coverage = read_metagene_data(ribo_obj, "stop", 28, 32)

        # Apply P-site shifts and normalization
        start_shifted = apply_psite_shifts(start_coverage, psite_offsets, total_reads)
        stop_shifted = apply_psite_shifts(stop_coverage, psite_offsets, total_reads)

        # Generate and save plots
        generate_plots(start_shifted, stop_shifted)

        return JsonResponse({"message": "Plots generated successfully!"})

    return render(request, "riboApp/coverageGraphs.html", {"ribo_files": ribo_files})