---
name: security
description: Scan changed Python files with bandit. Print findings >= MEDIUM severity AND >= MEDIUM confidence. Refuse auto-fix on dangerous categories.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:security

Argument: $ARGUMENTS
Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
Changed Python files: !`{ git diff --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git diff --cached --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git ls-files --others --exclude-standard -- '*.py' 2>/dev/null; } | sort -u | tr '\n' ' '`
All Python files (only used if $ARGUMENTS == "all"): !`git ls-files -- '*.py' 2>/dev/null | tr '\n' ' '`
Bandit version: !`R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv); $R run bandit --version 2>&1 | head -1 || echo "bandit: NOT INSTALLED"`

## Argument

| Argument | Behavior |
|---|---|
| (none)  | Scan changed files only (default) |
| `all`   | Scan **every** tracked `.py` file in the repo |
| anything else | Output `Unknown argument: <token>. Accepts no argument or 'all'.` and exit non-zero |

## Operating mode

**Silent.** Run bandit via `!`, pipe JSON into the bundled classifier, emit only the final summary and any AskUserQuestion required.

**Hermetic — never write into the user's repo.** All helper logic lives in `${CLAUDE_PLUGIN_ROOT}/tools/`. Do not write `classify_*.py`, scratch JSON, log files, or any file that is not the actual user fix.

**Runner**: `R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv);` then `$R run bandit`.

## Logic

### Pre-flight

1. If `$ARGUMENTS` non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` exit non-zero.
2. Decide target list (changed vs all) per `$ARGUMENTS`.
3. If target list empty → `No .py files to scan.` exit 0.
4. If `bandit: NOT INSTALLED` → `bandit not installed. Run /bt-ai:proj-init.` exit non-zero.
5. If not in a git repo (changed-files path only) → `Not a git repository.` exit non-zero.

### Scan + classify

Pipe bandit JSON straight into the bundled classifier:

```
!R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run bandit -f json -ll -ii <files> 2>/dev/null | python "${CLAUDE_PLUGIN_ROOT}/tools/classify_bandit.py"
```

`-ll` filters severity to >= MEDIUM, `-ii` confidence to >= MEDIUM. The classifier emits:

```
summary blocked=N fixable=N total=N
[<sev>/<conf>] [BLOCKED|FIXABLE] <path>:<line> <code> <message>
```

The classifier's BLOCKED set mirrors the table below — keep them in lockstep.

### BLOCKED set (no auto-fix; human-only)

Dangerous-execution (mechanically rewriting masks intent):
- `B102` exec, `B307` eval, `B301` pickle, `B324` insecure hash (md5/sha1)
- `B501`-`B508` (cryptography family)
- `B602`-`B608` (subprocess / shell)
- `B610`, `B611` (SQL injection)
- `B701` jinja2 autoescape

Context-sensitive (intentional vs accidental depends on deployment):
- `B104` bind to 0.0.0.0 (intentional in containers — also skipped at the bandit-config level via `[tool.bandit].skips`)
- `B105`-`B107` hardcoded password heuristics (high false-positive rate)
- `B108` hardcoded `/tmp` usage

Everything else → FIXABLE (most still report-only — see security-fixer agent).

### Branch

- **No findings** → `No security findings >= MEDIUM/MEDIUM.` exit 0.
- **All findings BLOCKED** → `<N> findings require manual fix.` skip AskUserQuestion. Exit non-zero.
- **At least one FIXABLE** → ask.

### Ask user

AskUserQuestion (one prompt, three options):

- `a` — Auto-fix the FIXABLE ones (delegates to `security-fixer`)
- `s` — Show diffs first (`security-fixer` in `mode=diff`, then re-ask `apply / cancel`)
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

Forward only FIXABLE findings; never forward BLOCKED ones (the agent has its own refusal list as defense in depth).

Wait for agent's line: `fixed=N reported=M refused=K`.

After a successful `mode=apply` (fixed > 0), stage the agent's edits so preflight and follow-up commits see them:

```
!for f in <distinct paths from forwarded findings>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

(Use `git diff --quiet` per file to skip ones the agent reported-only on.)

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
- pyproject.toml absent → bandit uses defaults.
