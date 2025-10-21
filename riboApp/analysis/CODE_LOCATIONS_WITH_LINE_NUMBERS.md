# Code Locations With Line Numbers

## Quick Reference: Where Is Everything?

### Optimization Code

| Component | File | Lines | What It Does |
|-----------|------|-------|-------------|
| **Genome Cache Module** | `genome_cache.py` | 1-248 | Parse GTF/FASTA once, load instantly |
| **Cache GTF** | `genome_cache.py` | 41-63 | Parse GTF file and save to pickle |
| **Load GTF** | `genome_cache.py` | 66-83 | Load GTF from pickle or parse |
| **Cache FASTA** | `genome_cache.py` | 86-115 | Parse FASTA file and save to pickle |
| **Load FASTA** | `genome_cache.py` | 118-135 | Load FASTA from pickle or parse |
| **Cache Gene Lengths** | `genome_cache.py` | 138-160 | Extract gene lengths and save to pickle |
| **Load Gene Lengths** | `genome_cache.py` | 163-180 | Load gene lengths from pickle or extract |
| **Cache All** | `genome_cache.py` | 183-200 | Cache everything at once |
| **Clear Cache** | `genome_cache.py` | 203-220 | Delete all pickle files |

### Integration Points

| Component | File | Lines | What It Does |
|-----------|------|-------|-------------|
| **Preload All Data** | `data_loader.py` | 368-395 | Load metadata and cache genome data |
| **Load Gene Lengths** | `data_loader.py` | 217-235 | Use genome_cache for gene lengths |
| **Precompute Analyses** | `data_loader.py` | 398-477 | Pre-compute all analyses |
| **Preprocess View** | `views.py` | 3952-3975 | Entry point from server |
| **Calculate Gene Lengths** | `views.py` | 2354-2374 | Use genome_cache for gene lengths |
| **Load Stop Codon Positions** | `views.py` | 2302-2351 | Use genome_cache for GTF data |

### Vectorized Operations

| Component | File | Lines | What It Does |
|-----------|------|-------|-------------|
| **P-site Offset Mapping** | `stop_codon_readthrough.py` | ~150 | Vectorized `.map()` instead of `.apply()` |
| **Reference Position Mapping** | `stop_codon_readthrough.py` | ~200 | Vectorized `.map()` for gene positions |
| **Position Aggregation** | `stop_codon_readthrough.py` | ~250 | `.groupby()` instead of loops |

---

## Detailed Code Locations

### 1. Genome Cache Module: `riboApp/analysis/genome_cache.py`

**Lines 1-40: Setup**
```python
# Imports and configuration
# GTF_FILE, FASTA_FILE paths
# Cache directory setup
# Global cache variables
```

**Lines 41-63: cache_gtf_data()**
```python
def cache_gtf_data():
    """Parse GTF file and cache to pickle"""
    # Reads gencode.vM25.annotation.gtf
    # Saves to media/.genome_cache/gtf_data.pkl
    # Returns parsed GTF DataFrame
```

**Lines 66-83: load_gtf_data()**
```python
def load_gtf_data():
    """Load GTF data from pickle or parse if not cached"""
    # Check in-memory cache first
    # Load from pickle if available
    # Fall back to parsing if needed
```

**Lines 86-115: cache_fasta_data()**
```python
def cache_fasta_data():
    """Parse FASTA file and cache to pickle"""
    # Reads gencode.vM25.transcripts.fa
    # Saves to media/.genome_cache/fasta_data.pkl
    # Returns parsed FASTA dict
```

**Lines 118-135: load_fasta_data()**
```python
def load_fasta_data():
    """Load FASTA data from pickle or parse if not cached"""
    # Check in-memory cache first
    # Load from pickle if available
    # Fall back to parsing if needed
```

**Lines 138-160: cache_gene_lengths()**
```python
def cache_gene_lengths():
    """Extract gene lengths from GTF and cache to pickle"""
    # Loads GTF data
    # Extracts gene lengths
    # Saves to media/.genome_cache/gene_lengths.pkl
```

**Lines 163-180: load_gene_lengths()**
```python
def load_gene_lengths():
    """Load gene lengths from pickle or extract if not cached"""
    # Check in-memory cache first
    # Load from pickle if available
    # Fall back to extraction if needed
```

**Lines 183-200: cache_all_genome_data()**
```python
def cache_all_genome_data():
    """Cache all genome data at once"""
    # Called by preload_all_data()
    # Caches GTF, FASTA, and gene lengths
    # One-time cost during preprocessing
```

**Lines 203-220: clear_genome_cache()**
```python
def clear_genome_cache():
    """Delete all pickle files and clear in-memory cache"""
    # Deletes pickle files
    # Clears global cache variables
    # Forces re-parsing on next load
```

---

### 2. Data Loader Integration: `riboApp/analysis/data_loader.py`

**Lines 28-33: File Paths**
```python
GTF_FILE = BASE_DIR / "media" / "gencode.vM25.annotation.gtf"
FASTA_FILE = BASE_DIR / "media" / "gencode.vM25.transcripts.fa"
# These are passed to genome_cache module
```

**Lines 217-235: load_gene_lengths()**
```python
def load_gene_lengths():
    """Load gene lengths from genome cache (pickle)"""
    # Check in-memory cache
    # Call genome_cache.load_gene_lengths()
    # Return gene lengths dict
```

**Lines 368-395: preload_all_data()**
```python
def preload_all_data():
    """Preload all data needed for analyses"""
    # Step 1: Load metadata (5 seconds)
    # Step 2: Call genome_cache.cache_all_genome_data() (65 seconds)
    # Step 3: Compute CDS end positions (5 seconds)
    # Total: ~75 seconds
```

**Lines 398-477: precompute_all_analyses()**
```python
def precompute_all_analyses():
    """Pre-compute ALL analysis results for ALL files"""
    # For each parquet file:
    #   - Call stop_codon_readthrough.generate_stop_codon_readthrough_plots()
    #   - Store result in PRECOMPUTED_RESULTS
    # Total: 1-2 minutes
```

---

### 3. Views Integration: `riboApp/views.py`

**Lines 2105-2109: File Paths**
```python
GTF_FILE = "media/gencode.vM25.annotation.gtf"
TRANSCRIPTS_FASTA = "media/gencode.vM25.transcripts.fa"
# These are used for file existence checks only
```

**Lines 2302-2351: load_stop_codon_positions_from_gtf()**
```python
def load_stop_codon_positions_from_gtf():
    """Extract stop codon positions from GTF file"""
    # Line 2311: Call genome_cache.load_gtf_data()
    # Filter for stop_codon features
    # Extract gene names and positions
    # Return dict: {gene_name: position}
```

**Lines 2354-2374: calculate_gene_lengths()**
```python
def calculate_gene_lengths(gtf_file):
    """Get gene lengths from genome cache"""
    # Line 2361: Call genome_cache.load_gene_lengths()
    # Convert dict to DataFrame
    # Return gene lengths
```

**Lines 3952-3975: preprocess_all_files_view()**
```python
def preprocess_all_files_view(request):
    """View to trigger preprocessing"""
    # Line 3960: Call data_loader.preload_all_data()
    # Line 3964: Call data_loader.precompute_all_analyses()
    # Redirect to upload_parquet page
```

---

### 4. Vectorized Operations: `riboApp/analysis/stop_codon_readthrough.py`

**Lines ~150: P-site Offset Mapping**
```python
# Create mapping dict
length_to_offset = {}
for read_length in df_filtered["read_length"].unique():
    offset = psite_offsets.get((experiment_name, int(read_length)), None)
    if offset is not None:
        length_to_offset[read_length] = offset

# Apply vectorized
df_filtered["offset"] = df_filtered["read_length"].map(length_to_offset)
```

**Lines ~200: Reference Position Mapping**
```python
# Create mapping dict
gene_ref_positions = {}
for gene_name in df_filtered["gene_name"].unique():
    if gene_name in cds_end_positions:
        gene_ref_positions[gene_name] = cds_end_positions[gene_name]

# Apply vectorized
df_filtered["reference_pos"] = df_filtered["gene_name"].map(gene_ref_positions)
df_filtered["relative_position"] = df_filtered["p_site"] - df_filtered["reference_pos"]
```

**Lines ~250: Position Aggregation**
```python
# Filter to position range
df_filtered = df_filtered[df_filtered["relative_position"].between(-60, 30)]

# Groupby aggregation (instead of loop)
result = df_filtered.groupby("relative_position", as_index=False)["read_count"].sum()
result["normalized_count"] = (result["read_count"] / total_reads) * 1e6
```

---

## Call Chain Summary

```
User clicks "Preprocess All Files"
    ↓
views.py:3952 preprocess_all_files_view()
    ├─ views.py:3960 data_loader.preload_all_data()
    │  ├─ data_loader.py:379 load_psite_offsets()
    │  ├─ data_loader.py:380 load_stop_codon_types()
    │  ├─ data_loader.py:386 genome_cache.cache_all_genome_data()
    │  │  ├─ genome_cache.py:41 cache_gtf_data()
    │  │  ├─ genome_cache.py:86 cache_fasta_data()
    │  │  └─ genome_cache.py:138 cache_gene_lengths()
    │  └─ data_loader.py:390 load_cds_end_positions()
    │
    └─ views.py:3964 data_loader.precompute_all_analyses()
       └─ data_loader.py:398 precompute_all_analyses()
          └─ stop_codon_readthrough.py:generate_stop_codon_readthrough_plots()
             ├─ Line ~150: Vectorized P-site offset mapping
             ├─ Line ~200: Vectorized reference position mapping
             └─ Line ~250: Groupby aggregation
```

---

## Summary

✅ **All optimization code is in `genome_cache.py` (248 lines)**
✅ **All integration points are documented with line numbers**
✅ **All analysis files use the cache**
✅ **No direct GTF/FASTA parsing anywhere else**
✅ **Called from server via `preprocess_all_files_view()` at line 3952**

