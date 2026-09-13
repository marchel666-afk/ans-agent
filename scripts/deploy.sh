#!/usr/bin/env bash
# One-shot production deploy for ANS Agent (app + local Ollama), VPN-only access.
# Idempotent: safe to re-run for updates.  Run from repo root:  bash scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# --- Docker ---
if ! command -v docker >/dev/null; then
  echo ">> Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || { echo "!! Docker Compose v2 plugin missing. Install docker-compose-plugin."; exit 1; }

# --- .env (create with sane defaults on first run, then continue) ---
if [ ! -f .env ]; then
  cp .env.example .env
  # Auto-detect a VPN/private interface IP to bind to (wg*/tun* preferred).
  VPNIP="$(ip -4 -o addr show 2>/dev/null | awk '/wg|tun/{print $4}' | cut -d/ -f1 | head -1)"
  [ -z "${VPNIP:-}" ] && VPNIP="$(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -E '^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)' | grep -v '^127' | head -1)"
  [ -z "${VPNIP:-}" ] && VPNIP="127.0.0.1"
  sed -i "s|^ANS_BIND=.*|ANS_BIND=${VPNIP}|" .env
  sed -i "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=llama3.2|" .env
  chmod 600 .env
  echo ">> Created .env  (ANS_BIND=${VPNIP}; add API keys later if you want premium routing)"
fi
set -a; . ./.env; set +a
mkdir -p data workspace

COMPOSE="docker compose -f deploy/docker-compose.prod.yml"
echo ">> Building and starting app + ollama..."
$COMPOSE up -d --build

MODEL="${OLLAMA_MODEL:-llama3.2}"
echo ">> Pulling Ollama model: $MODEL ..."
$COMPOSE exec -T ollama ollama pull "$MODEL" || echo "!! model pull failed; retry: $COMPOSE exec ollama ollama pull $MODEL"

BIND="${ANS_BIND:-127.0.0.1}"; HP="${ANS_HOST_PORT:-8899}"
sleep 4
echo "==================== RESULT ===================="
echo "bind:  ${BIND}:${HP}"
echo -n "health: "; curl -fsS "http://${BIND}:${HP}/health" || echo "(FAILED — $COMPOSE logs --tail=60 ans-agent)"
echo
echo "token: $(cat data/auth.token 2>/dev/null || echo '(created on first request)')"
echo "UI:    http://${BIND}:${HP}/   (reach via SSH tunnel or your admin VPN)"
echo "================================================"
