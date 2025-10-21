# When Does Caching Happen? - Complete Timeline

## TL;DR

**Cache is NOT automatic!** You must manually click "🚀 Preprocess All Files" button after uploading files.

## Complete Timeline

### 1. User Uploads Parquet Files

```
User goes to /upload_parquet/
  ↓
Selects files and clicks "Upload Multiple Riboseq Files"
  ↓
Files are saved to: media/parquetFiles/
  ↓
✅ Files are on disk
❌ NO caching happens
❌ NO preprocessing happens
❌ Cache is EMPTY
```

**What happens:**
- Files are validated (check for required columns)
- Files are saved to disk
- Old preprocessing cache is created (for compatibility)
- Global caches are cleared (to force reload)

**What does NOT happen:**
- New data loader cache is NOT populated
- Analysis results are NOT pre-computed
- Hash maps are NOT created

### 2. User Tries to Generate a Plot (Without Preprocessing)

```
User goes to /stop_codon_readthrough/
  ↓
Selects files and clicks "Generate Plots"
  ↓
Check: Is result pre-computed? → NO (cache is empty)
  ↓
Load data from disk (SLOW - reading from disk)
  ↓
Load P-site offsets from CSV (SLOW - reading from disk)
  ↓
Load stop codon types from TSV (SLOW - reading from disk)
  ↓
Compute CDS end positions (SLOW - processing data)
  ↓
Apply P-site offsets (SLOW - DataFrame operations)
  ↓
Aggregate across genes (SLOW - groupby operations)
  ↓
Generate plot
  ↓
⏱️ Total time: 10-12 seconds
```

**Why is it slow?**
- Every operation reads from disk
- No hash maps, so lookups are O(n) instead of O(1)
- No pre-computed results, so everything is calculated on-the-fly

### 3. User Clicks "🚀 Preprocess All Files" (MANUAL ACTION REQUIRED!)

```
User goes to /upload_parquet/
  ↓
Clicks "🚀 Preprocess All Files" button
  ↓
POST request to /preprocess_all_files/
  ↓
┌─────────────────────────────────────────────────────────┐
│  LEVEL 1: preload_all_data()                            │
│  Time: ~60 seconds                                      │
├─────────────────────────────────────────────────────────┤
│  Step 1: Load metadata                                  │
│    ✓ P-site offsets → Hash map                         │
│      {('P42_Brain_Ribo_rep1', 28): 12, ...}            │
│    ✓ Stop codon types → Hash map                       │
│      {'Actb': 'TAA', 'Gapdh': 'TGA', ...}              │
│    ✓ Gene lengths → Hash map                           │
│      {'Actb': 1128, 'Gapdh': 1002, ...}                │
│                                                         │
│  Step 2: Load all parquet files into memory            │
│    ✓ P42_Brain_Ribo_rep1.parquet → DataFrame           │
│    ✓ P42_Kidney_Ribo_rep1.parquet → DataFrame          │
│    ✓ ... (all files)                                   │
│                                                         │
│  Step 3: Load mRNA files into memory                   │
│    ✓ P42_Brain_mRNA_rep1.parquet → DataFrame           │
│    ✓ ... (all mRNA files)                              │
│                                                         │
│  Step 4: Compute CDS end positions                     │
│    ✓ For each gene, find max end_position in CDS       │
│      {'Actb': 1237, 'Gapdh': 989, ...}                 │
└─────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────┐
│  LEVEL 2: precompute_all_analyses()                     │
│  Time: ~5-10 minutes                                    │
├─────────────────────────────────────────────────────────┤
│  For each parquet file:                                 │
│    ✓ Generate stop codon readthrough CSV               │
│      - Filter genes by stop codon type                 │
│      - Apply P-site offsets                            │
│      - Calculate relative positions                    │
│      - Aggregate across genes                          │
│      - Store final CSV in cache                        │
│                                                         │
│  Result: PRECOMPUTED_RESULTS = {                       │
│    'stop_codon_readthrough': {                         │
│      frozenset(['P42_Brain_Ribo_rep1.parquet']): CSV,  │
│      frozenset(['P42_Kidney_Ribo_rep1.parquet']): CSV, │
│      ...                                               │
│    }                                                   │
│  }                                                     │
└─────────────────────────────────────────────────────────┘
  ↓
✅ Success message: "All files have been preprocessed and all analyses pre-computed!"
✅ Cache is now FULL
✅ All future plots will be INSTANT
```

### 4. User Generates a Plot (After Preprocessing)

```
User goes to /stop_codon_readthrough/
  ↓
Selects files and clicks "Generate Plots"
  ↓
Check: Is result pre-computed? → YES! ✅
  ↓
Retrieve CSV from memory (0.01 seconds)
  ↓
Organize data by stop codon type (0.05 seconds)
  ↓
Create plot (0.3 seconds)
  ↓
⚡ Total time: < 1 second
```

**Why is it fast?**
- CSV is already computed and stored in memory
- No disk I/O
- No calculations needed
- Just retrieve and plot

## Visual Timeline

```
TIME: 0 min
├─ User uploads files
│  └─ Files saved to disk
│  └─ ❌ NO caching
│
TIME: 1 min
├─ User tries to generate plot
│  └─ ⏱️ Takes 10-12 seconds (slow, no cache)
│
TIME: 2 min
├─ User clicks "🚀 Preprocess All Files"
│  └─ Level 1: Load data (~60 seconds)
│  └─ Level 2: Pre-compute analyses (~5-10 minutes)
│
TIME: 12 min
├─ ✅ Preprocessing complete!
│  └─ Cache is FULL
│
TIME: 13 min
├─ User generates plot
│  └─ ⚡ Takes < 1 second (instant!)
│
TIME: 14 min
├─ User generates another plot
│  └─ ⚡ Takes < 1 second (instant!)
│
TIME: 15 min
├─ User generates 10 more plots
│  └─ ⚡ Each takes < 1 second (instant!)
│
TIME: 20 min
├─ ⚠️ Cache expires (5 minute timeout)
│  └─ Next plot will be slow again (10-12 seconds)
│  └─ But it will re-cache automatically
│
TIME: 21 min
├─ User generates plot
│  └─ ⏱️ Takes 3-5 seconds (re-caching)
│  └─ ✅ Cache refreshed
│
TIME: 22 min
├─ User generates plot
│  └─ ⚡ Takes < 1 second (instant again!)
```

## Where is the Button?

The "🚀 Preprocess All Files" button is located on the **Upload Parquet Files** page:

1. Navigate to: `/upload_parquet/`
2. Scroll down past the upload forms
3. You'll see a yellow box with the button
4. Click it and wait 5-10 minutes

## What if I Forget to Preprocess?

If you forget to click "Preprocess All Files":
- ✅ Plots will still work
- ❌ But they'll be SLOW (10-12 seconds each)
- ⚠️ First plot will auto-cache, making subsequent plots faster (3-5 seconds)
- 💡 But you won't get the full benefit of pre-computed results

## When Do I Need to Preprocess Again?

You need to click "Preprocess All Files" again when:

1. **You upload new files**
   - New files won't be in the cache
   - Old files will still be cached

2. **Cache expires (5 minutes of inactivity)**
   - If you don't use the app for 5 minutes, cache clears
   - Next plot will be slow, but will re-cache automatically

3. **You restart the Django server**
   - Cache is in-memory, so it's lost on restart
   - Need to preprocess again

4. **You modify P-site offsets or other metadata**
   - Old cached results may be invalid
   - Need to re-preprocess to update

## Can We Make It Automatic?

**YES!** We could make preprocessing happen automatically when files are uploaded. Here are the options:

### Option A: Automatic Preprocessing on Upload (Synchronous)
```python
# In upload_parquet view
if successful_uploads > 0:
    # Automatically preprocess
    from .analysis import data_loader
    data_loader.preload_all_data()
    data_loader.precompute_all_analyses()
```

**Pros:**
- User doesn't have to remember to click button
- Always up-to-date

**Cons:**
- Upload takes 5-10 minutes (user has to wait)
- Blocks the upload request

### Option B: Automatic Preprocessing on Upload (Asynchronous with Celery)
```python
# In upload_parquet view
if successful_uploads > 0:
    # Trigger background task
    preprocess_all_files_task.delay()
```

**Pros:**
- Upload is instant
- Preprocessing happens in background
- User can continue using the app

**Cons:**
- Requires Celery setup
- More complex

### Option C: Keep Manual Button (Current)
**Pros:**
- User has control
- No waiting during upload
- Simple implementation

**Cons:**
- User might forget to click it
- Requires manual action

## Recommendation

For now, **keep the manual button** because:
1. It's simple and works
2. User has control over when to wait
3. No additional dependencies needed

In the future, if you want automatic preprocessing, implement **Option B (Celery)** for the best user experience.

## Summary

**Cache is created ONLY when you click "🚀 Preprocess All Files" button.**

- ❌ NOT automatic on upload
- ❌ NOT automatic on first plot
- ✅ ONLY when you manually click the button

**After preprocessing:**
- ⚡ All plots are instant (< 1 second)
- 💾 Cache lasts 5 minutes
- 🔄 Auto-refreshes if expired (but slower first time)

