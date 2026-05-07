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

Pipe ruff JSON straight into the bundled classifier — never write scratch files into the user's repo:

```
R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null | python "${CLAUDE_PLUGIN_ROOT}/tools/classify_ruff.py"
```

`--force-exclude` is required so `[tool.ruff].extend-exclude` (set by `proj-init`) applies even when files are passed explicitly.

The classifier prints:

```
summary critical=N high=N low=N medium=N
[CRITICAL] <path>:<line> <code> <message>
[HIGH]     <path>:<line> <code> <message>
```

Severity table (classifier authoritative):

| Bucket | Prefixes | Action |
|---|---|---|
| **Critical** | `F`, `E9` | print + halt — human must read |
| **High**     | `B`, `S` | auto-applied via `--unsafe-fixes` only for the safe whitelist (B007/B009/B010/B011, S101 in tests/); otherwise printed and counted as remaining |
| **Low (auto-fix)** | `E` non-`E9`, `W`, `D`, `I`, `UP` | silent fix |
| **Medium (hidden)** | `N`, `C`, `PL` | never printed, never fixed |

### Auto-apply (silent)

Run these in order. They produce no narration:

```
R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py")
$R run ruff check <files> --force-exclude --fix --select=E,W,D,I,UP --silent 2>/dev/null
$R run ruff check <files> --force-exclude --fix --unsafe-fixes --select=B007,B009,B010,B011 --silent 2>/dev/null
$R run ruff format <files> --force-exclude 2>/dev/null
```

Stage only files actually modified (skip untouched files to avoid grabbing unrelated user edits):

```
for f in <files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

### Branch on Critical

- `critical == 0` → output one line:
  ```
  Style: <fixed_low+fixed_high> auto-fixed, <high_remaining> high findings remain.
  ```
  Stop with success. The High findings that were not in the safe whitelist are surfaced (one line each) but do not halt the suite — they are advisory, the user can choose to address them in a follow-up.

- `critical > 0` → the classifier already printed the per-finding lines. Output one final line:
  ```
  Halted: <critical> critical style findings require human review.
  ```
  Stop with non-zero exit so preflight halts.

### Hard rules

- **No AskUserQuestion.** This skill never blocks the user with prompts. Auto-fix or halt.
- **Never edit files manually** via `Edit`. All fixes come from ruff.
- **Hermetic.** Never write `classify_*.py`, scratch JSON, or log files into the user's repo. All helper logic lives under `${CLAUDE_PLUGIN_ROOT}/tools/`.
- **Single message.** You have the capability to call multiple tools in a single response. You MUST do classify + auto-fix + stage in one message. Do not send any other text besides the tool calls and the final summary line.
