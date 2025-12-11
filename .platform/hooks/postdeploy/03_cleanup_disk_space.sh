#!/bin/bash
# Clean up disk space to prevent "No space left on device" errors

echo "Cleaning up disk space..."

# Remove old uploaded files (keep only recent ones)
if [ -d "/var/app/current/media/uploads" ]; then
    echo "Removing old uploaded files..."
    find /var/app/current/media/uploads -type f -mtime +7 -delete 2>/dev/null || true
fi

# Remove old temporary files
if [ -d "/tmp" ]; then
    echo "Cleaning /tmp directory..."
    find /tmp -type f -mtime +1 -delete 2>/dev/null || true
fi

# Remove Django cache files
if [ -d "/var/app/current/media/.genome_cache" ]; then
    echo "Checking genome cache size..."
    CACHE_SIZE=$(du -sh /var/app/current/media/.genome_cache 2>/dev/null | cut -f1)
    echo "Genome cache size: $CACHE_SIZE"
fi

# Show disk usage
echo "Disk usage after cleanup:"
df -h /var/app/current | tail -1

exit 0

