#!/usr/bin/env bash
set -euo pipefail
mkdir -p backups
tar -czf "backups/ans-$(date +%Y%m%d-%H%M%S).tar.gz" data workspace .env
