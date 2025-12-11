#!/bin/bash
# Download GTF file from S3 to /var/app/current at startup

GTF_BUCKET="riboflow-gtf-files"
GTF_KEY="gencode.vM25.annotation.gtf"
GTF_LOCAL_PATH="/var/app/current/media/gencode.vM25.annotation.gtf"

echo "Checking if GTF file needs to be downloaded from S3..."

# Create media directory if it doesn't exist
mkdir -p /var/app/current/media

# Check if file already exists and is valid (not empty)
if [ -f "$GTF_LOCAL_PATH" ] && [ -s "$GTF_LOCAL_PATH" ]; then
    FILE_SIZE=$(stat -c%s "$GTF_LOCAL_PATH" 2>/dev/null)
    if [ "$FILE_SIZE" -gt 100000000 ]; then  # If > 100MB, assume it's valid
        echo "✅ GTF file already exists at $GTF_LOCAL_PATH ($(($FILE_SIZE / 1024 / 1024))MB)"
        exit 0
    fi
fi

echo "📥 Downloading GTF file from S3..."
# Use public S3 URL to download
S3_URL="https://${GTF_BUCKET}.s3.us-west-2.amazonaws.com/${GTF_KEY}"

if curl -f -o "$GTF_LOCAL_PATH" "$S3_URL" 2>&1; then
    if [ -f "$GTF_LOCAL_PATH" ]; then
        FILE_SIZE=$(stat -c%s "$GTF_LOCAL_PATH" 2>/dev/null)
        echo "✅ Downloaded GTF file ($(($FILE_SIZE / 1024 / 1024))MB)"
        exit 0
    fi
fi

echo "⚠️ Could not download GTF file from S3 - will use local cache if available"
exit 0

