"""
Central Data Loader Module

This module loads all data once and caches it globally for fast access.
All analysis modules should import from this module instead of loading data themselves.

Global Data Structures:
- PARQUET_DATA: {filename: DataFrame} - All parquet files loaded into memory
- GTF_DATA: DataFrame - GTF annotations
- GENE_LENGTHS: {gene_name: length} - Gene lengths from GTF
- PSITE_OFFSETS: {(experiment, read_length): offset} - P-site offsets hash map
- STOP_CODON_TYPES: {gene_name: stop_codon} - Stop codon types (TAA/TAG/TGA)
- CDS_END_POSITIONS: {gene_name: position} - CDS end positions for stop codon analysis
- AVAILABLE_FILES: {parquet: [...], mrna: [...]} - Available data files
"""

import os
import time
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GTF_FILE = BASE_DIR / "media" / "gencode.vM25.annotation.gtf"
PARQUET_FOLDER = BASE_DIR / "media" / "parquetFiles"
MRNA_FOLDER = BASE_DIR / "media" / "mrnaParquetFiles"
STOP_CODON_TSV = BASE_DIR / "media" / "stopcodons.gene_stopcodons.per_gene_majority.tsv"
OFFSET_CSV = BASE_DIR / "media" / "uorf_psite_offset.csv"
FASTA_FILE = BASE_DIR / "media" / "gencode.vM25.transcripts.fa"

CACHE_TIMEOUT = 300  # 5 minutes

# ============================================================================
# GLOBAL DATA STRUCTURES
# ============================================================================

# Main data caches
PARQUET_DATA = {}  # {filename: DataFrame}
PARQUET_DATA_TIMESTAMP = {}  # {filename: timestamp}

GTF_DATA = None
GTF_DATA_TIMESTAMP = None

GENE_LENGTHS = {}  # {gene_name: length}
GENE_LENGTHS_TIMESTAMP = None

PSITE_OFFSETS = {}  # {(experiment, read_length): offset}
PSITE_OFFSETS_TIMESTAMP = None

STOP_CODON_TYPES = {}  # {gene_name: 'TAA'/'TAG'/'TGA'}
STOP_CODON_TYPES_TIMESTAMP = None

CDS_END_POSITIONS = {}  # {gene_name: end_position}
CDS_END_POSITIONS_TIMESTAMP = None

AVAILABLE_FILES = {'parquet': [], 'mrna': [], 'timestamp': None}



# ============================================================================
# FILE SCANNING
# ============================================================================

def get_available_files():
    """Get list of available parquet files"""
    global AVAILABLE_FILES
    
    current_time = time.time()
    
    # Check cache
    if AVAILABLE_FILES['timestamp'] and (current_time - AVAILABLE_FILES['timestamp'] < CACHE_TIMEOUT):
        print("🚀 Using cached file lists")
        return AVAILABLE_FILES['parquet'], AVAILABLE_FILES['mrna']
    
    # Scan directories
    print("📊 Scanning for available files...")
    parquet_files = []
    mrna_files = []
    
    if PARQUET_FOLDER.exists():
        parquet_files = [f.name for f in PARQUET_FOLDER.glob("*.parquet")]
    
    if MRNA_FOLDER.exists():
        mrna_files = [f.name for f in MRNA_FOLDER.glob("*.parquet")]
    
    AVAILABLE_FILES['parquet'] = sorted(parquet_files)
    AVAILABLE_FILES['mrna'] = sorted(mrna_files)
    AVAILABLE_FILES['timestamp'] = current_time
    
    print(f"💾 Found {len(parquet_files)} parquet files and {len(mrna_files)} mRNA files")
    return parquet_files, mrna_files


# ============================================================================
# P-SITE OFFSETS
# ============================================================================

def load_psite_offsets():
    """Load P-site offsets into hash map for O(1) lookup"""
    global PSITE_OFFSETS, PSITE_OFFSETS_TIMESTAMP
    
    current_time = time.time()
    
    # Check cache
    if PSITE_OFFSETS and PSITE_OFFSETS_TIMESTAMP and (current_time - PSITE_OFFSETS_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached P-site offsets")
        return PSITE_OFFSETS
    
    print(f"📖 Loading P-site offsets from: {OFFSET_CSV}")
    
    if not OFFSET_CSV.exists():
        print("⚠️ P-site offset CSV not found")
        return {}
    
    df = pd.read_csv(OFFSET_CSV)
    
    # Ensure correct column names
    if "P_site_offset" not in df.columns:
        df.columns = ["experiment", "read_length", "P_site_offset"]
    
    # Create hash map: (experiment, read_length) -> offset
    offsets = {}
    for _, row in df.iterrows():
        key = (row["experiment"], int(row["read_length"]))
        offsets[key] = int(row["P_site_offset"])
    
    PSITE_OFFSETS = offsets
    PSITE_OFFSETS_TIMESTAMP = current_time
    
    print(f"✅ Loaded {len(offsets)} P-site offset mappings")
    return offsets





# ============================================================================
# STOP CODON TYPES
# ============================================================================

def load_stop_codon_types():
    """Load stop codon types into hash map"""
    global STOP_CODON_TYPES, STOP_CODON_TYPES_TIMESTAMP
    
    current_time = time.time()
    
    # Check cache
    if STOP_CODON_TYPES and STOP_CODON_TYPES_TIMESTAMP and (current_time - STOP_CODON_TYPES_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached stop codon types")
        return STOP_CODON_TYPES
    
    print(f"📖 Loading stop codon types from: {STOP_CODON_TSV}")
    
    if not STOP_CODON_TSV.exists():
        print("⚠️ Stop codon TSV not found")
        return {}
    
    stop_codons = {}
    valid_stop_codons = {'TAA', 'TAG', 'TGA'}
    
    with open(STOP_CODON_TSV, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) != 2:
                continue
            
            gene_name, stop_codon = parts
            if stop_codon in valid_stop_codons:
                stop_codons[gene_name] = stop_codon
    
    STOP_CODON_TYPES = stop_codons
    STOP_CODON_TYPES_TIMESTAMP = current_time
    
    # Print statistics
    taa = sum(1 for sc in stop_codons.values() if sc == 'TAA')
    tag = sum(1 for sc in stop_codons.values() if sc == 'TAG')
    tga = sum(1 for sc in stop_codons.values() if sc == 'TGA')
    
    print(f"✅ Loaded stop codons for {len(stop_codons)} genes")
    print(f"   TAA: {taa}, TAG: {tag}, TGA: {tga}")
    
    return stop_codons





# ============================================================================
# GENE LENGTHS
# ============================================================================

def load_gene_lengths():
    """Load gene lengths from genome cache (pickle)"""
    global GENE_LENGTHS, GENE_LENGTHS_TIMESTAMP

    current_time = time.time()

    # Check in-memory cache
    if GENE_LENGTHS and GENE_LENGTHS_TIMESTAMP and (current_time - GENE_LENGTHS_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached gene lengths")
        return GENE_LENGTHS

    # Load from genome cache (which uses pickle for instant loading)
    from . import genome_cache
    gene_lengths = genome_cache.load_gene_lengths()

    GENE_LENGTHS = gene_lengths
    GENE_LENGTHS_TIMESTAMP = current_time

    return gene_lengths





# ============================================================================
# CDS END POSITIONS (for stop codon analysis)
# ============================================================================

def load_cds_end_positions():
    """
    Load CDS end positions from parquet files.

    This is used for stop codon analysis to find where the stop codon is located.
    Since parquet files use transcript coordinates, the CDS end position is the stop codon.

    Returns:
        dict: {gene_name: cds_end_position}
    """
    global CDS_END_POSITIONS, CDS_END_POSITIONS_TIMESTAMP

    current_time = time.time()

    # Check cache
    if CDS_END_POSITIONS and CDS_END_POSITIONS_TIMESTAMP and (current_time - CDS_END_POSITIONS_TIMESTAMP < CACHE_TIMEOUT):
        print("🚀 Using cached CDS end positions")
        return CDS_END_POSITIONS

    print("📖 Computing CDS end positions from parquet files...")

    cds_end_positions = {}

    # Get available files
    parquet_files, _ = get_available_files()

    if not parquet_files:
        print("⚠️ No parquet files found")
        return {}

    # Use the first parquet file to get CDS end positions
    # (they should be the same across all files since they're based on transcript structure)
    first_file = parquet_files[0]
    df = load_parquet_file(first_file, folder='parquet')

    if df is None:
        print("⚠️ Could not load parquet file")
        return {}

    # For each gene, find the maximum end_position in the CDS region
    for gene_name in df['gene_name'].unique():
        gene_data = df[df['gene_name'] == gene_name]
        cds_data = gene_data[gene_data['region'] == 'CDS']

        if not cds_data.empty:
            # The stop codon is at the end of the CDS region
            cds_end_positions[gene_name] = cds_data['end_position'].max()

    CDS_END_POSITIONS = cds_end_positions
    CDS_END_POSITIONS_TIMESTAMP = current_time

    print(f"✅ Computed CDS end positions for {len(cds_end_positions)} genes")
    return cds_end_positions





# ============================================================================
# PARQUET DATA LOADING
# ============================================================================

def load_parquet_file(filename, folder='parquet'):
    """Load a single parquet file into memory"""
    global PARQUET_DATA, PARQUET_DATA_TIMESTAMP
    
    current_time = time.time()
    
    # Check cache
    cache_key = f"{folder}:{filename}"
    if cache_key in PARQUET_DATA and cache_key in PARQUET_DATA_TIMESTAMP:
        if current_time - PARQUET_DATA_TIMESTAMP[cache_key] < CACHE_TIMEOUT:
            print(f"🚀 Using cached data for {filename}")
            return PARQUET_DATA[cache_key]
    
    # Determine folder
    if folder == 'parquet':
        file_path = PARQUET_FOLDER / filename
    elif folder == 'mrna':
        file_path = MRNA_FOLDER / filename
    else:
        raise ValueError(f"Unknown folder: {folder}")
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return None
    
    print(f"📖 Loading parquet file: {filename}")
    df = pq.read_table(file_path).to_pandas()
    
    # Cache it
    PARQUET_DATA[cache_key] = df
    PARQUET_DATA_TIMESTAMP[cache_key] = current_time
    
    print(f"✅ Loaded {len(df)} rows from {filename}")
    return df


# ============================================================================
# PRELOAD ALL DATA
# ============================================================================

def preload_all_data():
    """
    Preload metadata and cache genome data.

    This loads:
    1. Metadata (P-site offsets, stop codon types)
    2. Genome data (GTF, FASTA) - cached to pickle for instant future access
    3. CDS end positions (for stop codon analysis)

    NOTE: Parquet files are NOT preloaded - they're small and loaded on-demand.
    Only genome files (GTF, FASTA) are cached since they're large and expensive to parse.

    Call this once when user clicks "Preprocess All Files".
    """
    print("\n" + "="*80)
    print("🚀 PREPROCESSING DATA...")
    print("="*80 + "\n")

    start_time = time.time()

    # Step 1: Load metadata
    print("📋 Step 1/3: Loading metadata...")
    load_psite_offsets()
    load_stop_codon_types()
    get_available_files()

    # Step 2: Cache genome data (GTF, FASTA)
    print(f"\n🧬 Step 2/3: Caching genome data...")
    from . import genome_cache
    genome_cache.cache_all_genome_data()

    # Step 3: Compute CDS end positions (needed for stop codon analysis)
    print(f"\n📊 Step 3/3: Computing CDS end positions...")
    load_cds_end_positions()

    elapsed = time.time() - start_time
    print("\n" + "="*80)
    print(f"✅ PREPROCESSING COMPLETE in {elapsed:.2f} seconds")
    print("="*80 + "\n")





# ============================================================================
# CLEAR CACHE
# ============================================================================

def clear_all_caches():
    """Clear all cached data"""
    global PARQUET_DATA, PARQUET_DATA_TIMESTAMP
    global GTF_DATA, GTF_DATA_TIMESTAMP
    global GENE_LENGTHS, GENE_LENGTHS_TIMESTAMP
    global PSITE_OFFSETS, PSITE_OFFSETS_TIMESTAMP
    global STOP_CODON_TYPES, STOP_CODON_TYPES_TIMESTAMP
    global CDS_END_POSITIONS, CDS_END_POSITIONS_TIMESTAMP
    global AVAILABLE_FILES

    PARQUET_DATA = {}
    PARQUET_DATA_TIMESTAMP = {}
    GTF_DATA = None
    GTF_DATA_TIMESTAMP = None
    GENE_LENGTHS = {}
    GENE_LENGTHS_TIMESTAMP = None
    PSITE_OFFSETS = {}
    PSITE_OFFSETS_TIMESTAMP = None
    STOP_CODON_TYPES = {}
    STOP_CODON_TYPES_TIMESTAMP = None
    CDS_END_POSITIONS = {}
    CDS_END_POSITIONS_TIMESTAMP = None
    AVAILABLE_FILES = {'parquet': [], 'mrna': [], 'timestamp': None}

    print("🗑️ All caches cleared")

