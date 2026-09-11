# Workspace execution

ANS uses a bounded workspace directory. The workspace tools prevent path traversal, expose file listing/read/write and command execution, and provide basic Git operations.

The coding executor is intentionally backed by Claude Code. It receives the task, current step and project file inventory and is instructed to make real changes and test them.

For production use, run the workspace in a container with only the project directory mounted. Add approval gates before destructive commands or deployment.
