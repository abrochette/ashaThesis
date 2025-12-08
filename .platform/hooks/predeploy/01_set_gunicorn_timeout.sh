#!/bin/bash
# Set Gunicorn timeout to 3600 seconds (1 hour) for large file uploads

# Create a gunicorn config file
cat > /var/app/current/gunicorn_config.py << 'EOF'
import multiprocessing

workers = 3
worker_class = "sync"
timeout = 3600
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
EOF

echo "✅ Gunicorn timeout set to 3600 seconds"

