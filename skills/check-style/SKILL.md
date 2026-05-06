---
name: check-style
description: Lint changed Python files with ruff. Print Critical/High findings, auto-fix Low silently, ask before fixing High.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:check-style

Runner: !`python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv`
Changed Python files: !`{ git diff --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git diff --cached --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null; git ls-files --others --exclude-standard -- '*.py' 2>/dev/null; } | sort -u | tr '\n' ' '`
Ruff version: !`R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv); $R run ruff --version 2>&1 | head -1 || echo "ruff: NOT INSTALLED"`

## Operating mode

**Silent.** No narration ("Now I will run ruff..."). Run ruff via `!`, parse JSON output, classify findings, emit only the final summary line and any AskUserQuestion required.

**Runner**: every shell call that runs a Python tool resolves the runner with the prefix `R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv);` then invokes `$R run <tool>`. This dispatches to `uv run` or `poetry run` as configured by `/bt-ai:proj-init`.

## Logic

### Pre-flight

1. If the changed-files line above is empty → output `No changed .py files.` and stop with exit 0.
2. If `ruff: NOT INSTALLED` appears → output `ruff not installed. Run /bt-ai:proj-init.` and stop with non-zero status. Do not attempt to install.
3. If not in a git repository → output `Not a git repository.` and stop with non-zero status.

### Lint

Run:

```
!$R run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null
```

`--force-exclude` is required so that `[tool.ruff].extend-exclude` (set by `proj-init`) applies even when files are passed explicitly on the command line — without it ruff would lint generated files (`*Lexer.py`, `*_pb2.py`, migrations, etc.) that the project has explicitly opted out of style checks.

Parse the JSON array. Each entry has `code`, `filename`, `location.row`, `message`.

### Severity grouping

Map each `code` to a bucket using its prefix:

| Bucket | Prefixes | Action |
|---|---|---|
| **Critical** | `F`, `E9` | print + halt fix mode |
| **High** | `B`, `S` | print + ask user |
| **Low (auto-fix)** | `W`, `D`, `I`, `UP` | silent fix |
| **Medium (hidden)** | `N`, `C` (incl. `C90`), `PL` | never printed, never fixed |

`E1`-`E8` (non-`E9`) are pycodestyle warnings → treat as Low.

### Silent auto-fix Low

```
!$R run ruff check <files> --force-exclude --fix --select=E,W,D,I,UP --silent 2>/dev/null
!$R run ruff format <files> --force-exclude 2>/dev/null
```

Track the count of low-severity fixes applied (re-run with `--statistics` if needed for the count, parsing only the total).

### Branch on Critical/High presence

- **No Critical or High** → output exactly:
  ```
  Fixed N low-severity issues. No critical/high findings.
  ```
  Replace `N` with the count. Stop with exit 0.

- **Critical or High present** → continue to print and ask.

### Print findings

For each Critical and High finding (Medium hidden, Low already fixed), print one line:

```
[CRITICAL] <path>:<line> <code> <message>
[HIGH]     <path>:<line> <code> <message>
```

Group by severity, Critical first. Truncate `message` at 80 chars.

### Ask user

Use AskUserQuestion exactly once with three options:

- `a` — Auto-fix what can be safely fixed (delegates to `style-fixer` agent)
- `s` — Show diffs first (delegates to `style-fixer` agent in dry-run, then re-asks `apply` / `cancel`)
- `n` — Skip; leave findings unfixed

### Delegate to style-fixer

If user picks `a` or `s`, invoke the `style-fixer` agent via Task. Pass JSON payload:

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

If `mode=diff`, then ask user `[apply / cancel]` (AskUserQuestion). On `apply`, re-invoke agent with `mode=apply`.

## Output

Single line, no preamble:

```
<fixed_count> fixed, <remaining_count> remaining.
```

Where `fixed_count` = low-severity fixes + agent-applied High fixes. `remaining_count` = unfixed Critical + skipped High.

Exit codes: 0 if `remaining_count == 0`, non-zero otherwise.

## Edge cases

- Empty changed-files list → `No changed .py files.` exit 0.
- Ruff parse error or stderr non-empty with no JSON → print stderr verbatim, exit non-zero.
- File deleted in diff → already filtered by `--diff-filter=ACMR`.
- All findings are Medium (hidden) → output `Fixed N low-severity issues. No critical/high findings.` exit 0 (Medium ignored by design).
- User chooses `n` with Critical present → exit non-zero with `0 fixed, N remaining.`.
- Git not a repo → `Not a git repository.` exit non-zero.
