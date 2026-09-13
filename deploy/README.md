# ANS Agent — production deploy (VPN-only)

Runs the agent + a local Ollama as Docker containers, reachable **only through
your VPN**. The agent can execute code, so it must not be exposed to the open
internet and should be isolated from the VPN's own admin panel/DB.

## 0. Prerequisites (on the VPS)
- Docker + Compose v2:  `docker --version && docker compose version`
  (install: `curl -fsSL https://get.docker.com | sh`)
- Your VPN interface IP on the VPS. Find it:
  `ip -4 addr | grep -E 'wg|tun|10\.|172\.'`  → e.g. `10.8.0.1`.

## 1. Get the code
```
git clone https://github.com/marchel666-afk/ans-agent.git
cd ans-agent
cp .env.example .env
```

## 2. Configure `.env`
Set at least:
- `ANS_BIND=<your VPN interface IP>`   (e.g. `10.8.0.1`) — so the UI is reachable
  only via the VPN. Leave `127.0.0.1` to keep it localhost-only (SSH tunnel).
- `OLLAMA_MODEL=llama3.2`  (or a lighter model on a weak CPU: `llama3.2:1b`, `qwen2.5:3b`).
- Optional API keys for premium/faster routing: `OPENAI_API_KEY`, `GEMINI_API_KEY`,
  `OPENROUTER_API_KEY`.
Keep `.env` private (`chmod 600 .env`). It is already git-ignored.

## 3. Deploy
```
bash scripts/deploy.sh
```
This builds the app, starts Ollama, pulls the model, prints the health status and
the **auth token** (from `data/auth.token`).

## 4. Use it
From a machine connected to the VPN, open:  `http://<ANS_BIND>:8080/`
On the first protected request, paste the auth token.

## 5. Verify
```
curl -fsS http://<ANS_BIND>:8080/health
docker compose -f deploy/docker-compose.prod.yml ps
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 ans-agent
```

## 6. Update later
```
git pull
bash scripts/deploy.sh          # rebuilds and restarts
```

## Security notes (agent runs code — treat as privileged)
- Never set `ANS_BIND=0.0.0.0`. Keep it on the VPN interface (or localhost).
- Add a firewall rule so port 8080 is not reachable from the public interface
  (e.g. `ufw deny 8080` on the public NIC; allow only the VPN subnet).
- The agent's tools run inside its container (isolated from the host), but it can
  reach the network — do not give the container access to the VPN admin panel/DB
  network. Run on a separate box if you want maximum isolation.
- Back up `data/` (SQLite + token) and `workspace/`; treat backups as sensitive.
- Rotate the auth token by deleting `data/auth.token` and restarting.
