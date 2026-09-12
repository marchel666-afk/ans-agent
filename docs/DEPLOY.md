# Production deployment

## Docker
1. Install Docker and Docker Compose.
2. Clone the repository.
3. Run `bash scripts/install.sh`.
4. Edit `.env`.
5. Run `docker compose -f deploy/docker-compose.yml up -d --build`.
6. Verify `bash scripts/healthcheck.sh`.

## Nginx
Copy `deploy/nginx.conf` to an Nginx site configuration, replace `server_name` with your domain, then enable the site and reload Nginx. Put TLS in front of the service before exposing it publicly.

## Data
SQLite and the agent workspace are bind-mounted outside the container. Use `scripts/backup.sh` regularly.

## Preflight
Run `bash scripts/healthcheck.sh` after deployment. Then authenticate in the UI and call `/startup` to verify the configured workspace and providers.

## Security
Do not expose port 8000 directly to the Internet. Keep secrets only in `.env`, protect the UI with an authentication layer before public deployment, and restrict the workspace to a dedicated project directory.

## Healthcheck
The container exposes `/health`; Docker restarts unhealthy services according to the configured policy.
