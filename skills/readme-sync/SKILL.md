---
name: readme-sync
description: Met à jour le README.md racine uniquement si la surface utilisateur change (scripts CLI, API publique, dépendances, variables d'env, fichiers d'install). Applique les patches propres.
disable-model-invocation: true
allowed-tools: Bash(git diff:*), Bash(git show:*), Bash(git ls-files:*), Bash(git add:*), Bash(git rev-parse:*), Bash(python:*), Bash(grep:*), Read, Glob, Edit
---

# /bt-ai:readme-sync

## Context

- Pyproject scripts diff: !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --grep '^[+-].*(\[project.scripts\]|=)' --cap 30 'pyproject.toml' 2>/dev/null`
- __all__ changes: !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --grep '__all__' --cap 10 '*.py' 2>/dev/null`
- Env var additions: !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --grep 'os\.(environ|getenv)' --cap 10 '*.py' 2>/dev/null`
- Pyproject deps name-set diff: !`python "${CLAUDE_PLUGIN_ROOT}/tools/pyproject_deps_diff.py" 2>/dev/null
- Install files changed: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" Dockerfile Makefile pyproject.toml 2>/dev/null`

## Your task

Detect signals indicating a user-facing surface change, delegate patch computation to the `readme-patcher` subagent, and auto-apply a clean patch. Halt only when the patch fails to apply.

### Guards

1. `README.md` is absent → output `No README.md. Run /bt-ai:proj-init.` Stop.
2. Not a git repository → output `Not a git repository.` Stop.

### Signal scan

Compute these flags from the captures above:

- `scripts_changed` = pyproject scripts diff is non-empty AND mentions `[project.scripts]` or its entries
- `all_changed` = `__all__` changes diff is non-empty
- `env_vars_added` = env var additions diff is non-empty
- `deps_added` = pyproject deps name-set diff is non-empty (i.e. an `ADDED:` or `REMOVED:` line is present). Pure version bumps do **not** fire this signal.
- `install_files_changed` = install files list is non-empty

If **all flags are false** → output `No README change needed.` Stop with success.

### Delegate to readme-patcher

Invoke `Task` with subagent `readme-patcher`. Pass JSON:

```json
{
  "readme_path": "README.md",
  "signals": {"scripts_changed": ..., "all_changed": ..., "env_vars_added": ..., "deps_added": ..., "install_files_changed": ...},
  "diff_excerpts": {"scripts": "...", "all": "...", "env_vars": "...", "deps": "...", "install": "..."}
}
```

Wait for the agent's structured JSON:

```json
{"patch": "<unified diff>", "sections_touched": ["Utilisation", "Configuration"]}
```

or:

```json
{"patch": null, "reason": "signals fired but no user-facing semantics change"}
```

### Apply

- `patch` is `null` → output `No README change needed.` Stop with success.
- `patch` is non-empty → apply via `Edit`. If the patch fails to apply, output:
  ```
  Halted: patch failed for README.md:
  <patch text>
  ```
  Stop with non-zero exit.
- On success, stage:
  ```
  git add -- README.md
  ```
  Output one line:
  ```
  README patched. Sections: <comma-list of sections_touched>.
  ```

### Hard rules

- **No AskUserQuestion.** Apply or halt.
- **French tone preserved.** The agent enforces this; this skill does not translate.
- **Single message.** Delegate + apply + stage in one tool-call turn per phase.
