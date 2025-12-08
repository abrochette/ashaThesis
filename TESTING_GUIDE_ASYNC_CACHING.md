# Testing Guide: Async Caching Implementation

## What to Expect

### Upload Phase (Immediate)
```
✅ File uploaded successfully
✅ Preprocessing will continue in the background
```
- Upload completes in **< 5 seconds** (no timeout!)
- File is immediately available for analysis
- Caching starts in background thread

### Analysis Phase (Immediate)
```
⚠️ Cache miss for PCA, reading file: filename.parquet
```
- First analysis run: **5-30 seconds** (reads file directly)
- Plots are generated correctly
- No errors or missing data

### Caching Phase (Background)
```
Background caching completed for filename.parquet
```
- Happens silently in background
- Takes 5-10 minutes for large files
- No impact on user experience

### Second Analysis Run (Fast)
```
🚀 Using cached gene counts for PCA: filename.parquet
```
- Second analysis run: **< 1 second** (uses cache)
- Much faster than first run
- Same results as first run

## Test Scenarios

### Scenario 1: Upload → Analyze Immediately
1. Upload a parquet file
2. Immediately go to analysis page
3. Generate a plot
4. **Expected**: Plot generates in 5-30 seconds (no cache yet)
5. **Check terminal**: Should see "Cache miss" message

### Scenario 2: Upload → Wait → Analyze
1. Upload a parquet file
2. Wait 10 minutes for caching to complete
3. Generate a plot
4. **Expected**: Plot generates in < 1 second (cache hit)
5. **Check terminal**: Should see "Using cached" message

### Scenario 3: P-site Offset Upload
1. Go to Upload page
2. Upload P-site offset CSV
3. **Expected**: Success message, file saved to media/uorf_psite_offset.csv
4. Go to P-site Offset Analysis page
5. **Expected**: Can also upload CSV from there

## Terminal Output to Look For

### Success Indicators
```
✅ Successfully uploaded X riboseq files. Preprocessing will continue in the background.
Background caching completed for filename.parquet
🚀 Using cached gene counts for PCA: filename.parquet
```

### Expected Warnings (Normal)
```
⚠️ Cache miss for PCA, reading file: filename.parquet
```
This is normal on first analysis run - file is being read directly.

### Error Indicators (Should NOT see)
```
Error during background caching
sqlite3.OperationalError
413 Request Entity Too Large
504 Gateway Time-out
```

## Performance Expectations

| Operation | Time | Cache Status |
|-----------|------|--------------|
| Upload file | < 5 sec | N/A |
| First analysis | 5-30 sec | Miss (reading file) |
| Caching (background) | 5-10 min | In progress |
| Second analysis | < 1 sec | Hit (using cache) |

## Troubleshooting

**Q: Upload still times out?**
- Check nginx timeout settings in `.platform/nginx/conf.d/proxy.conf`
- Should have `proxy_read_timeout 600s;`

**Q: Analysis is slow even after caching?**
- Check terminal for "Cache miss" message
- Caching may still be in progress
- Wait a few more minutes

**Q: P-site offset CSV not saving?**
- Check file format: needs "Experiment", "Read Length", "P-site Offset" columns
- Check file permissions on media/ directory

