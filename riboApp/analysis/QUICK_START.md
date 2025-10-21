# Quick Start Guide - New Data Loading System

## TL;DR

**Old System**: Every plot takes 10-12 seconds
**New System**: First preprocessing takes 2-3 minutes, then every plot takes < 1 second ⚡

## How to Use

### Step 1: Upload Your Files
1. Go to the upload page
2. Upload your parquet files as usual

### Step 2: Click "Preprocess All Files"
1. Click the "Preprocess All Files" button
2. Wait 2-3 minutes (one-time cost)
3. You'll see progress in the terminal:
   ```
   🚀 PREPROCESSING DATA...
   📋 Step 1/3: Loading metadata...
   ✅ Loaded 42 P-site offset mappings
   ✅ Loaded stop codons for 20,521 genes

   🧬 Step 2/3: Caching genome data...
   📖 Parsing GTF file (this may take a minute)...
   ✅ Cached GTF data (2,500,000 rows)
   📖 Parsing FASTA file (this may take a minute)...
   ✅ Cached FASTA data (150,000 sequences)
   📊 Extracting gene lengths from GTF...
   ✅ Cached gene lengths for 22,416 genes

   📊 Step 3/3: Computing CDS end positions...
   ✅ Computed CDS end positions for 18,234 genes

   ✅ PREPROCESSING COMPLETE in 120.45 seconds

   🔬 PRE-COMPUTING ANALYSIS RESULTS...
   📊 Pre-computing stop codon readthrough for 10 files...
     [1/10] P42_Brain_Ribo_rep1.parquet... ✅
     [2/10] P42_Brain_Ribo_rep2.parquet... ✅
   ...

   ✅ ANALYSIS RESULTS PRE-COMPUTED in 45.23 seconds
   ```

### Step 3: Generate Plots (Instant!)
1. Go to any analysis page (e.g., Stop Codon Readthrough)
2. Select your files
3. Click "Generate Plots"
4. **Plot appears in < 1 second!** ⚡

## What's Happening Behind the Scenes

### During Preprocessing

```
┌─────────────────────────────────────────────────┐
│  Loading into Memory (Hash Maps)               │
├─────────────────────────────────────────────────┤
│  ✓ P-site offsets: {(exp, len): offset}        │
│  ✓ Stop codons: {gene: 'TAA'/'TAG'/'TGA'}      │
│  ✓ Gene lengths: {gene: length}                │
│  ✓ CDS ends: {gene: position}                  │
│  ✓ All parquet files: {file: DataFrame}        │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  Pre-Computing Analysis Results (CSVs)          │
├─────────────────────────────────────────────────┤
│  For each file:                                 │
│    ✓ Stop codon readthrough → CSV              │
│    ✓ P-site metagene → CSV (future)            │
│    ✓ PCA → CSV (future)                        │
└─────────────────────────────────────────────────┘
```

### When You Request a Plot

```
User clicks "Generate Plot"
         ↓
Check: Is CSV pre-computed?
         ↓
    ┌────┴────┐
    │   YES   │  → Retrieve CSV (0.01s) → Plot (0.3s) → DONE! ⚡
    └─────────┘
         
    ┌────┴────┐
    │   NO    │  → Compute now (3-5s) → Cache CSV → Plot → DONE
    └─────────┘
```

## Performance Numbers

| Action | Old System | New System (After Preprocessing) |
|--------|-----------|----------------------------------|
| **First-time setup** | 0 seconds | 5-10 minutes (one-time) |
| **Generate plot** | 10-12 seconds | < 1 second ⚡ |
| **Generate 10 plots** | 100-120 seconds | < 10 seconds ⚡ |
| **Generate 100 plots** | 1000-1200 seconds (20 min) | < 100 seconds (1.5 min) ⚡ |

## Memory Usage

- **RAM**: ~1-2 GB (for 10 parquet files)
- **Disk**: No additional disk space needed
- **Cache duration**: 5 minutes (auto-refresh)

## When to Re-Preprocess

You need to click "Preprocess All Files" again when:
- ✓ You upload new parquet files
- ✓ You modify P-site offsets
- ✓ Cache expires (after 5 minutes of inactivity)
- ✓ You restart the Django server

## Troubleshooting

### "Plot is still slow (3-5 seconds)"
- You probably didn't click "Preprocess All Files"
- Or the cache expired (5 minutes)
- Solution: Click "Preprocess All Files" again

### "Preprocessing is taking forever"
- This is normal! It's pre-computing ALL analyses for ALL files
- Expected time: 5-10 minutes for 10 files
- You only need to do this once (or when you upload new files)

### "I got an error during preprocessing"
- Check the terminal for error messages
- Make sure all required files exist:
  - `media/uorf_psite_offset.csv`
  - `media/stopcodons.gene_stopcodons.per_gene_majority.tsv`
  - `media/gencode.vM25.annotation.gtf`
  - Parquet files in `media/parquetFiles/`

### "How do I know if preprocessing worked?"
- Look for this message: `✅ ALL ANALYSES PRE-COMPUTED in X seconds`
- Try generating a plot - it should be instant (< 1 second)
- Check terminal for: `⚡ Using pre-computed results - instant plot generation!`

## Advanced Usage

### Clear All Caches
```python
from riboApp.analysis import data_loader
data_loader.clear_all_caches()
```

### Check What's Cached
```python
from riboApp.analysis import data_loader

# Check if data is loaded
print(f"P-site offsets loaded: {len(data_loader.PSITE_OFFSETS)} entries")
print(f"Stop codons loaded: {len(data_loader.STOP_CODON_TYPES)} genes")
print(f"Parquet files loaded: {len(data_loader.PARQUET_DATA)} files")

# Check if analyses are pre-computed
print(f"Stop codon results cached: {len(data_loader.PRECOMPUTED_RESULTS['stop_codon_readthrough'])} file combinations")
```

### Preload Only (No Pre-Computation)
If you want faster preprocessing but don't need instant plots:
```python
from riboApp.analysis import data_loader

# Just load raw data (60 seconds)
data_loader.preload_all_data()

# Skip pre-computation
# Plots will take 3-5 seconds instead of < 1 second
```

## What's Next?

Currently only **Stop Codon Readthrough** uses the new system. Future analyses will be migrated:
- [ ] P-site Metagene plots
- [ ] PCA analysis
- [ ] Gene counts scatter plots
- [ ] Read length distribution

As each is migrated, they'll also benefit from instant plot generation!

## Questions?

See `DATA_LOADING_EXPLAINED.md` for a detailed technical explanation of how the system works.

