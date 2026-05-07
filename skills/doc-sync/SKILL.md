---
name: doc-sync
description: Sync French docs in docs/ with code changes from git diff. Auto-applies clean patches; halts only when patches fail to apply.
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git add:*), Bash(git rev-parse:*), Bash(cat:*), Read, Glob, Edit
---

# /bt-ai:doc-sync

## Context

- Diff stat (tracked changes): !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --stat --cap 50 '*.py' 'pyproject.toml' '*.md' 2>/dev/null`
- Untracked files: !`git ls-files --others --exclude-standard -- '*.py' 'pyproject.toml' '*.md' 2>/dev/null | head -20`
- Diff (capped at 500 lines, includes untracked as new-file hunks): !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --cap 500 '*.py' 'pyproject.toml' 2>/dev/null`

## Your task

Detect impacted French docs from the code diff, compute minimal unified-diff patches via the `doc-patcher` subagent, and auto-apply clean ones. Halt only when a patch fails to apply.

### Guards

1. Diff stat is empty (no changes in `*.py`, `pyproject.toml`, or `*.md`) → output `No code changes detected. Docs unchanged.` Stop with success.
2. `docs/` folder is absent → output `docs/ folder absent. Run /bt-ai:proj-init first.` Stop.

### Delegate to doc-patcher

Invoke `Task` with subagent `doc-patcher`. Pass JSON:

```json
{
  "diff": "<full text from above, capped at 500 lines>",
  "docs_path": "docs/",
  "routing": {
    "data-model.md": "class definitions, dataclass fields, schema changes, entity relationships",
    "contracts.md": "new endpoint, route, public method, event signature, API contract",
    "architecture.md": "new module/service, dependency added in pyproject, infrastructure change",
    "glossaire.md": "new business term, acronym, domain concept",
    "fonctionnel.md": "user-visible behavior, business rule, use case",
    "index.md": "always update §2 (freshness table) for any other doc patched"
  }
}
```

Wait for the agent's structured JSON return:

```json
{
  "patches": [{"file": "docs/data-model.md", "patch": "<unified diff>", "summary": "..."}],
  "skipped": [{"file": "docs/architecture.md", "reason": "drift too large; needs human"}]
}
```

### Apply

- `patches` empty AND `skipped` empty → output `No doc updates needed.` Stop with success.
- Otherwise, for each patch entry: use `Edit` to apply the unified diff. If a hunk does not apply cleanly, output:
  ```
  Halted: patch failed for <file>:
  <patch text>
  ```
  Stop with non-zero exit. The user merges manually.
- After all successful patches:
  ```
  for f in <successfully patched files>; do git add -- "$f"; done
  ```

### Output

Single line summary. If `skipped` is empty:
```
Patched N docs: <comma-list>.
```

If `skipped` is non-empty:
```
Patched N docs: <list>. Skipped M: <comma-list of reasons>.
```

If nothing was patched (all skipped) → `No doc updates needed. M skipped: <reasons>.`

### Hard rules

- **No AskUserQuestion.** Apply or halt. The user reviews via `git diff` before commit.
- **Subagent has its own context.** It reads only the routed docs; do not echo doc content into this skill's prompt.
- **Single message.** Delegate + apply + stage in one tool-call turn per phase.
