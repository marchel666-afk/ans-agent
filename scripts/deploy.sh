#!/usr/bin/env bash
# One-shot production deploy for ANS Agent (app + local Ollama), VPN-only access.
# Run from the repo root:  bash scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Docker is required. Install docker + compose plugin first."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 plugin is required."; exit 1; }

[ -f .env ] || { cp .env.example .env; echo ">> Created .env from template — edit it (ANS_BIND, OLLAMA_MODEL, API keys) and re-run."; exit 1; }
set -a; . ./.env; set +a
mkdir -p data workspace

COMPOSE="docker compose -f deploy/docker-compose.prod.yml"
echo ">> Building and starting app + ollama..."
$COMPOSE up -d --build

MODEL="${OLLAMA_MODEL:-llama3.2}"
echo ">> Pulling Ollama model: $MODEL (this can take a while on first run)..."
$COMPOSE exec -T ollama ollama pull "$MODEL" || echo "!! model pull failed — pull manually later: $COMPOSE exec ollama ollama pull $MODEL"

BIND="${ANS_BIND:-127.0.0.1}"
sleep 3
echo ">> Health check:"
curl -fsS "http://${BIND}:8080/health" && echo || echo "!! health check failed; see: $COMPOSE logs --tail=50 ans-agent"
echo ">> Auth token (paste into the UI): $(cat data/auth.token 2>/dev/null || echo '(created on first request)')"
echo ">> UI: http://${BIND}:8080/  (reachable only via the VPN if ANS_BIND is the VPN interface IP)"
