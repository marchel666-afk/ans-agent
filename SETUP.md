# ANS Agent — complete setup

## 1. Requirements

- Git
- Python 3.12+ for local mode
- Docker + Compose for VPS mode
- Claude Code CLI authenticated on the execution machine
- Optional API keys: OpenAI, Gemini, OpenRouter
- Optional GitHub token with repository permissions

## 2. Local Windows

PowerShell:
```powershell
git clone https://github.com/marchel666-afk/ans-agent.git
cd ans-agent
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

Open `http://127.0.0.1:8080`.

If PowerShell blocks activation, run the project with `.venv\Scripts\python.exe run.py`.

## 3. Claude Code

Install and authenticate Claude Code using Anthropic's current official installation/authentication flow. Verify that the `claude` executable is available in the same environment where ANS runs.

ANS does not store your Claude account password. Do not put a Claude subscription password in `.env`.

## 4. Optional model pool

Set provider credentials in `.env` only when you want those providers:
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`

Free/limited models should be configured in the model registry rather than hard-coded into the UI.

## 5. GitHub

Set `GITHUB_TOKEN` and `GITHUB_REPO`. Grant only the repository permissions needed for branch, commit, push and pull-request operations.

## 6. First run

1. Open the UI.
2. Enter a small task.
3. Select an agent profile.
4. Start in Agent mode.
5. Watch the event timeline.
6. Approve tools when prompted.
7. Inspect workspace/diff.
8. Create a branch/commit.
9. Push and optionally create a draft PR.

## 7. VPS / Docker

**Claude Code note:** the Docker image runs ANS, but your Claude Code Pro login is a user-level CLI authentication. For the simplest setup that uses your Pro subscription, run ANS natively on the VPS where `claude` is installed and authenticated. The Docker image is suitable when the executor is provided through an API/gateway or when Claude Code is separately installed and authenticated inside the container.

```bash
git clone https://github.com/marchel666-afk/ans-agent.git
cd ans-agent
bash scripts/install.sh
nano .env
docker compose -f deploy/docker-compose.yml up -d --build
bash scripts/healthcheck.sh
```

The production compose service listens on localhost port 8000. Put Nginx and TLS in front of it.

## 8. Backups

Back up at least:
- `data/`
- `workspace/`
- `.env` through a secure secret-management process

Never commit secrets.

## 9. Troubleshooting

Check:
```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f
curl http://127.0.0.1:8000/health
```

For local mode:
```text
python run.py
http://127.0.0.1:8080
```

## 10. Security baseline

Do not expose the agent directly to the public Internet. Use TLS, firewall rules, authentication, least-privilege GitHub credentials, a dedicated workspace, and regular backups.
