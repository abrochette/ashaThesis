#!/bin/bash
# Reload nginx to apply configuration changes
sudo systemctl reload nginx || sudo service nginx reload || true

