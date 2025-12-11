"""
Genome Cache Module

Caches GTF and FASTA data to pickle files for instant loading.
This avoids re-parsing large GTF/FASTA files on every analysis.

When user clicks "Preprocess All Files", this module:
1. Parses GTF file once and saves to pickle
2. Parses FASTA file once and saves to pickle
3. All future analyses load from pickle (instant!)

This is a one-time cost that makes all analyses much faster.
"""

import os
import pickle
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Try to use GTF file from S3 download location first (/tmp on AWS), then fall back to media folder
_GTF_FILE_S3 = Path("/tmp/gencode.vM25.annotation.gtf")
_GTF_FILE_LOCAL = BASE_DIR / "media" / "gencode.vM25.annotation.gtf"
GTF_FILE = _GTF_FILE_S3 if _GTF_FILE_S3.exists() else _GTF_FILE_LOCAL

FASTA_FILE = BASE_DIR / "media" / "gencode.vM25.transcripts.fa"
CACHE_DIR = BASE_DIR / "media" / ".genome_cache"

# Pickle file paths
GTF_PICKLE = CACHE_DIR / "gtf_data.pkl"
FASTA_PICKLE = CACHE_DIR / "fasta_data.pkl"
GENE_LENGTHS_PICKLE = CACHE_DIR / "gene_lengths.pkl"

# Global caches
_GTF_DATA = None
_FASTA_DATA = None
_GENE_LENGTHS = None


def ensure_cache_dir():
    """Create cache directory if it doesn't exist"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cache_gtf_data():
    """
    Parse GTF file and cache to pickle.
    This is called once when user clicks "Preprocess All Files".
    """
    print("📖 Parsing GTF file (this may take a minute)...")
    
    if not GTF_FILE.exists():
        print(f"❌ GTF file not found: {GTF_FILE}")
        return None
    
    ensure_cache_dir()
    
    # Parse GTF
    col_names = ["seqname", "source", "feature", "start", "end", "score", "strand", "frame", "attribute"]
    gtf_data = pd.read_csv(GTF_FILE, sep="\t", names=col_names, comment="#")
    
    # Save to pickle
    with open(GTF_PICKLE, 'wb') as f:
        pickle.dump(gtf_data, f)
    
    print(f"✅ Cached GTF data ({len(gtf_data)} rows)")
    return gtf_data


def load_gtf_data():
    """Load GTF data from pickle or parse if not cached"""
    global _GTF_DATA
    
    if _GTF_DATA is not None:
        return _GTF_DATA
    
    # Try to load from pickle
    if GTF_PICKLE.exists():
        print("⚡ Loading GTF from cache...")
        with open(GTF_PICKLE, 'rb') as f:
            _GTF_DATA = pickle.load(f)
        print(f"✅ Loaded GTF data ({len(_GTF_DATA)} rows)")
        return _GTF_DATA
    
    # Fall back to parsing
    print("⚠️ GTF cache not found, parsing file...")
    return cache_gtf_data()


def cache_fasta_data():
    """
    DEPRECATED: FASTA data is not used in any analysis.
    This function is kept for backward compatibility but does nothing.

    The FASTA file contains transcript sequences, but the analysis only needs:
    - GTF annotations (for gene positions)
    - Gene lengths (extracted from GTF)
    - Parquet files (for ribosome profiling data)

    Caching the entire FASTA file (150,000+ sequences) was causing:
    - 15+ minutes preprocessing time
    - Excessive memory usage
    - Unnecessary disk I/O
    """
    print("⏭️  Skipping FASTA caching (not used in analysis)")
    return None


def load_fasta_data():
    """
    DEPRECATED: FASTA data is not used in any analysis.
    This function is kept for backward compatibility but returns None.
    """
    print("⏭️  FASTA data is not used in analysis (returning None)")
    return None


def cache_gene_lengths():
    """
    Extract gene lengths from GTF and cache to pickle.
    This is called once when user clicks "Preprocess All Files".
    """
    print("📊 Extracting gene lengths from GTF...")
    
    ensure_cache_dir()
    
    # Load GTF data
    gtf_data = load_gtf_data()
    if gtf_data is None:
        return None
    
    # Extract gene lengths
    gene_lengths = {}
    cds_data = gtf_data[gtf_data["feature"] == "CDS"]
    
    for _, row in cds_data.iterrows():
        # Extract gene_name from attributes
        attrs = row["attribute"]
        for attr in attrs.split(';'):
            attr = attr.strip()
            if attr.startswith('gene_name'):
                gene_name = attr.split('"')[1]
                length = row["end"] - row["start"] + 1
                
                # Accumulate lengths for genes with multiple CDS regions
                if gene_name in gene_lengths:
                    gene_lengths[gene_name] += length
                else:
                    gene_lengths[gene_name] = length
                break
    
    # Save to pickle
    with open(GENE_LENGTHS_PICKLE, 'wb') as f:
        pickle.dump(gene_lengths, f)
    
    print(f"✅ Cached gene lengths for {len(gene_lengths)} genes")
    return gene_lengths


def load_gene_lengths():
    """Load gene lengths from pickle or extract if not cached"""
    global _GENE_LENGTHS
    
    if _GENE_LENGTHS is not None:
        return _GENE_LENGTHS
    
    # Try to load from pickle
    if GENE_LENGTHS_PICKLE.exists():
        print("⚡ Loading gene lengths from cache...")
        with open(GENE_LENGTHS_PICKLE, 'rb') as f:
            _GENE_LENGTHS = pickle.load(f)
        print(f"✅ Loaded gene lengths for {len(_GENE_LENGTHS)} genes")
        return _GENE_LENGTHS
    
    # Fall back to extracting
    print("⚠️ Gene lengths cache not found, extracting from GTF...")
    return cache_gene_lengths()


def cache_all_genome_data():
    """
    Cache all genome data at once.
    Call this when user clicks "Preprocess All Files".

    OPTIMIZATION: Removed FASTA caching (not used in analysis).
    This reduces preprocessing time from 15+ minutes to 2-3 minutes.
    """
    print("\n" + "="*80)
    print("🧬 CACHING GENOME DATA...")
    print("="*80 + "\n")

    start_time = __import__('time').time()

    cache_gtf_data()
    # REMOVED: cache_fasta_data()  # Not used in analysis, saves 15+ minutes!
    cache_gene_lengths()

    elapsed = __import__('time').time() - start_time
    print("\n" + "="*80)
    print(f"✅ GENOME DATA CACHED in {elapsed:.2f} seconds")
    print("="*80 + "\n")


def clear_genome_cache():
    """Clear all cached genome data"""
    global _GTF_DATA, _FASTA_DATA, _GENE_LENGTHS
    
    _GTF_DATA = None
    _FASTA_DATA = None
    _GENE_LENGTHS = None
    
    # Delete pickle files
    for pickle_file in [GTF_PICKLE, FASTA_PICKLE, GENE_LENGTHS_PICKLE]:
        if pickle_file.exists():
            pickle_file.unlink()
    
    print("🗑️ Genome cache cleared")

