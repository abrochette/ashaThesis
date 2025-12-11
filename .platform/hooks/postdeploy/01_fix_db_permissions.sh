#!/bin/bash
# Fix database file permissions to allow writes

echo "Fixing database permissions..."

# Make sure the database file is writable
if [ -f "/var/app/current/db.sqlite3" ]; then
    chmod 666 /var/app/current/db.sqlite3
    chmod 777 /var/app/current
    echo "✅ Database permissions fixed"
else
    echo "⚠️ Database file not found at /var/app/current/db.sqlite3"
fi

exit 0

