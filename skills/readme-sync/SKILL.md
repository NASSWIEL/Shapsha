---
name: readme-sync
description: Met à jour le README.md racine uniquement si la surface utilisateur change (scripts CLI, API publique, dépendances, variables d'env, fichiers d'install). L'agent édite en place ; ce skill ne fait que stager.
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(git diff:*), Bash(git show:*), Bash(git ls-files:*), Bash(git add:*), Bash(git rev-parse:*), Bash(test:*), Bash(grep:*), Read, Glob
---

# /bt-ai:readme-sync

## Context

- Pyproject scripts diff: !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --grep '^[+-].*(\[project.scripts\]|=)' --cap 30 'pyproject.toml' 2>/dev/null`
- __all__ changes: !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --grep '__all__' --cap 10 '*.py' 2>/dev/null`
- Env var additions: !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --grep 'os\.(environ|getenv)' --cap 10 '*.py' 2>/dev/null`
- Pyproject diff: !`git diff -- pyproject.toml 2>/dev/null | head -40`
- Install files changed: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" Dockerfile Makefile pyproject.toml 2>/dev/null`
- README.md exists: !`test -f README.md && echo yes || echo no`

## Your task

Detect signals indicating a user-facing surface change, delegate the README edit to the `readme-patcher` subagent (which edits in place), and stage the result.

### Guards

1. `README.md exists` is `no` → output `No README.md. Run /bt-ai:proj-init.` Stop.

### Signal scan

Compute these flags from the captures above:

- `scripts_changed` = pyproject scripts diff is non-empty AND mentions `[project.scripts]` or its entries
- `all_changed` = `__all__` changes diff is non-empty
- `env_vars_added` = env var additions diff is non-empty
- `deps_added` = the Pyproject diff shows a `+` (or `-`) line that introduces or removes a **package name** in `dependencies`, `optional-dependencies`, or `[tool.poetry.dependencies]`. A pure version-string change in an existing line (e.g., `"requests>=2.30"` → `"requests>=2.31"`) does **not** fire this signal — only name additions/removals do.
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

The agent edits README.md in place via `Edit`/`MultiEdit` and returns:

```json
{"patched": ["README.md"], "sections_touched": ["Utilisation", "Configuration"]}
```

or:

```json
{"patched": [], "reason": "signals fired but no user-facing change"}
```

### Stage and summarize

- `patched` empty → output `No README change needed.` (append the agent's `reason` if present). Stop with success.
- `patched` non-empty → run:
  ```
  git add -- README.md
  ```
  Then output:
  ```
  README patched. Sections: <comma-list of sections_touched>.
  ```

### Hard rules

- **Do not edit README.md yourself.** The agent owns all edits. This skill only stages.
- **Do not parse or apply unified diffs.** Old contract is gone.
- **Do not write helper scripts** into the user's repo.
- **No AskUserQuestion.** Apply or no-op.
- **Single message.** Delegate + stage in one tool-call turn.
