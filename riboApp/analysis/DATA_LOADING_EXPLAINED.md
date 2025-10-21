# Data Loading System - Complete Explanation

## Overview

The new data loading system has **two levels of caching** for maximum performance:

1. **Level 1: Raw Data Cache** - Loads parquet files, GTF, offsets, etc. into memory
2. **Level 2: Pre-Computed Results Cache** - Pre-generates the actual CSV data for each plot

## Architecture Diagram

```
User Clicks "Preprocess All Files"
         ↓
┌────────────────────────────────────────────────────────────┐
│  LEVEL 1: Load Raw Data into Memory                       │
│  ────────────────────────────────────────                 │
│  • P-site offsets → Hash map: {(exp, len): offset}        │
│  • Stop codon types → Hash map: {gene: 'TAA'/'TAG'/'TGA'} │
│  • Gene lengths → Hash map: {gene: length}                │
│  • CDS end positions → Hash map: {gene: position}         │
│  • All parquet files → {filename: DataFrame}              │
│                                                            │
│  Time: ~30-60 seconds                                     │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│  LEVEL 2: Pre-Compute All Analysis Results                │
│  ────────────────────────────────────────────              │
│  For each file:                                            │
│    • Stop codon readthrough → CSV with plot data          │
│    • P-site metagene → CSV with plot data                 │
│    • PCA → CSV with plot data                             │
│    • etc.                                                  │
│                                                            │
│  Time: ~5-10 minutes (one-time cost)                      │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│  USER REQUESTS A PLOT                                      │
│  ────────────────────────────────────────                 │
│  1. Check if CSV is pre-computed                           │
│  2. If yes: Retrieve CSV and plot (< 1 second) ⚡         │
│  3. If no: Compute on-the-fly (~3-5 seconds)              │
└────────────────────────────────────────────────────────────┘
```

## What Gets Loaded/Precomputed

### Level 1: Raw Data (in `preload_all_data()`)

#### 1. **P-site Offsets** (`PSITE_OFFSETS`)
```python
# Hash map for O(1) lookup
{
    ('P42_Brain_Ribo_rep1', 28): 12,
    ('P42_Brain_Ribo_rep1', 29): 12,
    ('P42_Brain_Ribo_rep1', 30): 13,
    ('P42_Kidney_Ribo_rep1', 28): 12,
    ...
}
```
- **Source**: `media/uorf_psite_offset.csv`
- **Why**: Instant lookup instead of filtering DataFrame
- **Speed**: O(1) instead of O(n)

#### 2. **Stop Codon Types** (`STOP_CODON_TYPES`)
```python
# Hash map for O(1) lookup
{
    'Actb': 'TAA',
    'Gapdh': 'TGA',
    'Rpl13a': 'TAG',
    ...
}
```
- **Source**: `media/stopcodons.gene_stopcodons.per_gene_majority.tsv`
- **Why**: Instant lookup for filtering genes by stop codon type
- **Speed**: O(1) instead of O(n)

#### 3. **Gene Lengths** (`GENE_LENGTHS`)
```python
# Hash map for O(1) lookup
{
    'Actb': 1128,
    'Gapdh': 1002,
    'Rpl13a': 645,
    ...
}
```
- **Source**: `media/gencode.vM25.annotation.gtf` (CDS features)
- **Why**: Needed for PCA normalization (TPM calculation)
- **Speed**: O(1) instead of reading GTF every time

#### 4. **CDS End Positions** (`CDS_END_POSITIONS`)
```python
# Hash map for O(1) lookup
{
    'Actb': 1237,      # Position where stop codon is located
    'Gapdh': 989,
    'Rpl13a': 723,
    ...
}
```
- **Source**: Computed from first parquet file (CDS region max end_position)
- **Why**: Critical for stop codon readthrough analysis - this is where position 0 is
- **Speed**: Computed once, used for all files

#### 5. **All Parquet Files** (`PARQUET_DATA`)
```python
# All parquet files loaded into memory
{
    'parquet:P42_Brain_Ribo_rep1.parquet': DataFrame(...),
    'parquet:P42_Kidney_Ribo_rep1.parquet': DataFrame(...),
    'mrna:P42_Brain_mRNA_rep1.parquet': DataFrame(...),
    ...
}
```
- **Source**: `media/parquetFiles/` and `media/mrnaParquetFiles/`
- **Why**: Avoid disk I/O for every analysis
- **Memory**: ~500MB - 2GB depending on number of files

### Level 2: Pre-Computed Results (in `precompute_all_analyses()`)

#### Stop Codon Readthrough Results
```python
PRECOMPUTED_RESULTS['stop_codon_readthrough'] = {
    frozenset(['P42_Brain_Ribo_rep1.parquet']): DataFrame(
        # This is the EXACT CSV that would be plotted
        columns=['position', 'experiment', 'normalized_count', 'stop_codon_type']
        # position: -60 to +30
        # normalized_count: RPM values (already summed across genes)
        # stop_codon_type: 'TAA', 'TAG', or 'TGA'
    ),
    frozenset(['P42_Kidney_Ribo_rep1.parquet']): DataFrame(...),
    ...
}
```

**What this means:**
- When user selects "P42_Brain_Ribo_rep1" and clicks "Generate Plot"
- System checks: "Do I have pre-computed results for this file?"
- If YES: Retrieve the CSV and plot it (< 1 second) ⚡
- If NO: Compute on-the-fly (~3-5 seconds)

## Performance Comparison

### Scenario 1: No Caching (Old System)
```
User clicks "Generate Plot"
  ↓
Read parquet file from disk (2-3 seconds)
  ↓
Filter for CDS/UTR3 regions (0.5 seconds)
  ↓
Load P-site offsets CSV (0.5 seconds)
  ↓
Filter offsets for this experiment (0.2 seconds)
  ↓
Load stop codon types TSV (0.3 seconds)
  ↓
Filter genes by stop codon type (0.5 seconds)
  ↓
Calculate CDS end positions (1 second)
  ↓
Apply P-site offsets (1 second)
  ↓
Aggregate across genes (2 seconds)
  ↓
Create plot (0.5 seconds)
  ↓
TOTAL: ~10-12 seconds
```

### Scenario 2: Level 1 Caching Only
```
User clicks "Preprocess All Files" (one-time: 60 seconds)
  ↓
[All data loaded into memory]
  ↓
User clicks "Generate Plot"
  ↓
Retrieve parquet from memory (0.1 seconds)
  ↓
Filter for CDS/UTR3 regions (0.3 seconds)
  ↓
Get P-site offsets from hash map (0.001 seconds)
  ↓
Get stop codon types from hash map (0.001 seconds)
  ↓
Get CDS end positions from hash map (0.001 seconds)
  ↓
Apply P-site offsets (0.5 seconds)
  ↓
Aggregate across genes (1.5 seconds)
  ↓
Create plot (0.3 seconds)
  ↓
TOTAL: ~3-4 seconds
```

### Scenario 3: Level 1 + Level 2 Caching (New System)
```
User clicks "Preprocess All Files" (one-time: 5-10 minutes)
  ↓
[All data loaded + All analyses pre-computed]
  ↓
User clicks "Generate Plot"
  ↓
Check pre-computed results (0.001 seconds)
  ↓
Retrieve CSV from memory (0.01 seconds)
  ↓
Create plot (0.3 seconds)
  ↓
TOTAL: < 1 second ⚡⚡⚡
```

## Memory Usage

### Level 1 Only
- **P-site offsets**: ~10 KB (hash map)
- **Stop codon types**: ~500 KB (20,000 genes)
- **Gene lengths**: ~500 KB (20,000 genes)
- **CDS end positions**: ~500 KB (20,000 genes)
- **Parquet files**: ~50-100 MB per file × 10 files = **500 MB - 1 GB**
- **TOTAL**: ~1-2 GB

### Level 1 + Level 2
- **Level 1**: ~1-2 GB
- **Pre-computed CSVs**: ~1-5 MB per file × 10 files = **10-50 MB**
- **TOTAL**: ~1-2 GB (negligible increase)

## When to Use Each Level

### Use Level 1 Only If:
- You have limited time for preprocessing
- You're frequently changing analysis parameters
- You want moderate speedup (3-4 seconds instead of 10-12 seconds)

### Use Level 1 + Level 2 If:
- You want MAXIMUM speed (< 1 second plots)
- You're doing lots of exploratory analysis
- You don't mind waiting 5-10 minutes for initial preprocessing
- Analysis parameters are stable

## How to Use

### In Your Django App

```python
# When user clicks "Preprocess All Files"
from riboApp.analysis import data_loader

# Option 1: Just load raw data (faster preprocessing)
data_loader.preload_all_data()  # ~60 seconds

# Option 2: Load raw data + pre-compute all analyses (slower preprocessing, instant plots)
data_loader.preload_all_data()        # ~60 seconds
data_loader.precompute_all_analyses() # ~5-10 minutes
```

### In Analysis Modules

```python
# stop_codon_readthrough.py
def generate_stop_codon_readthrough_plots(selected_files):
    # Check for pre-computed results first
    csv_data = data_loader.get_precomputed_result('stop_codon_readthrough', selected_files)
    
    if csv_data is not None:
        # Instant! Just plot the cached CSV
        plot_html = create_plot(csv_data)
        return plot_html, None, csv_data
    
    # Not cached, compute now
    # ... do analysis ...
    
    # Cache the result for next time
    data_loader.store_precomputed_result('stop_codon_readthrough', selected_files, csv_data)
    
    return plot_html, None, csv_data
```

## Cache Invalidation

All caches expire after **5 minutes** by default. You can:

1. **Clear all caches manually**:
   ```python
   data_loader.clear_all_caches()
   ```

2. **Re-preprocess** when you upload new files:
   - Upload new files
   - Click "Preprocess All Files"
   - System will reload everything

## Future Improvements

1. **Persistent caching** - Save pre-computed results to disk (pickle/parquet)
2. **Incremental updates** - Only recompute when files change
3. **Multi-threading** - Parallelize pre-computation
4. **Progress bar** - Show progress during preprocessing
5. **Selective precomputation** - Let user choose which analyses to pre-compute

## Summary

**The key insight**: Instead of computing analysis results every time the user requests a plot, we **pre-compute the exact CSV data that will be plotted** and cache it. When the user requests a plot, we just retrieve the CSV and plot it instantly.

This is like the difference between:
- **Old way**: Cooking a meal from scratch every time someone orders
- **New way**: Pre-cooking meals and just reheating when someone orders

The preprocessing takes longer (5-10 minutes), but every subsequent plot is **instant** (< 1 second).

