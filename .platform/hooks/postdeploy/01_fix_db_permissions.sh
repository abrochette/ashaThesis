#!/bin/bash
# Fix database and cache directory permissions to allow writes

echo "Fixing database and cache permissions..."

# Make sure the database file is writable
if [ -f "/var/app/current/db.sqlite3" ]; then
    chmod 666 /var/app/current/db.sqlite3
    chmod 777 /var/app/current
    echo "✅ Database permissions fixed"
else
    echo "⚠️ Database file not found at /var/app/current/db.sqlite3"
fi

# Make sure the cache directory is writable
if [ -d "/var/app/current/media/.django_cache" ]; then
    chmod 777 /var/app/current/media/.django_cache
    chmod 666 /var/app/current/media/.django_cache/* 2>/dev/null || true
    echo "✅ Cache directory permissions fixed"
else
    mkdir -p /var/app/current/media/.django_cache
    chmod 777 /var/app/current/media/.django_cache
    echo "✅ Cache directory created with correct permissions"
fi

exit 0

