# Security

ANS Agent is a powerful local development agent. Before public exposure:

- Configure ANS_AUTH_TOKEN_FILE and protect the generated token.
- Send `Authorization: Bearer <token>` to protected API endpoints.
- Keep port 8000 private behind Nginx/firewall.
- Never put provider or GitHub secrets into prompts.
- Use a dedicated workspace directory.
- Review terminal commands through the approval layer.
- Back up the SQLite database and workspace.
- Put TLS and an additional identity/access layer in front of a public deployment.
