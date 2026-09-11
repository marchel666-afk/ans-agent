# ANS Agent Architecture

## Product

ANS Agent is a self-hosted multi-model agent workspace. The UI is based on the capabilities already present in cdesktop; ANS adds a model/provider routing and orchestration layer.

## Design principles

1. Keep coding CLIs as first-class executors.
2. Keep providers replaceable.
3. Never require one model to do every job.
4. Prefer free/limited models for low-risk work.
5. Escalate difficult tasks to premium models.
6. Every autonomous run has a plan, acceptance criteria, iteration limit and audit trail.
7. Secrets never enter Git.

## Agent roles

- planner: decomposes the task and defines acceptance criteria
- researcher: gathers external/contextual information
- architect: proposes implementation strategy
- executor: changes the project through a coding agent
- tester: runs checks and reproduces failures
- reviewer: evaluates the result against the task
- fixer: applies corrections
- judge: compares independent candidate solutions

## Execution modes

### CHAT
One selected model answers directly.

### AGENT
planner -> executor -> tester -> reviewer -> fixer loop.

### AUTOPILOT
Same loop, with repeated iterations until acceptance criteria pass, a safety gate is reached, or the iteration budget is exhausted.

### BEST_OF_N
Run N independent candidate solutions, then use a judge to select/synthesize the best result.

## Provider tiers

### Premium
- Claude / Claude Code
- OpenAI / GPT
- Gemini

### Free or limited
- OpenRouter free pool
- provider-specific free tiers
- other compatible endpoints

### Local
- Ollama
- OpenAI-compatible local servers

## Routing signals

The router considers:
- task category
- complexity
- tool requirements
- context size
- multimodal requirements
- provider availability
- rate limits
- estimated cost
- historical success rate

## Security

Autonomous actions must support approval gates for:
- destructive filesystem operations
- production deployment
- credential access
- external side effects
- irreversible Git operations

## Base project

cdesktop is the initial UI/runtime reference because it already wraps Claude Code, Codex, Gemini CLI, OpenCode and Hermes as local child processes and provides sessions, workspaces, worktrees, terminal, diff review, preview and routines.
