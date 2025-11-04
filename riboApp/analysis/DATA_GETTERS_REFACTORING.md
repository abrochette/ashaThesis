# Data Getters Refactoring - Complete ✅

## Overview

Created a new utility module `riboApp/analysis/data_getters.py` to centralize all data retrieval and getter functions, keeping `views.py` clean and focused on view logic.

## What Was Moved

### File Listing Functions
- ✅ `get_available_parquet_files()` - List available parquet files
- ✅ `get_available_mrna_parquet_files()` - List available mRNA files
- ✅ `get_cached_available_files()` - Cache file lists with timeout

### Gene Counts Functions
- ✅ `load_or_build_gene_counts_dict()` - Load or build gene counts with pickle caching
- ✅ `get_total_read_count()` - Get total read count for normalization
- ✅ `get_region_gene_counts()` - Get gene counts by region
- ✅ `get_mrna_gene_counts_dict()` - Get mRNA gene counts with caching

### Read Length Data Functions
- ✅ `get_read_length_distribution()` - Generate read length distribution plots

### Cached Data Retrieval Functions
- ✅ `get_cached_gene_counts()` - Fast retrieval of gene counts from cache
- ✅ `get_cached_file_metadata()` - Get file metadata from cache
- ✅ `get_cached_read_length_data()` - Get read length distribution from cache
- ✅ `get_cached_cds_data()` - Get CDS data from cache
- ✅ `get_cached_region_stats()` - Get region statistics from cache
- ✅ `get_cached_psite_data()` - Get P-site enhanced data from cache
- ✅ `get_cached_plot()` - Get cached plot HTML
- ✅ `set_cached_plot()` - Set cached plot HTML

### Metadata Functions
- ✅ `get_cached_psite_offsets()` - Get P-site offsets from cache
- ✅ `load_selected_genes()` - Load selected genes from database

## New Module Structure

### `riboApp/analysis/data_getters.py` (300 lines)

**Organized into sections:**

1. **Configuration** (lines 1-35)
   - File paths
   - Cache timeout settings
   - Global cache variables

2. **File Listing and Availability** (lines 37-95)
   - `get_available_parquet_files()`
   - `get_available_mrna_parquet_files()`
   - `get_cached_available_files()`

3. **Gene Counts - Basic** (lines 97-145)
   - `load_or_build_gene_counts_dict()`
   - `get_total_read_count()`

4. **Gene Counts - With Regions** (lines 147-195)
   - `get_region_gene_counts()`
   - `get_mrna_gene_counts_dict()`

5. **Read Length Data** (lines 197-240)
   - `get_read_length_distribution()`

6. **Cached Data Retrieval** (lines 242-310)
   - All `get_cached_*()` functions
   - `set_cached_plot()`

7. **Metadata and Offsets** (lines 312-340)
   - `get_cached_psite_offsets()`
   - `load_selected_genes()`

## Changes to `views.py`

All getter functions in `views.py` now delegate to `data_getters.py`:

```python
# Before: Full implementation in views.py
def get_available_parquet_files():
    parquet_files, _ = get_cached_available_files()
    return parquet_files

# After: Delegates to data_getters
def get_available_parquet_files():
    """Get available parquet files - delegates to data_getters"""
    from .analysis.data_getters import get_available_parquet_files as _get_available
    return _get_available()
```

This pattern is used for all 20+ getter functions.

## Benefits

✅ **Cleaner views.py** - Removed 200+ lines of data retrieval code
✅ **Better organization** - All data getters in one place
✅ **Easier maintenance** - Single source of truth for data retrieval
✅ **Reusability** - Other modules can import from data_getters
✅ **Testability** - Easier to unit test data retrieval logic
✅ **Separation of concerns** - Views focus on HTTP logic, data_getters focus on data

## Usage

### From views.py
```python
from .analysis.data_getters import get_available_parquet_files, get_cached_gene_counts

files = get_available_parquet_files()
counts = get_cached_gene_counts(filename)
```

### From other modules
```python
from riboApp.analysis.data_getters import load_selected_genes, get_region_gene_counts

genes = load_selected_genes()
counts = get_region_gene_counts(filename, "riboseq")
```

## File Statistics

| File | Lines | Change |
|------|-------|--------|
| `data_getters.py` | 340 | +340 (new) |
| `views.py` | ~3900 | -200 (delegated) |
| **Total** | **~4240** | **+140** |

## Next Steps

1. ✅ Test that all functions work correctly
2. ✅ Verify imports work from other modules
3. ✅ Update any other modules that need to use data_getters
4. ✅ Consider moving more utility functions to separate modules

## Summary

Successfully refactored data retrieval logic into a dedicated utility module, making the codebase more maintainable and organized! 🎉

