from django.shortcuts import render
from django.http import JsonResponse
import plotly.express as px
import pandas as pd
import os
import pyarrow.parquet as pq
from .models import SelectedGene

def get_available_parquet_files():
    """
    Returns a list of available Parquet files in the storage folder.
    """
    parquet_folder = "media/parquetFiles/"
    return [f for f in os.listdir(parquet_folder) if f.endswith(".parquet")]

def get_gene_counts(file1, file2):
    """
    Reads two selected Parquet files in chunks, merges data on `gene_name`,
    and returns a **memory-efficient** Pandas DataFrame.
    """
    parquet_folder = "media/parquetFiles/"
    file1_path = os.path.join(parquet_folder, file1)
    file2_path = os.path.join(parquet_folder, file2)

    print(f"✅ Processing {file1_path} and {file2_path}")

    # ✅ Read only "gene_name" and "read_count" columns in chunks
    gene_counts = {}

    for batch in pq.ParquetFile(file1_path).iter_batches(batch_size=100000, columns=["gene_name", "read_count"]):
        df_chunk = batch.to_pandas()
        for _, row in df_chunk.iterrows():
            gene_counts[row["gene_name"]] = {"x": row["read_count"]}

    for batch in pq.ParquetFile(file2_path).iter_batches(batch_size=100000, columns=["gene_name", "read_count"]):
        df_chunk = batch.to_pandas()
        for _, row in df_chunk.iterrows():
            if row["gene_name"] in gene_counts:
                gene_counts[row["gene_name"]]["y"] = row["read_count"]

    # ✅ Convert to DataFrame (only genes that exist in both files)
    df_merged = pd.DataFrame.from_dict(gene_counts, orient="index").dropna().reset_index()
    df_merged.columns = ["gene_name", "read_count_x", "read_count_y"]

    return df_merged

def geneCounts(request):
    """
    Renders the gene counts page with dropdowns for file selection.
    """
    selected_genes = SelectedGene.objects.all()
    parquet_files = get_available_parquet_files()
    plot_div = None  # Default empty plot

    if request.method == "POST":
        file1 = request.POST.get("file1")
        file2 = request.POST.get("file2")

        if file1 and file2:
            df = get_gene_counts(file1, file2)
            print(f"Generating scatter plot for {file1} (X-axis) vs {file2} (Y-axis)")

            fig = px.scatter(
                df,
                x="read_count_x",
                y="read_count_y",
                hover_name="gene_name",
                title=f"Scatter Plot of {file1} vs {file2}",
                labels={"read_count_x": file1, "read_count_y": file2},
            )

            fig.update_layout(clickmode='event+select')

            plot_div = fig.to_html(full_html=False)  # Convert to HTML

    return render(request, "riboApp/geneCounts.html", {
        "selected_genes": selected_genes,
        "parquet_files": parquet_files,
        "plot_div": plot_div  # Send the plot to the template
    })

def save_selected_genes(request):
    """
    Saves selected genes to the database.
    """
    if request.method == "POST":
        genes = request.POST.getlist("genes[]")  # Extract genes from AJAX request
        print(f"✅ Saving selected genes: {genes}")  # ✅ Debugging

        for gene in genes:
            SelectedGene.objects.get_or_create(gene_name=gene)

        return JsonResponse({"message": f"Saved {len(genes)} genes to database."})

    return JsonResponse({"error": "Invalid request"}, status=400)