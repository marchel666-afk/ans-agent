# GitHub integration

Configure GITHUB_TOKEN, GITHUB_REPO and GITHUB_BASE_BRANCH in .env.

Recommended workflow:
1. Audit workspace.
2. Work on a feature branch.
3. Review Diff.
4. Run tests.
5. Commit.
6. Push and create PR only after approval.

Keep the token server-side. Never expose it to model prompts or the browser.
