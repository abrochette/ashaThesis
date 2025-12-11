#!/bin/bash
# Download GTF file from S3 to /tmp at startup

set -e

# GTF file details
GTF_BUCKET="riboflow-gtf-files"
GTF_KEY="gencode.vM25.annotation.gtf"
GTF_LOCAL_PATH="/tmp/gencode.vM25.annotation.gtf"

echo "Checking if GTF file needs to be downloaded from S3..."

# Check if file already exists and is valid (not empty)
if [ -f "$GTF_LOCAL_PATH" ] && [ -s "$GTF_LOCAL_PATH" ]; then
    FILE_SIZE=$(stat -f%z "$GTF_LOCAL_PATH" 2>/dev/null || stat -c%s "$GTF_LOCAL_PATH" 2>/dev/null)
    if [ "$FILE_SIZE" -gt 100000000 ]; then  # If > 100MB, assume it's valid
        echo "✅ GTF file already exists at $GTF_LOCAL_PATH ($(($FILE_SIZE / 1024 / 1024))MB)"
        exit 0
    fi
fi

echo "📥 Downloading GTF file from S3..."
aws s3 cp "s3://$GTF_BUCKET/$GTF_KEY" "$GTF_LOCAL_PATH" --region us-west-2

if [ -f "$GTF_LOCAL_PATH" ]; then
    FILE_SIZE=$(stat -f%z "$GTF_LOCAL_PATH" 2>/dev/null || stat -c%s "$GTF_LOCAL_PATH" 2>/dev/null)
    echo "✅ Downloaded GTF file ($(($FILE_SIZE / 1024 / 1024))MB)"
else
    echo "❌ Failed to download GTF file from S3"
    exit 1
fi

