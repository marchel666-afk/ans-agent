#!/usr/bin/env bash
set -euo pipefail
command -v docker >/dev/null || { echo "Docker is required"; exit 1; }
mkdir -p data workspace
[ -f .env ] || cp .env.example .env
echo "Edit .env, then run: docker compose -f deploy/docker-compose.yml up -d --build"
