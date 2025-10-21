# Analysis Module System

## Overview

This directory contains modular analysis code separated from the main Django views.
The goal is to:
1. **Separate concerns** - Each analysis type has its own module
2. **Centralize data loading** - All data is loaded once and cached globally
3. **Optimize performance** - Use hash maps for O(1) lookups instead of repeated file reads

## Architecture

```
riboApp/analysis/
├── __init__.py
├── data_loader.py              # Central data loading and caching
├── stop_codon_readthrough.py   # Stop codon readthrough analysis
└── README.md                    # This file
```

## Data Loader Module (`data_loader.py`)

### Global Data Structures

All data is stored in global dictionaries for fast access:

- **`PARQUET_DATA`**: `{filename: DataFrame}` - All parquet files loaded into memory
- **`PSITE_OFFSETS`**: `{(experiment, read_length): offset}` - Hash map for O(1) P-site offset lookup
- **`STOP_CODON_TYPES`**: `{gene_name: 'TAA'/'TAG'/'TGA'}` - Hash map for stop codon types
- **`GENE_LENGTHS`**: `{gene_name: length}` - Hash map for gene lengths
- **`CDS_END_POSITIONS`**: `{gene_name: position}` - Hash map for CDS end positions
- **`AVAILABLE_FILES`**: `{parquet: [...], mrna: [...]}` - List of available files

### Key Functions

#### `preload_all_data()`
Loads ALL data at once for maximum performance. Call this once at startup or when user clicks "Preprocess All Files".

```python
from riboApp.analysis import data_loader

# Preload everything
data_loader.preload_all_data()
```

#### Individual Loaders

```python
# Load P-site offsets
offsets = data_loader.load_psite_offsets()
offset = data_loader.get_psite_offset('P42_Brain_Ribo_rep1', 28)

# Load stop codon types
stop_codons = data_loader.load_stop_codon_types()
stop_type = data_loader.get_stop_codon_type('Actb')  # Returns 'TAA', 'TAG', or 'TGA'

# Load gene lengths
gene_lengths = data_loader.load_gene_lengths()
length = data_loader.get_gene_length('Actb')

# Load parquet file
df = data_loader.load_parquet_file('P42_Brain_Ribo_rep1.parquet', folder='parquet')
```

#### Cache Management

```python
# Clear all caches
data_loader.clear_all_caches()
```

### Caching Strategy

- **5-minute timeout** for all caches
- **Automatic reloading** if cache expires
- **Session-based** - caches persist across requests within the same Python process

## Stop Codon Readthrough Module (`stop_codon_readthrough.py`)

### Main Function

```python
from riboApp.analysis import stop_codon_readthrough

# Generate plots
plot_html, error_msg, csv_data = stop_codon_readthrough.generate_stop_codon_readthrough_plots(
    selected_files=['P42_Brain_Ribo_rep1.parquet', 'P42_Kidney_Ribo_rep1.parquet']
)
```

### How It Works

1. **Loads data** from `data_loader` module (uses cached data if available)
2. **Filters genes** by stop codon type (TAA/TAG/TGA)
3. **Includes CDS + UTR3 regions** (UTR3 contains readthrough reads)
4. **Calculates CDS end positions** (stop codon location)
5. **Applies P-site offsets** using hash map lookup
6. **Normalizes to RPM** (Reads Per Million)
7. **Aggregates across genes** by summing RPM values
8. **Creates separate plots** for each sample with three lines (TAA/TAG/TGA)

### Key Improvements

- **Uses hash maps** for P-site offset lookup instead of DataFrame filtering
- **Loads data once** from cache instead of reading files repeatedly
- **Proper stop codon alignment** using CDS end positions from transcript coordinates
- **Includes readthrough reads** from UTR3 region

## Usage in Django Views

### Example: Stop Codon Readthrough View

```python
def stop_codon_readthrough(request):
    """Stop codon readthrough analysis"""
    from .analysis import stop_codon_readthrough as scr_module
    
    if request.method == "POST":
        selected_files = request.POST.getlist("selected_files")
        
        # Use modular system
        plot_html, error_msg, csv_data = scr_module.generate_stop_codon_readthrough_plots(selected_files)
        
        # Store CSV for download
        if csv_data is not None:
            request.session['stop_codon_csv_data'] = csv_data.to_json()
    
    return render(request, "riboApp/stopCodonReadthrough.html", {
        "plot_html": plot_html,
        "error_message": error_msg,
    })
```

### Preloading Data

Users can click "Preprocess All Files" button which calls:

```python
def preprocess_all_files_view(request):
    """Preload all data at once"""
    if request.method == "POST":
        from .analysis import data_loader
        
        # Preload everything
        data_loader.preload_all_data()
        
        messages.success(request, "All data preloaded successfully!")
    
    return redirect('upload_parquet')
```

## Performance Benefits

### Before (Old System)
- Read parquet files from disk for each analysis
- Filter DataFrames repeatedly for P-site offsets
- Load GTF/TSV files multiple times
- **Slow**: ~10-30 seconds per analysis

### After (New System)
- Load all data once into memory
- Use hash maps for O(1) lookups
- Cache everything globally
- **Fast**: ~1-3 seconds per analysis (after preload)

## Future Expansion

To add a new analysis module:

1. Create `riboApp/analysis/your_analysis.py`
2. Import `data_loader` for data access
3. Implement your analysis function
4. Update the corresponding view in `views.py` to use your module

Example:

```python
# riboApp/analysis/pca_analysis.py
from . import data_loader

def generate_pca_plots(selected_files):
    # Load data from cache
    gene_lengths = data_loader.load_gene_lengths()
    
    # Your analysis code here
    ...
    
    return plot_html, error_msg, csv_data
```

## Notes

- **Thread safety**: Current implementation uses global variables, which are safe for single-threaded Django development server but may need locks for production
- **Memory usage**: Preloading all data uses more memory but provides much faster analysis
- **Cache invalidation**: Caches expire after 5 minutes or can be manually cleared

## Migration Status

- ✅ **Stop Codon Readthrough** - Migrated to new system
- ⏳ **P-site Metagene** - To be migrated
- ⏳ **PCA Analysis** - To be migrated
- ⏳ **P-site Offset** - To be migrated
- ⏳ **Gene Counts** - To be migrated
- ⏳ **Read Length Distribution** - To be migrated

