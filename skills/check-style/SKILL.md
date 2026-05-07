---
name: check-style
description: "Lint des fichiers Python modifiés avec ruff. Affiche tous les findings clairement. S'arrête sur les critiques (F*, E9*) avec leur liste complète. Demande consentement avant d'appliquer les fixes non-critiques."
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

Run ruff on the changed Python files (or `all` files if `$ARGUMENTS == "all"`), display findings as observations, halt with the **full list** of Critical findings if any, otherwise **ask consent** before applying fixes for non-critical findings.

### Guards

1. `$ARGUMENTS` is non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `ruff: NOT INSTALLED` → output `ruff not installed. Run /bt-ai:proj-init.` Stop.
3. Target list (resolved per `$ARGUMENTS`) is empty → output `No .py files to lint.` Stop with success.

### Lint and classify

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). Run ruff with JSON output. **Append `|| true`** so ruff's exit code 1 (which only means "findings exist") does not surface as a scary error in the user's terminal:

```
<runner> run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null || true
```

`--force-exclude` is required so `[tool.ruff].extend-exclude` (set by `proj-init`) applies even when files are passed explicitly.

The output is a JSON array. Each finding has fields `code`, `filename`, `location.row`, `message`. Read the JSON in memory and classify each finding by its `code` prefix into three buckets:

| Bucket | Prefixes / matches | Routing |
|---|---|---|
| **`critical[]`** | `F*`, `E9*` | Will halt with full listing — never auto-fixed (real bugs need human review). |
| **`safe_fixable[]`** | `E` (not `E9`), `W`, `D`, `I`, `UP`, **plus** `B007`/`B009`/`B010`/`B011`, **plus** `S101` only when `filename` contains `tests/` | Eligible for auto-fix with user consent. |
| **`advisory[]`** | All other `B*`, `S*` outside the safe whitelist | Reported only — no automatic fix path; user must address manually. |

Codes that match no prefix above (`N*`, `C*`, `PL*`, etc.) → ignore silently.

Do **not** print per-finding lines yet. Hold the buckets in memory and branch below.

### Branch 1 — Critical findings present

If `len(critical) > 0`, output the full list and halt. **No question, no auto-fix** — Critical findings are real bugs (undefined names, syntax errors, etc.) that require a human to read the code:

```
Halted: <N> critical style finding(s) require human review:
  - <filename>:<row> <code> <message>
  - <filename>:<row> <code> <message>
  ...
```

Stop with non-zero exit so preflight halts.

### Branch 2 — No findings at all

If `len(critical) == 0` AND `len(safe_fixable) == 0` AND `len(advisory) == 0`:

```
Style: no findings.
```

Stop with success.

### Branch 3 — Only advisory (no fixable, no critical)

If `len(critical) == 0` AND `len(safe_fixable) == 0` AND `len(advisory) > 0`:

Print the advisory list as observations (not directives), then stop with success — there is nothing to ask, the user must address them by hand.

```
Style: <N> non-critical finding(s) noted (no automatic fix available):
  - <filename>:<row> <code> <message>
  ...
```

### Branch 4 — Fixable findings present (with optional advisory)

If `len(critical) == 0` AND `len(safe_fixable) > 0`:

1. Print the combined non-critical list as observations:
   ```
   Found <K> non-critical style finding(s):
     - <filename>:<row> <code> <message>     [from safe_fixable]
     - <filename>:<row> <code> <message>     [from advisory]
     ...
   ```
   List `safe_fixable[]` first, then `advisory[]`. Each line is just the finding — no imperative phrasing on the skill's part.

2. Use the `AskUserQuestion` tool with one question:
   - **header**: `Style fixes`
   - **question**: `Do you want me to fix these issues that are not critical?`
   - **multiSelect**: `false`
   - **options**:
     - label `Yes`, description `Apply ruff auto-fixes for the safe non-critical findings`
     - label `No`, description `Skip auto-fix; leave the code as-is`

3. On `No`:
   ```
   Style: <K> non-critical finding(s) noted, no fixes applied.
   ```
   Stop with success.

4. On `Yes` → run the auto-fix sequence below.

### Auto-fix (only after `Yes` consent)

Run in order; each command appends `|| true` so non-zero from "fixes applied" does not surface as an error:

```
<runner> run ruff check <files> --force-exclude --fix --select=E,W,D,I,UP --silent 2>/dev/null || true
<runner> run ruff check <files> --force-exclude --fix --unsafe-fixes --select=B007,B009,B010,B011 --silent 2>/dev/null || true
<runner> run ruff format <files> --force-exclude 2>/dev/null || true
```

If any item in `safe_fixable[]` had `code == "S101"` AND its filename contains `tests/`, also run:

```
<runner> run ruff check <files> --force-exclude --fix --unsafe-fixes --select=S101 --silent 2>/dev/null || true
```

Stage only files actually modified (skip untouched files to avoid grabbing unrelated user edits):

```
for f in <files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

### Final summary (post-fix)

```
Style: <fixed_count> auto-fixed, <advisory_count> advisory finding(s) remain.
```

`fixed_count` = `len(safe_fixable)` (those were targeted by ruff --fix). `advisory_count` = `len(advisory)` (those were never in the auto-fix path).

Stop with success.

### Hard rules

- **Halt on Critical = list, never ask.** Critical findings (`F*`, `E9*`) are real bugs; never offer to "fix" them. Always print the full list before halting.
- **Consent before edits.** For non-critical findings, `AskUserQuestion` once before any auto-fix. The user controls when their code is touched.
- **No imperative phrasing.** When listing findings, present them as observations (`<filename>:<row> <code> <message>`). The skill itself never tells the user "remove X" — that's ruff's job inside its own `<message>` field.
- **`|| true` on ruff commands.** Ruff exits 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Never edit files manually** via `Edit`. All fixes come from ruff.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo. The model classifies ruff's JSON output directly.
