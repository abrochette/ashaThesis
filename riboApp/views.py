from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect, Http404
from .models import ProcessingInput
from .forms import CreateNewList
import mimetypes
import yaml
import os
import pandas as pd
from .forms import ParquetUploadForm
from .models import ParquetData
from django.contrib import messages
from django.db import models
import pyarrow.parquet as pq
import dash
from dash import dcc, html
from .models import SelectedGene
import riboApp.geneCounts
from django_plotly_dash import DjangoDash
from django.shortcuts import render
from django.http import JsonResponse
import plotly.express as px
import pandas as pd
import os
import pyarrow.parquet as pq


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