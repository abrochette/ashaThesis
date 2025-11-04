"""
Data Getter Utilities Module

This module contains all getter and loader functions for retrieving data from parquet files,
cache, and other sources. It keeps views.py clean by centralizing all data retrieval logic.

Functions are organized by category:
- File listing and availability
- Gene counts (various formats)
- Read length data
- Region-specific data
- Cached data retrieval
- Metadata retrieval
"""

import os
import pickle
import pandas as pd
import pyarrow.parquet as pq
from django.core.cache import cache
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PARQUET_FOLDER = "media/parquetFiles/"
MRNA_FOLDER = "media/mrnaFiles/"
PICKLE_FOLDER = "media/parquetPickles/"
MRNA_PICKLE_FOLDER = "media/mrnaPickles/"
OFFSET_CSV = "media/uorf_psite_offset.csv"
STOP_CODON_TSV = "media/stopcodons.gene_stopcodons.per_gene_majority.tsv"

# Cache timeout in seconds (5 minutes)
CACHE_TIMEOUT = 300

# Global caches
_AVAILABLE_FILES_CACHE = None
_AVAILABLE_FILES_CACHE_TIMESTAMP = None
_PSITE_OFFSETS_CACHE = None
_PSITE_OFFSETS_CACHE_TIMESTAMP = None


# ============================================================================
# FILE LISTING AND AVAILABILITY
# ============================================================================

def get_available_parquet_files():
    """Get list of available parquet files"""
    parquet_files, _ = get_cached_available_files()
    return parquet_files


def get_available_mrna_parquet_files():
    """Get list of available mRNA parquet files"""
    _, mrna_files = get_cached_available_files()
    return mrna_files


def get_cached_available_files():
    """Get available files from global cache or scan if needed"""
    global _AVAILABLE_FILES_CACHE, _AVAILABLE_FILES_CACHE_TIMESTAMP
    
    import time
    current_time = time.time()
    
    # Check cache
    if (_AVAILABLE_FILES_CACHE is not None and 
        _AVAILABLE_FILES_CACHE_TIMESTAMP is not None and
        current_time - _AVAILABLE_FILES_CACHE_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached file lists")
        return _AVAILABLE_FILES_CACHE
    
    # Scan directories
    print("📊 Scanning for available files...")
    parquet_files = []
    mrna_files = []
    
    if os.path.exists(PARQUET_FOLDER):
        parquet_files = sorted([f for f in os.listdir(PARQUET_FOLDER) if f.endswith(".parquet")])
    
    if os.path.exists(MRNA_FOLDER):
        mrna_files = sorted([f for f in os.listdir(MRNA_FOLDER) if f.endswith(".parquet")])
    
    _AVAILABLE_FILES_CACHE = (parquet_files, mrna_files)
    _AVAILABLE_FILES_CACHE_TIMESTAMP = current_time
    
    print(f"💾 Found {len(parquet_files)} parquet files and {len(mrna_files)} mRNA files")
    return parquet_files, mrna_files


# ============================================================================
# GENE COUNTS - BASIC
# ============================================================================

def load_or_build_gene_counts_dict(parquet_filename):
    """Load or build gene counts dictionary with pickle caching"""
    os.makedirs(PICKLE_FOLDER, exist_ok=True)
    
    parquet_path = os.path.join(PARQUET_FOLDER, parquet_filename)
    base_name = os.path.splitext(parquet_filename)[0]
    pickle_path = os.path.join(PICKLE_FOLDER, f"{base_name}.pkl")
    
    # Check if pickle exists and is newer than parquet
    if os.path.exists(pickle_path):
        parquet_mtime = os.path.getmtime(parquet_path)
        pickle_mtime = os.path.getmtime(pickle_path)
        if pickle_mtime > parquet_mtime:
            with open(pickle_path, "rb") as f:
                print(f"Loading gene_counts_dict from pickle for {parquet_filename}")
                return pickle.load(f)
    
    # Build from parquet
    print(f"Building gene_counts_dict from parquet: {parquet_filename}")
    df = pq.read_table(parquet_path, columns=["gene_name", "read_count"]).to_pandas()
    gene_counts = df.groupby("gene_name", as_index=False)["read_count"].sum()
    gene_counts_dict = dict(zip(gene_counts["gene_name"], gene_counts["read_count"]))
    
    # Save to pickle
    with open(pickle_path, "wb") as f:
        pickle.dump(gene_counts_dict, f)
        print(f"Saved pickle: {pickle_path}")
    
    return gene_counts_dict


def get_total_read_count(filename, file_type="riboseq"):
    """Get total read count from a parquet file for normalization"""
    if file_type == "riboseq":
        file_path = os.path.join(PARQUET_FOLDER, filename)
    else:  # mrna
        file_path = os.path.join(MRNA_FOLDER, filename)
    
    try:
        df = pq.read_table(file_path, columns=["read_count"]).to_pandas()
        total_reads = df["read_count"].sum()
        print(f"Total reads in {filename}: {total_reads}")
        return total_reads
    except Exception as e:
        print(f"❌ Error reading {filename}: {str(e)}")
        return 0


# ============================================================================
# GENE COUNTS - WITH REGIONS
# ============================================================================

def get_region_gene_counts(filename, file_type="riboseq"):
    """Get gene counts by region from a parquet file

    Returns nested dictionary: {gene_name: {region: count}}
    """
    if file_type == "riboseq":
        file_path = os.path.join(PARQUET_FOLDER, filename)
    else:  # mrna
        file_path = os.path.join(MRNA_FOLDER, filename)

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return {}

    try:
        # Read parquet file with region information
        df = pq.read_table(file_path, columns=["gene_name", "read_count", "region"]).to_pandas()

        # Group by gene and region, sum read counts
        region_counts = df.groupby(['gene_name', 'region'])['read_count'].sum().reset_index()

        # Convert to nested dictionary: {gene_name: {region: count}}
        result = {}
        for _, row in region_counts.iterrows():
            gene = row['gene_name']
            region = row['region']
            count = row['read_count']

            if gene not in result:
                result[gene] = {}
            result[gene][region] = count

        print(f"📊 Loaded region-specific counts for {len(result)} genes from {filename}")
        return result

    except Exception as e:
        print(f"❌ Error reading {filename}: {str(e)}")
        return {}


def get_mrna_gene_counts_dict(mrna_filename):
    """Get or create gene counts dictionary for mRNA file with caching"""
    os.makedirs(MRNA_PICKLE_FOLDER, exist_ok=True)
    
    mrna_path = os.path.join(MRNA_FOLDER, mrna_filename)
    pickle_path = os.path.join(MRNA_PICKLE_FOLDER, mrna_filename.replace('.parquet', '.pkl'))
    
    # Check if pickle exists and is newer
    if os.path.exists(pickle_path):
        mrna_mtime = os.path.getmtime(mrna_path)
        pickle_mtime = os.path.getmtime(pickle_path)
        if pickle_mtime > mrna_mtime:
            with open(pickle_path, "rb") as f:
                print(f"Loading mRNA gene counts from pickle: {mrna_filename}")
                return pickle.load(f)
    
    # Build from parquet
    print(f"Building mRNA gene counts from parquet: {mrna_filename}")
    df = pq.read_table(mrna_path, columns=["gene_name", "read_count"]).to_pandas()
    gene_counts = df.groupby("gene_name", as_index=False)["read_count"].sum()
    gene_counts_dict = dict(zip(gene_counts["gene_name"], gene_counts["read_count"]))
    
    # Save to pickle
    with open(pickle_path, "wb") as f:
        pickle.dump(gene_counts_dict, f)
    
    return gene_counts_dict


def get_gene_counts_with_regions(file1, file2, cds_only=False):
    """Get gene counts for two files with region information for colored plotting"""
    import pandas as pd

    ribo_counts1 = get_region_gene_counts(file1, "riboseq")
    ribo_counts2 = get_region_gene_counts(file2, "riboseq")

    data_rows = []
    for gene in set(ribo_counts1.keys()) & set(ribo_counts2.keys()):
        regions1 = ribo_counts1[gene]
        regions2 = ribo_counts2[gene]
        common_regions = set(regions1.keys()) & set(regions2.keys())

        for region in common_regions:
            if cds_only and region != "CDS":
                continue

            count1 = regions1[region]
            count2 = regions2[region]
            region_name = region
            if region == "UTR5":
                region_name = "5UTR"
            elif region == "UTR3":
                region_name = "3UTR"

            data_rows.append({
                "gene_name": gene,
                "read_count_x": count1,
                "read_count_y": count2,
                "region": region_name
            })

    df = pd.DataFrame(data_rows)
    region_text = "CDS-only" if cds_only else "all regions"
    print(f"🎨 Processed {len(df)} gene-region combinations for {file1} and {file2} ({region_text})")
    return df


# ============================================================================
# READ LENGTH DATA
# ============================================================================

def get_read_length_distribution(selected_files):
    """Get read length distribution for selected files"""
    if not selected_files:
        return None, "No files selected!"
    
    # Use cache key for the combination of files
    files_key = "_".join(sorted(selected_files))
    cache_key = f"read_length_dist_{files_key}"
    
    cached_plots = cache.get(cache_key)
    if cached_plots is not None:
        print(f"Loaded read length distribution plots from cache for {files_key}")
        return cached_plots, None
    
    all_distributions = {}
    
    for selected_file in selected_files:
        file_path = os.path.join(PARQUET_FOLDER, selected_file)
        if not os.path.exists(file_path):
            continue
        
        try:
            pq_file = pq.ParquetFile(file_path)
            read_lengths = []
            
            for batch in pq_file.iter_batches(batch_size=100000, columns=["read_length"]):
                df_chunk = batch.to_pandas()
                read_lengths.extend(df_chunk["read_length"].tolist())
            
            if read_lengths:
                read_length_counts = pd.Series(read_lengths).value_counts().sort_index()
                file_basename = os.path.splitext(selected_file)[0]
                all_distributions[file_basename] = {
                    'lengths': read_length_counts.index.tolist(),
                    'counts': read_length_counts.values.tolist(),
                    'total_reads': sum(read_length_counts.values)
                }
        except Exception as e:
            print(f"Error processing {selected_file}: {str(e)}")
            continue
    
    return all_distributions, None


# ============================================================================
# PERSISTENT CACHE DIRECTORY
# ============================================================================

from pathlib import Path
PERSISTENT_CACHE_DIR = Path(os.path.dirname(__file__)).parent.parent / "media" / ".persistent_cache"
PERSISTENT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_persistent_cache_file(cache_key):
    """Get the file path for a persistent cache key"""
    return PERSISTENT_CACHE_DIR / f"{cache_key}.pkl"


def _load_persistent_cache(cache_key):
    """Load data from persistent pickle cache"""
    cache_file = _get_persistent_cache_file(cache_key)
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
                print(f"⚡ Loaded {cache_key} from persistent cache")
                return data
        except Exception as e:
            print(f"⚠️ Error loading persistent cache {cache_key}: {e}")
    return None


def _save_persistent_cache(cache_key, data):
    """Save data to persistent pickle cache"""
    try:
        cache_file = _get_persistent_cache_file(cache_key)
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
            print(f"💾 Saved {cache_key} to persistent cache")
    except Exception as e:
        print(f"⚠️ Error saving persistent cache {cache_key}: {e}")


# ============================================================================
# CACHED DATA RETRIEVAL
# ============================================================================

def get_cached_gene_counts(filename, file_type="riboseq", cds_only=False):
    """Fast retrieval of gene counts from cache (persistent + in-memory)"""
    if cds_only:
        cache_key = f"preprocess_{file_type}_{filename}_cds_gene_counts"
        count_column = "cds_count"
    else:
        cache_key = f"preprocess_{file_type}_{filename}_gene_counts"
        count_column = "total_count"

    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        df = pd.DataFrame(cached_data)
        if count_column != "total_count" and count_column in df.columns:
            df = df.rename(columns={count_column: "total_count"})
        return df

    # Fallback to in-memory cache
    cached_data = cache.get(cache_key)
    if cached_data:
        df = pd.DataFrame(cached_data)
        if count_column != "total_count" and count_column in df.columns:
            df = df.rename(columns={count_column: "total_count"})
        return df

    return pd.DataFrame()


def get_cached_file_metadata(filename, file_type="riboseq"):
    """Get file metadata from cache (persistent + in-memory)"""
    cache_key = f"preprocess_{file_type}_{filename}_metadata"

    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        return cached_data

    # Fallback to in-memory cache
    return cache.get(cache_key, {})


def get_cached_read_length_data(filename, file_type="riboseq"):
    """Fast retrieval of read length distribution from cache (persistent + in-memory)"""
    cache_key = f"preprocess_{file_type}_{filename}_read_length"

    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)

    # Fallback to in-memory cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_cds_data(filename):
    """Fast retrieval of CDS data for metagene analysis (persistent + in-memory)"""
    cache_key = f"preprocess_riboseq_{filename}_cds_data"

    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)

    # Fallback to in-memory cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_region_stats(filename, file_type="riboseq"):
    """Fast retrieval of region statistics from cache (persistent + in-memory)"""
    cache_key = f"preprocess_{file_type}_{filename}_region_stats"

    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)

    # Fallback to in-memory cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_psite_data(filename):
    """Fast retrieval of P-site enhanced data for metagene analysis (persistent + in-memory)"""
    cache_key = f"preprocess_riboseq_{filename}_psite_data"

    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)

    # Fallback to in-memory cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return pd.DataFrame(cached_data)
    return pd.DataFrame()


def get_cached_plot(cache_key):
    """Get cached plot HTML (persistent + in-memory)"""
    # 🚀 Try persistent cache first
    cached_data = _load_persistent_cache(cache_key)
    if cached_data:
        return cached_data

    # Fallback to in-memory cache
    return cache.get(cache_key)


def set_cached_plot(cache_key, plot_html, timeout=None):
    """Set cached plot HTML (both persistent and in-memory)"""
    _save_persistent_cache(cache_key, plot_html)  # 🚀 Persistent
    cache.set(cache_key, plot_html, timeout=timeout)  # In-memory


def clear_delta_analysis_cache():
    """Clear all delta analysis cached plots from persistent cache"""
    import glob

    # Clear from persistent cache directory
    cache_files = glob.glob(str(PERSISTENT_CACHE_DIR / "delta_analysis_*.pkl"))
    cleared_count = 0

    for cache_file in cache_files:
        try:
            os.remove(cache_file)
            print(f"🗑️ Deleted delta analysis persistent cache: {cache_file}")
            cleared_count += 1
        except Exception as e:
            print(f"⚠️ Error deleting cache file {cache_file}: {e}")

    # Also clear from Django in-memory cache by deleting all delta_analysis keys
    # We need to iterate through and delete manually since we can't list all keys
    # Instead, we'll just clear the entire cache as a fallback
    try:
        cache.clear()
        print(f"🗑️ Cleared Django in-memory cache")
    except Exception as e:
        print(f"⚠️ Error clearing in-memory cache: {e}")

    print(f"🗑️ Cleared {cleared_count} delta analysis cached plots")


# ============================================================================
# METADATA AND OFFSETS
# ============================================================================

def get_cached_psite_offsets():
    """Get P-site offsets from global cache or load if needed"""
    global _PSITE_OFFSETS_CACHE, _PSITE_OFFSETS_CACHE_TIMESTAMP
    
    import time
    current_time = time.time()
    
    if (_PSITE_OFFSETS_CACHE is not None and 
        _PSITE_OFFSETS_CACHE_TIMESTAMP is not None and
        current_time - _PSITE_OFFSETS_CACHE_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached P-site offsets")
        return _PSITE_OFFSETS_CACHE
    
    print("📖 Loading P-site offsets from CSV...")
    
    if os.path.exists(OFFSET_CSV):
        offsets_df = pd.read_csv(OFFSET_CSV)
        _PSITE_OFFSETS_CACHE = offsets_df
        _PSITE_OFFSETS_CACHE_TIMESTAMP = current_time
        print(f"✅ Loaded P-site offsets for {len(offsets_df)} entries")
        return offsets_df
    else:
        print("⚠️ P-site offset CSV not found")
        return pd.DataFrame()


def load_selected_genes():
    """Load selected genes from database"""
    from riboApp.models import SelectedGene
    selected_genes = SelectedGene.objects.values_list('gene_name', flat=True)
    return set(selected_genes)

