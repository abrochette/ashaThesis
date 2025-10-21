# Data Loader Script - Detailed Explanation

## Overview

The `data_loader.py` script is the **central hub** for all data loading and caching in the application. It manages:
- Metadata (P-site offsets, stop codon types)
- Genome data (GTF, gene lengths)
- Parquet files (ribosome profiling data)
- CDS end positions (for stop codon analysis)
- Pre-computed analysis results (optional caching)

## Current Architecture

### Global Data Structures (Lines 40-69)

```python
# Main caches
PARQUET_DATA = {}                    # {filename: DataFrame}
GTF_DATA = None                      # GTF DataFrame
GENE_LENGTHS = {}                    # {gene_name: length}
PSITE_OFFSETS = {}                   # {(experiment, read_length): offset}
STOP_CODON_TYPES = {}                # {gene_name: 'TAA'/'TAG'/'TGA'}
CDS_END_POSITIONS = {}               # {gene_name: end_position}
AVAILABLE_FILES = {...}              # List of available files

# Pre-computed results (OPTIONAL - can be removed)
PRECOMPUTED_RESULTS = {
    'stop_codon_readthrough': {},
    'psite_metagene': {},
    'pca': {},
}
```

## Functions Breakdown

### 1. FILE SCANNING (Lines 75-102)

**Function:** `get_available_files()`
- **Purpose:** Scan media folders for available parquet files
- **Returns:** List of parquet files and mRNA files
- **Used by:** Views to show available files to user
- **Status:** ✅ NEEDED - Keep this

---

### 2. P-SITE OFFSETS (Lines 109-151)

**Functions:**
- `load_psite_offsets()` (Line 109) - Load P-site offset CSV into hash map
- `get_psite_offset(experiment, read_length)` (Line 145) - Get offset for specific experiment

**Purpose:** Load P-site offsets used in stop codon analysis
**Used by:** `stop_codon_readthrough.py` to apply P-site corrections
**Status:** ✅ NEEDED - Keep this

---

### 3. STOP CODON TYPES (Lines 157-211)

**Functions:**
- `load_stop_codon_types()` (Line 157) - Load stop codon TSV into hash map
- `get_stop_codon_type(gene_name)` (Line 205) - Get stop codon for specific gene

**Purpose:** Load stop codon types (TAA/TAG/TGA) for each gene
**Used by:** `stop_codon_readthrough.py` to filter by stop codon type
**Status:** ✅ NEEDED - Keep this

---

### 4. GENE LENGTHS (Lines 217-244)

**Functions:**
- `load_gene_lengths()` (Line 217) - Load from genome_cache pickle
- `get_gene_length(gene_name)` (Line 238) - Get length for specific gene

**Purpose:** Load gene lengths extracted from GTF
**Used by:** Various analyses to normalize by gene length
**Status:** ✅ NEEDED - Keep this

---

### 5. CDS END POSITIONS (Lines 250-311)

**Functions:**
- `load_cds_end_positions()` (Line 250) - Compute from first parquet file
- `get_cds_end_position(gene_name)` (Line 305) - Get position for specific gene

**Purpose:** Find where stop codon is located for each gene
**Used by:** `stop_codon_readthrough.py` as reference point for relative positions
**Status:** ⚠️ POTENTIALLY UNNECESSARY - See analysis below

---

### 6. PARQUET DATA LOADING (Lines 317-351)

**Function:** `load_parquet_file(filename, folder='parquet')`
- **Purpose:** Load a single parquet file on-demand
- **Caching:** Caches in memory for 5 minutes
- **Used by:** Views when user selects files for analysis
- **Status:** ✅ NEEDED - Keep this

---

### 7. PRELOAD ALL DATA (Lines 357-396)

**Function:** `preload_all_data()`
- **Purpose:** Called when user clicks "Preprocess All Files"
- **Steps:**
  1. Load metadata (P-site offsets, stop codon types)
  2. Cache genome data (GTF, gene lengths) to pickle
  3. Compute CDS end positions
- **Time:** ~45 seconds
- **Status:** ✅ NEEDED - Keep this

---

### 8. PRE-COMPUTE ALL ANALYSES (Lines 398-451)

**Function:** `precompute_all_analyses()`
- **Purpose:** Pre-compute analysis results for ALL files
- **What it does:** Loops through all 10 parquet files and generates stop codon readthrough plots
- **Time:** 1-2 minutes per file = 10-20 minutes total
- **Status:** ❌ **NOT NEEDED - REMOVE THIS**

**Why remove it?**
- You said: "only preprocessing those things when the preprocess button is pressed"
- This function does the opposite - it pre-computes everything
- Analyses should be computed on-demand when user requests plots
- Removing this saves 10-20 minutes of preprocessing time

---

### 9. GET/STORE PRE-COMPUTED RESULTS (Lines 453-500)

**Functions:**
- `get_precomputed_result(analysis_type, selected_files)` (Line 453)
- `store_precomputed_result(analysis_type, selected_files, result_data)` (Line 482)

**Purpose:** Cache/retrieve pre-computed analysis results
**Status:** ❌ **NOT NEEDED - REMOVE THESE**

**Why remove them?**
- These are only used by `precompute_all_analyses()` which we're removing
- If we're not pre-computing, we don't need these functions
- Analyses will be computed on-demand instead

---

### 10. CLEAR CACHE (Lines 506-537)

**Function:** `clear_all_caches()`
- **Purpose:** Clear all cached data
- **Used by:** Admin functions to reset cache
- **Status:** ✅ KEEP - But update to remove PRECOMPUTED_RESULTS

---

## What to Remove

### 1. Remove `precompute_all_analyses()` (Lines 398-451)

This function is NOT called anymore (we removed it from views.py). It's dead code.

### 2. Remove `get_precomputed_result()` (Lines 453-480)

This function is only used by `precompute_all_analyses()`. If we remove that, this is dead code.

### 3. Remove `store_precomputed_result()` (Lines 482-500)

This function is only used by `precompute_all_analyses()`. If we remove that, this is dead code.

### 4. Remove PRECOMPUTED_RESULTS global variables (Lines 62-69)

These are only used by the three functions above. If we remove those functions, we don't need these globals.

### 5. Update `clear_all_caches()` (Lines 506-537)

Remove references to PRECOMPUTED_RESULTS since we're removing that.

---

## What to Keep

✅ `get_available_files()` - Needed to list files
✅ `load_psite_offsets()` - Needed for stop codon analysis
✅ `load_stop_codon_types()` - Needed for stop codon analysis
✅ `load_gene_lengths()` - Needed for all analyses
✅ `load_cds_end_positions()` - Needed for stop codon analysis
✅ `load_parquet_file()` - Needed to load data on-demand
✅ `preload_all_data()` - Needed for preprocessing
✅ `clear_all_caches()` - Needed for cache management

---

## Potential Issue: CDS_END_POSITIONS

**Question:** Is `load_cds_end_positions()` actually needed?

**Current usage:** It loads the first parquet file (60 million rows) just to compute CDS end positions.

**Alternative:** Could we get CDS end positions from GTF instead of parquet?

**Recommendation:** Check if GTF already has this information. If yes, we can:
1. Extract CDS end positions from GTF during `cache_all_genome_data()`
2. Remove the parquet loading from `load_cds_end_positions()`
3. Save 30+ seconds of preprocessing time

---

## Summary

**Current state:** 538 lines
**After cleanup:** ~350 lines (35% reduction)

**Functions to remove:**
- `precompute_all_analyses()` (54 lines)
- `get_precomputed_result()` (27 lines)
- `store_precomputed_result()` (18 lines)
- PRECOMPUTED_RESULTS globals (8 lines)

**Total savings:** ~107 lines of dead code

**Performance impact:** Preprocessing stays at ~45 seconds (no change, since we already removed the call from views.py)

---

## Next Steps

1. Remove the three functions above
2. Remove PRECOMPUTED_RESULTS globals
3. Update `clear_all_caches()` to remove PRECOMPUTED_RESULTS references
4. (Optional) Check if CDS_END_POSITIONS can be computed from GTF instead of parquet

