"""
Stop Codon Readthrough Analysis Module

Analyzes ribosome readthrough past stop codons, separated by stop codon type (TAA/TAG/TGA).
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from . import data_loader


def generate_stop_codon_readthrough_plots(selected_files):
    """
    Generate stop codon periodicity plots separated by stop codon type

    Args:
        selected_files: List of parquet filenames to analyze

    Returns:
        (plot_html, error_message, csv_data)
    """
    if not selected_files:
        return None, "No files selected!", None

    # Check if we have pre-computed results
    precomputed_csv = data_loader.get_precomputed_result('stop_codon_readthrough', selected_files)

    if precomputed_csv is not None:
        print("⚡ Using pre-computed results - instant plot generation!")
        # Just create the plot from cached CSV
        all_stop_data = _organize_csv_by_stop_type(precomputed_csv)
        plot_html = create_stop_codon_comparison_plot(all_stop_data)
        return plot_html, None, precomputed_csv

    # No pre-computed results, compute now
    print("🔄 Computing results on-the-fly...")

    # Load required data
    stop_codon_types = data_loader.load_stop_codon_types()
    if not stop_codon_types:
        return None, "Could not load stop codon types!", None

    psite_offsets = data_loader.load_psite_offsets()
    if not psite_offsets:
        return None, "P-site offsets not found! Please configure P-site offsets first.", None
    
    # Process each selected file
    all_stop_data = {'TAA': [], 'TAG': [], 'TGA': []}
    
    for selected_file in selected_files:
        file_basename = selected_file.replace('.parquet', '')
        
        print(f"📊 Processing stop codon readthrough for {selected_file}")
        
        # Load parquet data
        df = data_loader.load_parquet_file(selected_file, folder='parquet')
        if df is None:
            print(f"⚠️ Could not load {selected_file}")
            continue
        
        # Filter for CDS and UTR3 regions (UTR3 contains readthrough reads!)
        df = df[df["region"].isin(["CDS", "UTR3"])]
        
        if df.empty:
            print(f"⚠️ No CDS/UTR3 data found in {selected_file}")
            continue
        
        # Calculate total reads for normalization
        total_reads = df["read_count"].sum()
        
        # Process each stop codon type
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
            stop_data = process_stop_codon_metagene(
                df_filtered, psite_offsets, file_basename, total_reads
            )
            
            if not stop_data.empty:
                # Add stop codon type column
                stop_data['stop_codon_type'] = stop_type
                all_stop_data[stop_type].append(stop_data)
    
    # Check if we have data
    if not any(all_stop_data.values()):
        return None, "No valid data found for selected files", None
    
    # Create plot
    plot_html = create_stop_codon_comparison_plot(all_stop_data)
    
    # Combine all data for CSV export
    all_data_combined = []
    for stop_type in ['TAA', 'TAG', 'TGA']:
        if all_stop_data[stop_type]:
            combined = pd.concat(all_stop_data[stop_type], ignore_index=True)
            all_data_combined.append(combined)
    
    csv_data = pd.concat(all_data_combined, ignore_index=True) if all_data_combined else None

    # Cache the result for future use
    if csv_data is not None:
        data_loader.store_precomputed_result('stop_codon_readthrough', selected_files, csv_data)

    return plot_html, None, csv_data


def _organize_csv_by_stop_type(csv_data):
    """
    Organize CSV data by stop codon type for plotting.

    Args:
        csv_data: DataFrame with columns: position, experiment, normalized_count, stop_codon_type

    Returns:
        dict: {'TAA': [DataFrame], 'TAG': [DataFrame], 'TGA': [DataFrame]}
    """
    all_stop_data = {'TAA': [], 'TAG': [], 'TGA': []}

    for stop_type in ['TAA', 'TAG', 'TGA']:
        stop_data = csv_data[csv_data['stop_codon_type'] == stop_type]
        if not stop_data.empty:
            all_stop_data[stop_type].append(stop_data)

    return all_stop_data


def process_stop_codon_metagene(df, psite_offsets, experiment_name, total_reads):
    """
    Process metagene data for stop codon analysis - OPTIMIZED VERSION

    Args:
        df: DataFrame with read data (CDS + UTR3 regions)
        psite_offsets: Hash map of {(experiment, read_length): offset}
        experiment_name: Name of the experiment
        total_reads: Total reads for normalization

    Returns:
        DataFrame with columns: position, experiment, normalized_count
    """

    # Get CDS end positions from data loader (pre-computed)
    cds_end_positions = data_loader.load_cds_end_positions()

    if not cds_end_positions:
        # Fallback: calculate on-the-fly
        print("⚠️ CDS end positions not preloaded, calculating now...")
        cds_end_positions = {}
        for gene_name in df["gene_name"].unique():
            gene_data = df[df["gene_name"] == gene_name]
            cds_data = gene_data[gene_data["region"] == "CDS"]
            if not cds_data.empty:
                # The stop codon is at the end of the CDS region
                cds_end_positions[gene_name] = cds_data["end_position"].max()

    # Filter for read lengths 28-32 (typical ribosome footprint sizes)
    df_filtered = df[df["read_length"].between(28, 32)].copy()

    if df_filtered.empty:
        return pd.DataFrame()

    # OPTIMIZATION 1: Use vectorized map instead of apply
    # Create a mapping of read_length -> offset for this experiment
    length_to_offset = {}
    for read_length in df_filtered["read_length"].unique():
        offset = psite_offsets.get((experiment_name, int(read_length)), None)
        if offset is not None:
            length_to_offset[read_length] = offset

    # Map offsets using vectorized operation
    df_filtered["offset"] = df_filtered["read_length"].map(length_to_offset)
    df_filtered = df_filtered.dropna(subset=["offset"])
    df_filtered["p_site"] = df_filtered["start_position"] + df_filtered["offset"].astype(int)

    # OPTIMIZATION 2: Add reference positions to all rows at once
    # Create a mapping of gene_name -> reference_pos
    gene_ref_positions = {}
    for gene_name in df_filtered["gene_name"].unique():
        if gene_name in cds_end_positions:
            gene_ref_positions[gene_name] = cds_end_positions[gene_name]
        else:
            # Fallback: use max end_position in CDS
            gene_data = df_filtered[df_filtered["gene_name"] == gene_name]
            cds_reads = gene_data[gene_data["region"] == "CDS"]
            if not cds_reads.empty:
                gene_ref_positions[gene_name] = cds_reads["end_position"].max()
            else:
                gene_ref_positions[gene_name] = gene_data["p_site"].max()

    # Map reference positions using vectorized operation
    df_filtered["reference_pos"] = df_filtered["gene_name"].map(gene_ref_positions)

    # Calculate relative positions for all rows at once
    df_filtered["relative_position"] = df_filtered["p_site"] - df_filtered["reference_pos"]

    # OPTIMIZATION 3: Use groupby aggregation instead of looping through positions
    # Filter for genes with at least 10 reads
    gene_counts = df_filtered.groupby("gene_name").size()
    valid_genes = gene_counts[gene_counts >= 10].index
    df_filtered = df_filtered[df_filtered["gene_name"].isin(valid_genes)]

    genes_processed = len(valid_genes)
    genes_skipped = len(gene_counts) - genes_processed

    if df_filtered.empty:
        print(f"  Processed 0 genes, skipped {genes_skipped} genes")
        return pd.DataFrame()

    # Filter for positions from -60 to +30
    df_filtered = df_filtered[df_filtered["relative_position"].between(-60, 30)]

    # Aggregate all at once using groupby
    result = df_filtered.groupby("relative_position", as_index=False)["read_count"].sum()

    # Normalize to RPM
    result["normalized_count"] = (result["read_count"] / total_reads) * 1e6
    result["experiment"] = experiment_name
    result = result.rename(columns={"relative_position": "position"})
    result = result[["position", "experiment", "normalized_count"]]

    print(f"  Processed {genes_processed} genes, skipped {genes_skipped} genes")

    return result


def create_stop_codon_comparison_plot(all_stop_data):
    """
    Create separate plots for each sample, with each plot showing TAA/TAG/TGA lines
    
    Args:
        all_stop_data: Dict with keys 'TAA', 'TAG', 'TGA', each containing list of DataFrames
        
    Returns:
        HTML string of the plot
    """
    
    # Colors for each stop codon type
    colors = {
        'TAA': 'rgb(31, 119, 180)',   # Blue
        'TAG': 'rgb(255, 127, 14)',    # Orange
        'TGA': 'rgb(44, 160, 44)'      # Green
    }
    
    # Combine all data
    all_data_list = []
    for stop_type in ['TAA', 'TAG', 'TGA']:
        if all_stop_data[stop_type]:
            combined = pd.concat(all_stop_data[stop_type], ignore_index=True)
            all_data_list.append(combined)
    
    if not all_data_list:
        return "<p>No data to plot</p>"
    
    all_data = pd.concat(all_data_list, ignore_index=True)
    
    # Get unique experiments
    experiments = sorted(all_data['experiment'].unique())
    
    # Create subplots - one per experiment
    fig = make_subplots(
        rows=len(experiments),
        cols=1,
        subplot_titles=[f"{exp}" for exp in experiments],
        vertical_spacing=0.05,
        shared_xaxes=True
    )
    
    # Add traces for each experiment
    for idx, experiment in enumerate(experiments, 1):
        exp_data = all_data[all_data['experiment'] == experiment]
        
        for stop_type in ['TAA', 'TAG', 'TGA']:
            stop_data = exp_data[exp_data['stop_codon_type'] == stop_type]
            
            if not stop_data.empty:
                # Sort by position
                stop_data = stop_data.sort_values('position')
                
                fig.add_trace(
                    go.Scatter(
                        x=stop_data['position'],
                        y=stop_data['normalized_count'],
                        mode='lines',
                        name=stop_type,
                        line=dict(color=colors[stop_type], width=2),
                        legendgroup=stop_type,
                        showlegend=(idx == 1)  # Only show legend for first subplot
                    ),
                    row=idx,
                    col=1
                )
        
        # Add vertical line at position 0 (stop codon)
        fig.add_vline(
            x=0,
            line_dash="dash",
            line_color="gray",
            opacity=0.5,
            row=idx,
            col=1
        )
    
    # Update layout
    fig.update_layout(
        height=400 * len(experiments),
        title_text="Stop Codon Readthrough Analysis by Stop Codon Type",
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Update axes
    fig.update_xaxes(title_text="Position Relative to Stop Codon", row=len(experiments), col=1)
    fig.update_yaxes(title_text="Normalized Count (RPM)")
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

