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

def get_gene_counts(file1, file2, cds_only=False):
    """
    Reads two selected Parquet files in chunks, merges data on gene_name,
    and returns a **memory-efficient** Pandas DataFrame.

    Args:
        file1: First parquet file name
        file2: Second parquet file name
        cds_only: If True, only include CDS region reads
    """
    parquet_folder = "media/parquetFiles/"
    file1_path = os.path.join(parquet_folder, file1)
    file2_path = os.path.join(parquet_folder, file2)

    region_text = " (CDS only)" if cds_only else ""
    print(f"Processing {file1_path} and {file2_path}{region_text}")

    # Choose columns to read based on whether we need region filtering
    columns = ["gene_name", "read_count"]
    if cds_only:
        columns.append("region")

    gene_counts = {}

    # Process first file
    for batch in pq.ParquetFile(file1_path).iter_batches(batch_size=100000, columns=columns):
        df_chunk = batch.to_pandas()

        # Filter for CDS only if requested
        if cds_only:
            df_chunk = df_chunk[df_chunk["region"] == "CDS"]

        for _, row in df_chunk.iterrows():
            gene = row["gene_name"]
            count = row["read_count"]
            if gene in gene_counts:
                gene_counts[gene]["x"] += count
            else:
                gene_counts[gene] = {"x": count}

    # Process second file
    for batch in pq.ParquetFile(file2_path).iter_batches(batch_size=100000, columns=columns):
        df_chunk = batch.to_pandas()

        # Filter for CDS only if requested
        if cds_only:
            df_chunk = df_chunk[df_chunk["region"] == "CDS"]

        for _, row in df_chunk.iterrows():
            gene = row["gene_name"]
            count = row["read_count"]
            if gene in gene_counts:
                if "y" in gene_counts[gene]:
                    gene_counts[gene]["y"] += count
                else:
                    gene_counts[gene]["y"] = count

    # Convert to DataFrame (only genes that exist in both files)
    valid_genes = {gene: counts for gene, counts in gene_counts.items() if "x" in counts and "y" in counts}

    df_merged = pd.DataFrame({
        "gene_name": list(valid_genes.keys()),
        "read_count_x": [counts["x"] for counts in valid_genes.values()],
        "read_count_y": [counts["y"] for counts in valid_genes.values()]
    })

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
        cds_only = request.POST.get("cds_only") == "true"
        show_regions = request.POST.get("show_regions") == "true"

        if file1 and file2:
            if show_regions:
                # Import the region-aware function from views
                from riboApp.views import get_gene_counts_with_regions
                df = get_gene_counts_with_regions(file1, file2, cds_only=cds_only)

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
                    title=f"Scatter Plot{region_text} of {file1} vs {file2}<br><sub>Overall R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
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
                # Use traditional aggregated function
                df = get_gene_counts(file1, file2, cds_only=cds_only)

                region_text = " (CDS only)" if cds_only else ""
                print(f"Generating scatter plot for {file1} (X-axis) vs {file2} (Y-axis){region_text}")

                # Calculate correlation coefficient
                correlation = df["read_count_x"].corr(df["read_count_y"])
                r_squared = correlation ** 2

                fig = px.scatter(
                    df,
                    x="read_count_x",
                    y="read_count_y",
                    hover_name="gene_name",
                    title=f"Scatter Plot{region_text} of {file1} vs {file2}<br><sub>R = {correlation:.3f}, R² = {r_squared:.3f}</sub>",
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
        print(f"Saving selected genes: {genes}")  # ✅ Debugging

        for gene in genes:
            SelectedGene.objects.get_or_create(gene_name=gene)

        return JsonResponse({"message": f"Saved {len(genes)} genes to database."})

    return JsonResponse({"error": "Invalid request"}, status=400)