#!/bin/bash
# Set Gunicorn timeout to 7200 seconds (2 hours) for large file uploads and analysis

# Create a gunicorn config file
cat > /var/app/current/gunicorn_config.py << 'EOF'
import multiprocessing

workers = 2
worker_class = "sync"
timeout = 7200
keepalive = 5
max_requests = 500
max_requests_jitter = 50
EOF

echo "✅ Gunicorn timeout set to 7200 seconds with 2 workers"

