---
name: check-style
description: Lint changed Python files with ruff. Print Critical/High findings, auto-fix Low silently, ask before fixing High.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:check-style

Argument: $ARGUMENTS
Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
Changed Python files: !`{ git diff --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git diff --cached --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git ls-files --others --exclude-standard -- '*.py' 2>/dev/null; } | sort -u | tr '\n' ' '`
All Python files (only used if $ARGUMENTS == "all"): !`git ls-files -- '*.py' 2>/dev/null | tr '\n' ' '`
Ruff version: !`R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv); $R run ruff --version 2>&1 | head -1 || echo "ruff: NOT INSTALLED"`

## Argument

| Argument | Behavior |
|---|---|
| (none)  | Lint changed files only (default — recommended for incremental work) |
| `all`   | Lint **every** tracked `.py` file in the repo (slow on large repos; surfaces pre-existing debt) |
| anything else | Output `Unknown argument: <token>. Accepts no argument or 'all'.` and exit non-zero |

## Operating mode

**Silent.** No narration ("Now I will run ruff..."). Run ruff via `!`, parse JSON output, classify findings, emit only the final summary line and any AskUserQuestion required.

**Hermetic — never write into the user's repo.** All helper logic lives in `${CLAUDE_PLUGIN_ROOT}/tools/`. Do not write `classify_*.py`, scratch JSON, log files, or any file that is not the actual user fix. The user's git status must show only intended edits.

**Runner**: `R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv);` then `$R run <tool>`. Dispatches to `uv run` or `poetry run`.

## Logic

### Pre-flight

1. If `$ARGUMENTS` is non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` exit non-zero.
2. Decide the target list:
   - `$ARGUMENTS == "all"` → use the `All Python files` line.
   - else → use `Changed Python files`.
3. If the target list is empty → output `No .py files to lint.` exit 0.
4. If `ruff: NOT INSTALLED` → output `ruff not installed. Run /bt-ai:proj-init.` exit non-zero.
5. If not in a git repo (only required for the changed-files path) → output `Not a git repository.` exit non-zero.

### Lint + classify

Run ruff and pipe its JSON straight into the bundled classifier — no temp files:

```
!R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null | python "${CLAUDE_PLUGIN_ROOT}/tools/classify_ruff.py"
```

`--force-exclude` is required so `[tool.ruff].extend-exclude` (set by `proj-init`) applies even when files are passed explicitly — without it ruff lints generated files (`*Lexer.py`, `*_pb2.py`, migrations) the project has opted out of style checks.

The classifier emits:

```
summary critical=N high=N low=N medium=N
[CRITICAL] <path>:<line> <code> <message>
[HIGH]     <path>:<line> <code> <message>
```

(Medium hidden by design; Low not printed because it's auto-fixed below.)

### Severity table (classifier authoritative)

| Bucket | Prefixes | Action |
|---|---|---|
| **Critical** | `F`, `E9` | print + halt fix mode |
| **High**     | `B`, `S` | print + ask user |
| **Low (auto-fix)** | `E` (non-`E9`), `W`, `D`, `I`, `UP` | silent fix |
| **Medium (hidden)** | `N`, `C` (incl. `C90`), `PL` | never printed, never fixed |

### Silent auto-fix Low

```
!R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run ruff check <files> --force-exclude --fix --select=E,W,D,I,UP --silent 2>/dev/null
!R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run ruff format <files> --force-exclude 2>/dev/null
```

**Stage what we changed.** Ruff/format may have rewritten files. Re-stage only files we actually touched — `git diff --name-only` against the post-fix tree gives the list of currently-modified tracked files; intersect with `<files>` to avoid grabbing unrelated user edits:

```
!for f in <files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

(Skip files that are unchanged after auto-fix — `git diff --quiet` returns 0 = no change, so we only `git add` the modified ones.)

### Branch on Critical/High presence

- **No Critical or High** → output exactly:
  ```
  Fixed N low-severity issues. No critical/high findings.
  ```
  Replace `N` with the count from `--statistics` (re-run if needed). Stop with exit 0.

- **Critical or High present** → continue. The classifier already printed the per-finding lines; do not re-print.

### Ask user

Use AskUserQuestion exactly once, three options:

- `a` — Auto-fix what can be safely fixed (delegates to `style-fixer` agent)
- `s` — Show diffs first (delegates `style-fixer` in dry-run, then re-asks `apply` / `cancel`)
- `n` — Skip; leave findings unfixed

### Delegate to style-fixer

If user picks `a` or `s`, invoke the `style-fixer` agent via Task. Pass JSON:

```json
{
  "mode": "apply" | "diff",
  "files": ["path1.py", "path2.py", ...],
  "findings": [
    {"path": "...", "line": N, "code": "B006", "message": "..."},
    ...
  ]
}
```

Wait for the agent's single-line return: `fixed=N skipped=M files=<list>`.

If `mode=diff`, ask user `[apply / cancel]` (AskUserQuestion). On `apply`, re-invoke agent with `mode=apply`.

After a successful `mode=apply` (fixed > 0), stage the agent's edits so preflight (and any follow-up commit) sees them:

```
!for f in <files from agent return>; do git add -- "$f"; done
```

## Output

Single line, no preamble:

```
<fixed_count> fixed, <remaining_count> remaining.
```

Where `fixed_count` = low-severity fixes + agent-applied High fixes. `remaining_count` = unfixed Critical + skipped High.

Exit codes: 0 if `remaining_count == 0`, non-zero otherwise.

## Edge cases

- Empty target list → `No .py files to lint.` exit 0.
- Ruff parse error or stderr non-empty with no JSON → print stderr verbatim, exit non-zero.
- File deleted in diff → already filtered by `--diff-filter=ACMR`.
- All findings Medium (hidden) → output `Fixed N low-severity issues. No critical/high findings.` exit 0.
- User chooses `n` with Critical present → exit non-zero with `0 fixed, N remaining.`.
- `$ARGUMENTS == "all"` on a >5k file repo → ruff handles it; just slower. No special path needed.
