#!/bin/bash
# Clean up disk space to prevent "No space left on device" errors

echo "Cleaning up disk space..."

# Remove old uploaded files (keep only recent ones)
if [ -d "/var/app/current/media/uploads" ]; then
    echo "Removing old uploaded files..."
    find /var/app/current/media/uploads -type f -mtime +1 -delete 2>/dev/null || true
fi

# Remove old parquet pickle cache files (these can be regenerated)
if [ -d "/var/app/current/media/parquetPickles" ]; then
    echo "Removing parquet pickle cache files..."
    rm -rf /var/app/current/media/parquetPickles/* 2>/dev/null || true
fi

if [ -d "/var/app/current/media/mrnaPickles" ]; then
    echo "Removing mRNA pickle cache files..."
    rm -rf /var/app/current/media/mrnaPickles/* 2>/dev/null || true
fi

# Remove old temporary files
if [ -d "/tmp" ]; then
    echo "Cleaning /tmp directory..."
    find /tmp -type f -mtime +0 -delete 2>/dev/null || true
fi

# Remove old genome cache files (can be regenerated)
if [ -d "/var/app/current/media/.genome_cache" ]; then
    echo "Removing genome cache files..."
    rm -rf /var/app/current/media/.genome_cache/* 2>/dev/null || true
fi

# Show disk usage
echo "Disk usage after cleanup:"
df -h /var/app/current | tail -1

exit 0

