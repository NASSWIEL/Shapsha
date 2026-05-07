---
name: check-style
description: Lint des fichiers Python modifiés avec ruff. Applique les corrections sûres en silence. S'arrête uniquement sur les findings critiques (F*, E9*).
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git add:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git status:*), Bash(git rev-parse:*)
---

# /bt-ai:check-style

## Context

- Argument: $ARGUMENTS
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
- Changed Python files: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" 2>/dev/null`
- All Python files (only used if $ARGUMENTS == "all"): !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --all 2>/dev/null`
- Ruff version: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe ruff 2>/dev/null`

## Your task

Run ruff on the changed Python files (or `all` files if `$ARGUMENTS == "all"`), auto-apply safe fixes silently, and emit a single summary line. Halt only when Critical findings remain — Critical means a human must read the code, not a regex.

### Guards

1. `$ARGUMENTS` is non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `ruff: NOT INSTALLED` → output `ruff not installed. Run /bt-ai:proj-init.` Stop.
3. Target list (resolved per `$ARGUMENTS`) is empty → output `No .py files to lint.` Stop with success.

### Lint and classify

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). Run ruff with JSON output:

```
<runner> run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null
```

`--force-exclude` is required so `[tool.ruff].extend-exclude` (set by `proj-init`) applies even when files are passed explicitly.

The output is a JSON array. Each finding has fields `code`, `filename`, `location.row`, `message`. Read the JSON and classify each finding by its `code` prefix, printing one line per Critical/High finding to stdout:

| Bucket | Prefixes | Action |
|---|---|---|
| **Critical** | `F`, `E9` | Print `[CRITICAL] <filename>:<row> <code> <message>`. Will halt. |
| **High** | `B`, `S` | If `code` is in `{B007, B009, B010, B011}` OR (`code == "S101"` AND `filename` contains `tests/`) → save for safe auto-fix below. Otherwise print `[HIGH] <filename>:<row> <code> <message>`; counts toward `high_remaining`. |
| **Low** | `E` (not `E9`), `W`, `D`, `I`, `UP` | Save for silent auto-fix below. |
| **Medium** | `N`, `C`, `PL` | Ignore silently. |

Codes that match no prefix above → ignore.

Track three counters: `critical_count`, `high_remaining`, `total_fixed` (Low + safe-High that will be auto-fixed).

### Auto-apply (silent)

If any Low or safe-High findings were classified, run these in order. They produce no narration:

```
<runner> run ruff check <files> --force-exclude --fix --select=E,W,D,I,UP --silent 2>/dev/null
<runner> run ruff check <files> --force-exclude --fix --unsafe-fixes --select=B007,B009,B010,B011 --silent 2>/dev/null
<runner> run ruff format <files> --force-exclude 2>/dev/null
```

If any safe-High finding was `S101` in a `tests/` file, also run:

```
<runner> run ruff check <files> --force-exclude --fix --unsafe-fixes --select=S101 --silent 2>/dev/null
```

Stage only files actually modified (skip untouched files to avoid grabbing unrelated user edits):

```
for f in <files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

### Branch on Critical

- `critical_count == 0` → output one line:
  ```
  Style: <total_fixed> auto-fixed, <high_remaining> high findings remain.
  ```
  Stop with success. The High findings outside the safe whitelist were already printed; they are advisory and do not halt the suite.

- `critical_count > 0` → the per-finding `[CRITICAL]` lines were already printed during classification. Output one final line:
  ```
  Halted: <critical_count> critical style findings require human review.
  ```
  Stop with non-zero exit so preflight halts.

### Hard rules

- **No AskUserQuestion.** This skill never blocks the user with prompts. Auto-fix or halt.
- **Never edit files manually** via `Edit`. All fixes come from ruff.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo. The model classifies ruff's JSON output directly.
- **Single message.** Call all required tools in one response. Do not narrate between tool calls; print the per-finding lines and the final summary line only.
