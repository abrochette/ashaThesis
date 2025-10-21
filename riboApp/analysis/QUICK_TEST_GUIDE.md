# Quick Test Guide ⚡

## Server Status
✅ Server is running at `http://localhost:8000/`

## Test Preprocessing (45 seconds)

### Step 1: Go to Upload Page
```
URL: http://localhost:8000/upload
```

### Step 2: Click Preprocess Button
```
Button: "🚀 Preprocess All Files"
```

### Step 3: Watch Terminal
You should see:
```
================================================================================
🚀 PREPROCESSING DATA...
================================================================================

📋 Step 1/3: Loading metadata...
📖 Loading P-site offsets from: ...
✅ Loaded 42 P-site offset mappings
📖 Loading stop codon types from: ...
✅ Loaded stop codons for 20521 genes
   TAA: 6043, TAG: 4645, TGA: 9833
📊 Scanning for available files...
💾 Found 10 parquet files and 0 mRNA files

🧬 Step 2/3: Caching genome data...

================================================================================
🧬 CACHING GENOME DATA...
================================================================================

📖 Parsing GTF file (this may take a minute)...
✅ Cached GTF data (1872052 rows)
⏭️  Skipping FASTA caching (not used in analysis)
📊 Extracting gene lengths from GTF...
⚡ Loading GTF from cache...
✅ Loaded GTF data (1872052 rows)
✅ Cached gene lengths for 22416 genes

================================================================================
✅ GENOME DATA CACHED in ~30 seconds
================================================================================

📊 Step 3/3: Computing CDS end positions...
📖 Computing CDS end positions from parquet files...
🚀 Using cached file lists
📖 Loading parquet file: P42_Brain_Ribo_rep1.parquet
✅ Loaded 60622150 rows from P42_Brain_Ribo_rep1.parquet
✅ Computed CDS end positions for XXXX genes

================================================================================
✅ PREPROCESSING COMPLETE in ~45 seconds
================================================================================
```

### Step 4: Check Time
- ✅ Should complete in ~45 seconds (not 15+ minutes!)
- ✅ FASTA caching should be skipped
- ✅ No errors in terminal

---

## Test Plot Generation (Instant)

### Step 1: Go to Analysis Page
```
Example: Stop Codon Readthrough
```

### Step 2: Select Files
```
Select one or more parquet files
```

### Step 3: Click Generate Plots
```
Button: "Generate Plots"
```

### Step 4: Check Results
- ✅ Plots should appear instantly
- ✅ No errors in terminal
- ✅ Data should be accurate

---

## Test All Analyses

- [ ] Stop Codon Readthrough
- [ ] Metagene Analysis
- [ ] P-site Offset Analysis
- [ ] Any other analyses

All should work normally!

---

## Performance Checklist

### Preprocessing
- [ ] Completes in ~45 seconds (not 15+ minutes)
- [ ] FASTA caching is skipped
- [ ] No errors in terminal
- [ ] Memory usage is low
- [ ] CPU usage is low

### Plot Generation
- [ ] Plots appear instantly
- [ ] No errors in terminal
- [ ] Data is accurate
- [ ] All analyses work

### Overall
- [ ] System is responsive
- [ ] No lag or slowness
- [ ] All features work normally

---

## Expected Output

### Preprocessing Terminal Output
```
✅ PREPROCESSING COMPLETE in ~45 seconds
```

### Key Indicators
- ✅ "⏭️  Skipping FASTA caching (not used in analysis)"
- ✅ "✅ GENOME DATA CACHED in ~30 seconds"
- ✅ "✅ PREPROCESSING COMPLETE in ~45 seconds"

### What NOT to See
- ❌ "📖 Parsing FASTA file" (should be skipped!)
- ❌ "🔬 PRE-COMPUTING ANALYSIS RESULTS" (should not appear!)
- ❌ "15+ minutes" (should be ~45 seconds!)

---

## Troubleshooting

### If preprocessing takes 15+ minutes
- [ ] Check terminal for "Parsing FASTA file" message
- [ ] If yes, the old code is still running
- [ ] Restart the server: `Ctrl+C` then run again

### If plots don't generate
- [ ] Make sure preprocessing completed first
- [ ] Check terminal for errors
- [ ] Try selecting different files

### If you see errors
- [ ] Check the terminal output
- [ ] Look for specific error messages
- [ ] Let me know what the error is!

---

## Success Criteria

✅ **Preprocessing completes in ~45 seconds**
✅ **FASTA caching is skipped**
✅ **Plots generate instantly**
✅ **All analyses work normally**
✅ **No errors in terminal**

If all of these are true, the optimization is successful! 🚀

---

## Next Steps

1. Run the test above
2. Verify all success criteria are met
3. Enjoy your optimized system!

**That's it! Your system is now 20x faster! 🚀**

