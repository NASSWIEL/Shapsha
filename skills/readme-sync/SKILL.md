---
name: readme-sync
description: Update root README.md only when user-facing surface changes (CLI scripts, public API, dependencies, env vars, install files). Auto-applies clean patches.
disable-model-invocation: true
allowed-tools: Bash(git diff:*), Bash(git show:*), Bash(git ls-files:*), Bash(git add:*), Bash(git rev-parse:*), Bash(python:*), Bash(grep:*), Read, Glob, Edit
---

# /bt-ai:readme-sync

## Context

- Pyproject scripts diff: !`{ git diff -- pyproject.toml 2>/dev/null; git diff --cached -- pyproject.toml 2>/dev/null; } | grep -E '^[+-].*\[project.scripts\]|^[+-].*=.*' | head -30`
- __all__ changes: !`{ git diff -- '*.py' 2>/dev/null; git diff --cached -- '*.py' 2>/dev/null; for f in $(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null); do [ -f "$f" ] && grep -H '__all__' "$f" 2>/dev/null; done; } | grep -E '^[+-].*__all__|__all__' | head -10`
- Env var additions: !`{ git diff -- '*.py' 2>/dev/null; git diff --cached -- '*.py' 2>/dev/null; for f in $(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null); do [ -f "$f" ] && grep -H -E 'os\.(environ|getenv)' "$f" 2>/dev/null; done; } | grep -E '^\+.*os\.(environ|getenv)|os\.(environ|getenv)' | head -10`
- Pyproject deps name-set diff: !`python -c "
import re, subprocess, sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib

def names(deps):
    out = set()
    for d in deps or []:
        m = re.match(r'[A-Za-z0-9_.\-]+', str(d).strip())
        if m:
            out.add(m.group(0).lower())
    return out

def project_deps(toml_bytes):
    try:
        data = tomllib.loads(toml_bytes.decode('utf-8'))
    except Exception:
        return None
    proj = data.get('project', {}).get('dependencies', [])
    poetry = data.get('tool', {}).get('poetry', {}).get('dependencies', {})
    poetry_names = list(poetry.keys()) if isinstance(poetry, dict) else []
    return (names(proj) | names(poetry_names)) - {'python'}

try:
    head = subprocess.run(['git','show','HEAD:pyproject.toml'], capture_output=True, check=False).stdout
    cur = open('pyproject.toml','rb').read()
except Exception:
    sys.exit(0)

old = project_deps(head) if head else set()
new = project_deps(cur) or set()
added = sorted(new - old)
removed = sorted(old - new)
if added: print('ADDED:', ' '.join(added))
if removed: print('REMOVED:', ' '.join(removed))
" 2>/dev/null | head -10`
- Install files changed: !`{ git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -E '^(Dockerfile|Makefile|pyproject\.toml)$' | head -5`

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
