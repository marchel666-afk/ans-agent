# ANS Agent — User Guide

## 1. What you are running

ANS is a self-hosted agent workspace. Claude Code is the local execution engine; GPT, Gemini, OpenRouter and optional Ollama are used for planning, review and fallback.

Important: a Claude Code subscription is not the same thing as an Anthropic API key. The Claude adapter invokes the local `claude` CLI, so keep Claude Code installed and authenticated on the machine running ANS. GPT/Gemini/OpenRouter entries use API keys.

## 2. Install on Windows

Install Python 3.12+, Git, Node.js and Claude Code. Verify:

    python --version
    git --version
    node --version
    claude --version

Clone the repository and install dependencies:

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -r requirements.txt
    copy .env.example .env

Create or edit `.env`:

    OPENAI_API_KEY=
    OPENAI_MODEL=gpt-5
    GEMINI_API_KEY=
    GEMINI_MODEL=gemini-2.5-flash
    OPENROUTER_API_KEY=
    OPENROUTER_MODEL=openrouter/free
    GITHUB_TOKEN=
    GITHUB_REPO=owner/repository
    GITHUB_BASE_BRANCH=main
    ANS_WORKSPACE=./workspace
    ANS_DB=./data/ans.db

Do not put your Claude Code subscription password or session token into `.env`.

Start:

    python run.py

Open `http://127.0.0.1:8080`. The first protected request asks for the generated ANS token. On Windows it is `data\\auth.token`; on Linux/macOS it is `data/auth.token`.

## 3. Recommended model setup

Use Claude Code as the executor/coder. Use GPT as planner/architect/reviewer. Use Gemini as research/planning fallback. Add OpenRouter for a broad free/cheap fallback pool. Ollama is optional for local models.

The router checks configured providers and backs off providers that fail. It does not magically turn a consumer subscription into an API quota: an API provider requires its own compatible access method.

## 4. First task

Create a project inside the configured workspace. Then give ANS an outcome, not a list of keystrokes. Example:

    Inspect this project, understand the architecture, fix the failing combat system, run the existing tests, and show me the final diff. Do not delete unrelated files.

Start with `Agent` mode. Use `Autopilot` only after verifying the workspace and approval policy.

## 5. Approval behavior

Read/list/Git inspection is low risk. File writes and terminal actions are approval-gated. Dangerous shell patterns are additionally blocked. Push/PR operations are intended to remain behind approval.

The current MVP stops the active run when approval is required. Approving the request does not yet resume the exact suspended model turn; rerun the task after approval. This is intentional until resumable tool-call state is added.

## 6. GitHub

Set `GITHUB_TOKEN` with only the repository permissions required for your workflow. Set `GITHUB_REPO=owner/repository`. ANS can inspect branches and pull requests and can create draft PRs through the backend. Keep the token server-side.

## 7. Production on VPS

Use Docker:

    bash scripts/install.sh
    docker compose -f deploy/docker-compose.yml up -d --build

Place Nginx in front of port 8000 and terminate TLS there. Do not expose port 8000 directly to the Internet. See `docs/DEPLOY.md` and `docs/SECURITY.md`.

## 8. Backups

Run:

    bash scripts/backup.sh

This archives the database, workspace and `.env`. Store backups outside the VPS as well; treat the archive as sensitive because it may contain credentials.

## 9. Troubleshooting

- `Claude Code CLI not found`: install Claude Code and make `claude` available in PATH.
- `Missing OPENAI_API_KEY`: configure the key in `.env` and restart ANS.
- `Unauthorized`: read the generated token from `data/auth.token` and paste it into the browser prompt.
- Workspace unavailable: verify `ANS_WORKSPACE` exists and is writable.
- Docker starts but UI is broken: verify Nginx proxies WebSocket upgrades and `/web/*` is served by FastAPI.
