---
name: security
description: Scan changed Python files with bandit. Print findings >= MEDIUM severity AND >= MEDIUM confidence. Refuse auto-fix on dangerous categories.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:security

Runner: !`python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv`
Changed Python files: !`{ git diff --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git diff --cached --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git ls-files --others --exclude-standard -- '*.py' 2>/dev/null; } | sort -u | tr '\n' ' '`
Bandit version: !`R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv); $R run bandit --version 2>&1 | head -1 || echo "bandit: NOT INSTALLED"`

## Operating mode

**Silent.** Run bandit via `!`, parse JSON, classify FIXABLE vs BLOCKED, emit only the final summary line and any AskUserQuestion required.

**Runner**: shell calls that run Python tools resolve the runner with `R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv);` then invoke `$R run bandit`. Dispatches to `uv run` or `poetry run` as set by `/bt-ai:proj-init`.

## Logic

### Pre-flight

1. If changed-files is empty → output `No changed .py files.` exit 0.
2. If `bandit: NOT INSTALLED` → output `bandit not installed. Run /bt-ai:proj-init.` exit non-zero.
3. If not a git repository → output `Not a git repository.` exit non-zero.

### Scan

```
!$R run bandit -f json -ll -ii <files> 2>/dev/null
```

`-ll` filters severity to >= MEDIUM. `-ii` filters confidence to >= MEDIUM. Bandit JSON output has `results` array with `test_id`, `filename`, `line_number`, `issue_severity`, `issue_confidence`, `issue_text`.

### Classify per finding

The **no-auto-fix blacklist** (must be `[BLOCKED]`):

Dangerous-execution rules (mechanically rewriting these would mask intent):
- `B102` exec
- `B307` eval
- `B301` pickle deserialization
- `B324` insecure hash (md5, sha1)
- `B501` through `B508` (cryptography family)
- `B602` through `B608` (subprocess / shell)
- `B610`, `B611` (SQL injection)
- `B701` jinja2 autoescape

Context-sensitive rules (the finding may be intentional and the right fix depends on deployment context):
- `B104` hardcoded bind to all interfaces (`0.0.0.0`) — intentional for containers
- `B105` hardcoded password string (high false-positive rate on configuration keys)
- `B106` hardcoded password as function argument (same)
- `B107` hardcoded password as default argument (same)
- `B108` hardcoded `/tmp` directory usage — may be deliberate

All others → `[FIXABLE]` (in the sense the agent may consider them; most still won't be auto-edited — see security-fixer agent).

### Print findings

For each finding, one line:

```
[<sev>/<conf>] [<class>] <path>:<line> <code> <message>
```

Examples:

```
[HIGH/HIGH] [BLOCKED]  src/app.py:42 B307 Use of insecure function eval
[MED/HIGH]  [FIXABLE]  src/api.py:55 B101 Use of assert detected
```

Truncate `message` at 80 chars.

### Branch

- **No findings** → output `No security findings >= MEDIUM/MEDIUM.` exit 0.
- **All findings BLOCKED** → output `<N> findings require manual fix.` and skip AskUserQuestion. Exit non-zero.
- **At least one FIXABLE** → continue to ask.

### Ask user

AskUserQuestion (one prompt, three options):

- `a` — Auto-fix the FIXABLE ones (delegates to `security-fixer` agent)
- `s` — Show diffs first (agent in `mode=diff`, then re-ask `apply / cancel`)
- `n` — Skip

### Delegate to security-fixer

Invoke `Task` with agent `security-fixer`. Pass JSON:

```json
{
  "mode": "apply" | "diff",
  "findings": [
    {"path": "...", "line": N, "code": "B101", "severity": "MEDIUM", "confidence": "HIGH", "message": "..."},
    ...
  ]
}
```

Only forward FIXABLE findings; never forward BLOCKED ones (the agent has its own refusal list as defense in depth).

Wait for agent's single line: `fixed=N reported=M refused=K`.

## Output

Single line, no preamble:

```
<fixed> fixed, <blocked> require manual fix.
```

Exit codes: 0 if `blocked == 0`, non-zero otherwise.

## Edge cases

- Bandit JSON malformed → print stderr verbatim, exit non-zero.
- Bandit `[tool.bandit]` config errors → re-run without config: `!$R run bandit -f json -ll -ii --configfile /dev/null <files>`.
- All findings BLOCKED → no AskUserQuestion shown.
- User picks `n` → exit 0 (the user chose not to act; that is not an error).
- Findings touch a file already removed from disk → bandit will skip; ignore.
- pyproject.toml absent → bandit uses defaults; OK.
