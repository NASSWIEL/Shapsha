---
name: readme-sync
description: Update root README.md only when user-facing surface changes (CLI scripts, public API, dependencies, env vars, install files).
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Edit
---

# /bt-ai:readme-sync

Pyproject scripts diff: !`{ git diff -- pyproject.toml 2>/dev/null; git diff --cached -- pyproject.toml 2>/dev/null; } | grep -E '^[+-].*\\[project.scripts\\]|^[+-].*=.*' | head -30`
__all__ changes: !`{ git diff -- '*.py' 2>/dev/null; git diff --cached -- '*.py' 2>/dev/null; for f in $(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null); do [ -f "$f" ] && grep -H '__all__' "$f" 2>/dev/null; done; } | grep -E '^[+-].*__all__|__all__' | head -10`
Env var additions: !`{ git diff -- '*.py' 2>/dev/null; git diff --cached -- '*.py' 2>/dev/null; for f in $(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null); do [ -f "$f" ] && grep -H -E 'os\\.(environ|getenv)' "$f" 2>/dev/null; done; } | grep -E '^\\+.*os\\.(environ|getenv)|os\\.(environ|getenv)' | head -10`
Pyproject deps name-set diff: !`python -c "
import re, subprocess, sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib

def names(deps):
    out = set()
    for d in deps or []:
        m = re.match(r'[A-Za-z0-9_.\\-]+', str(d).strip())
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
Install files changed: !`{ git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -E '^(Dockerfile|Makefile|pyproject\\.toml)$' | head -5`

## Operating mode

**Silent.** No "Scanning for signals..." narration. Compute signals via shell, branch, delegate to `readme-patcher` only if signals fire.

## Logic

### Pre-flight

1. If `README.md` is absent → output `No README.md. Run /bt-ai:proj-init.` exit non-zero.
2. If not a git repository → output `Not a git repository.` exit non-zero.

### Signal scan

Compute these flags from the captures above:

- `scripts_changed` = pyproject scripts diff is non-empty AND mentions `[project.scripts]` or its entries
- `all_changed` = `__all__` changes diff is non-empty
- `env_vars_added` = env var additions diff is non-empty
- `deps_added` = pyproject deps name-set diff is non-empty (i.e. an `ADDED:` or `REMOVED:` line is present). Pure version bumps do **not** fire this signal.
- `install_files_changed` = install files list is non-empty

If **all flags are false** → output `No README change needed.` exit 0.

### Delegate to readme-patcher

Invoke `Task` with agent `readme-patcher`. Pass JSON:

```json
{
  "readme_path": "README.md",
  "signals": {
    "scripts_changed": true|false,
    "all_changed": true|false,
    "env_vars_added": true|false,
    "deps_added": true|false,
    "install_files_changed": true|false
  },
  "diff_excerpts": {
    "scripts": "<excerpt>",
    "all": "<excerpt>",
    "env_vars": "<excerpt>",
    "deps": "<excerpt>",
    "install": "<excerpt>"
  }
}
```

Wait for agent's structured JSON return:

```json
{"patch": "<unified diff>", "sections_touched": ["Utilisation", "Configuration"]}
```

or:

```json
{"patch": null, "reason": "signals fired but no user-facing semantics change"}
```

### Branch on response

- `patch` is `null` → output `No README change needed.` exit 0.
- `patch` non-empty → continue to ask.

### Print and ask

Print:

```
README patch proposed. Sections: <comma-list of sections_touched>.
```

AskUserQuestion (three options):

- `a` — Apply
- `s` — Show diff first (print, then re-ask `apply / cancel`)
- `n` — Skip

### Apply

If user picks `a`, use `Edit` to apply the unified diff. If the patch fails to apply, output `Patch failed for README.md.` followed by patch text, exit non-zero.

After a successful apply, stage README.md so preflight and follow-up commits see it:

```
!git add -- README.md
```

## Output

Single line, no preamble:

```
README patched.
```

Or:

```
No README change needed.
```

Exit non-zero if patch fails to apply.

## Edge cases

- README has TOC anchors → patcher must regenerate matching TOC entries. Parent does not enforce; agent is responsible.
- README is in French → patcher writes in French (matches existing tone). Hardcoded in agent's instructions.
- Signals fire but no actual user-facing semantics change (e.g., dependency version bump only) → agent returns `patch: null`, parent prints `No README change needed.`.
- Patch fails → exit non-zero so `/preflight` halts.
