# CLAUDE.md

Read `docs/current-state.md` before making repo-specific claims or starting work.

Use the shared `repo-status-continuity` skill for start/end-of-work discipline. For a quick context load, run:

```bash
~/.openclaw/workspace/scripts/bootstrap-repo-context.sh
```

Before finishing non-trivial repo work, update `docs/current-state.md`, refresh its generated block, and run:

```bash
~/.agents/scripts/repo-status check --repo "$PWD"
```
