# ANS Agent

Self-hosted multi-model agent workspace inspired by modern agent workbenches.

## Features

- Claude Code as the execution engine
- GPT / Gemini / OpenRouter / Ollama model pool
- model routing with provider fallback and backoff
- persistent sessions and project memory
- workspace sandbox
- terminal, file and Git tools
- approval gates
- GitHub branches / PR integration
- Best-of-N mode
- realtime WebSocket run timeline
- Docker + Nginx deployment

## Local start

    python -m venv .venv
    .venv\\Scripts\\activate        # Windows
    # source .venv/bin/activate    # Linux/macOS
    pip install -r requirements.txt
    copy .env.example .env         # Windows
    # cp .env.example .env         # Linux/macOS
    python run.py

Open http://127.0.0.1:8080.

The first protected API request asks for the token stored in `ANS_AUTH_TOKEN_FILE` (default `data/auth.token`).

## Production

    bash scripts/install.sh
    docker compose -f deploy/docker-compose.yml up -d --build

See `docs/USER_GUIDE.md`, `docs/DEPLOY.md` and `docs/SECURITY.md`.
