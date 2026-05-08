---
name: check-style
description: "Lint des fichiers Python modifiés avec ruff. Affiche chaque finding avec un extrait de code (3 lignes). S'arrête sur les critiques (F*, E9*). Pour le reste : ruff fait les fixes mécaniques, puis fan-out parallèle (un sous-agent style-fixer par fichier, en simultané) pour les docstrings D1xx et les renommages locaux N803/N806 ; le parent gère les renommages cross-file N801/N802 via Grep + MultiEdit."
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git add:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git status:*), Bash(git rev-parse:*), Read, Edit, MultiEdit, Grep
---

# /bt-ai:check-style

## Context

- Argument: $ARGUMENTS
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
- Changed Python files: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" 2>/dev/null`
- All Python files (only used if $ARGUMENTS == "all"): !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --all 2>/dev/null`
- Ruff version: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe ruff 2>/dev/null`

## Your task

Run ruff on the changed Python files (or `all` files if `$ARGUMENTS == "all"`), display **every** finding with a 3-line code snippet, halt with the full list of Critical findings if any, otherwise **ask consent** before applying fixes. Fixes are split into three engines:

- **`safe_fixable[]`** → `ruff --fix` (mechanical: imports, whitespace, formatting, the D-codes ruff can auto-fix). Ruff parallelises internally; one shell call covers all files.
- **`model_fixable[]` per-file work** → fan-out parallèle: **one `style-fixer` subagent per impacted file, in a single message**. Each agent handles `D1xx` docstring inserts and `N803`/`N806` (argument/local-variable) renames inside its own file. With ≤ 10 files this is one batch; ≥ 10, split into batches of 10 across consecutive messages.
- **`model_fixable[]` cross-file work** → done by the **parent**: `N801` (class) and `N802` (function) renames need `Grep` to find every caller, then `MultiEdit` per touched file. Subagents refuse these by design.

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

The output is a JSON array. Each finding has fields `code`, `filename`, `location.row`, `location.column`, `message`, and `fix` (object or null). Read the JSON in memory and classify each finding into **four** buckets:

| Bucket | Codes | Routing |
|---|---|---|
| **`critical[]`** | `F*`, `E9*` | Halt with full listing — never auto-fixed (real bugs need human review). |
| **`safe_fixable[]`** | `E` (not `E9`), `W`, `I`, `UP`, **plus** any `D*` whose ruff `fix` field is non-null, **plus** `B007`/`B009`/`B010`/`B011`, **plus** `S101` only when `filename` contains `tests/` | Ruff `--fix` handles them. |
| **`model_fixable[]`** | `D100`/`D101`/`D102`/`D103`/`D104`/`D105`/`D106`/`D107` whose ruff `fix` field is null (missing docstring — ruff cannot generate text), **plus** `N801`/`N802`/`N803`/`N806` (renames) | Model edits with `Edit`/`MultiEdit` (and `Grep` for class/function renames). |
| **`advisory[]`** | All other `B*`, `S*`, `C90*`, `PL*`, and any `N*` outside the rename whitelist | Reported only — no automatic fix path; user must address manually. |

Hold the buckets in memory. **Do not print yet.** Branch below.

### Display findings — every finding gets a code snippet

For every finding (in any bucket), render a 3-line block. To get the snippet, `Read` the target file with `offset = max(1, location.row - 1)` and `limit = 3`. Format:

```
  <filename>:<row>:<col> <code> — <message>
    <row-1> | <previous source line>
  > <row>   | <offending source line>
    <row+1> | <next source line>
```

If the file does not have a previous/next line (top/bottom), omit that side. Plain ASCII; no colors.

For `model_fixable[]` blocks, append a `→ <action>:` line that previews what the model will do:

| Code | Action line template |
|---|---|
| `D100` | `→ Insert a module-level docstring at line 1 (one-line summary derived from the file's name and imports).` |
| `D101` | `→ Insert a Google-style class docstring under \`class <Name>:\`.` |
| `D102` | `→ Insert a Google-style method docstring under \`def <name>(...):\`.` |
| `D103` | `→ Insert a Google-style function docstring under \`def <name>(...):\`.` |
| `D104` | `→ Insert a package docstring at the top of \`__init__.py\`.` |
| `D105` | `→ Insert a one-line docstring under the magic method.` |
| `D106` | `→ Insert a one-line docstring under the nested class.` |
| `D107` | `→ Insert a one-line docstring under \`__init__\` describing what the constructor sets up.` |
| `N801` | `→ Rename class \`<old>\` → \`<new>\` (CapWords) across the project.` |
| `N802` | `→ Rename function \`<old>\` → \`<new>\` (lower_snake_case) across the project.` |
| `N803` | `→ Rename argument \`<old>\` → \`<new>\` (lower_snake_case) inside this function.` |
| `N806` | `→ Rename local variable \`<old>\` → \`<new>\` (lower_snake_case) inside this function.` |

`<old>` is extracted from the ruff `message` (it is usually quoted in backticks: ``Function name `getUser` should be lowercase``). Compute `<new>`:

- **CapWords** (`N801`): split on `_` and on lowercase→uppercase boundaries, capitalize each token, concat. `myClass` → `MyClass`, `my_class` → `MyClass`.
- **lower_snake_case** (`N802`/`N803`/`N806`): insert `_` before every uppercase letter that follows a lowercase one, lowercase everything. `getUser` → `get_user`, `MyVar` → `my_var`, `HTTPServer` → `http_server`.

### Branch 1 — Critical findings present

If `len(critical) > 0`, print only the critical block(s) (with snippets) and halt. **No question, no auto-fix** — Critical findings are real bugs (undefined names, syntax errors) that require a human to read the code:

```
Halted: <N> critical style finding(s) require human review:

<critical blocks with snippets>
```

Stop with non-zero exit so preflight halts.

### Branch 2 — No findings at all

If all four buckets are empty:

```
Style: no findings.
```

Stop with success.

### Branch 3 — Only advisory (no fixable, no model_fixable, no critical)

Print the advisory list with snippets, then stop with success — there is nothing to ask, the user must address them by hand:

```
Style: <N> non-critical finding(s) noted (no automatic fix available):

<advisory blocks with snippets>
```

### Branch 4 — Fixable findings present (with optional advisory)

If `len(critical) == 0` AND (`len(safe_fixable) > 0` OR `len(model_fixable) > 0`):

1. Print every finding grouped by bucket, with snippets, so the user knows what each will become:

   ```
   Found <K> non-critical style finding(s):

   --- ruff will auto-fix (<count_safe>) ---
   <safe_fixable blocks with snippets>

   --- I will fix manually with Edit/MultiEdit (<count_model>) ---
   <model_fixable blocks with snippets, each followed by its → action line>

   --- advisory only, no automatic fix (<count_advisory>) ---
   <advisory blocks with snippets>
   ```

   Omit a `---` section when its count is 0.

2. Use the `AskUserQuestion` tool with one question:
   - **header**: `Style fixes`
   - **question**: `Do you want me to fix these non-critical issues?`
   - **multiSelect**: `false`
   - **options**:
     - label `Yes`, description `Apply ruff auto-fixes and let me edit docstrings/renames manually`
     - label `No`, description `Skip auto-fix; leave the code as-is`

3. On `No`:
   ```
   Style: <K> non-critical finding(s) noted, no fixes applied.
   ```
   Stop with success.

4. On `Yes` → run the fix sequence below.

### Fix sequence (only after `Yes` consent)

#### Step 1 — ruff auto-fix (mechanical)

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

#### Step 2 — fan-out to `style-fixer` (parallel, per file)

Group `model_fixable[]` by `filename`, **excluding** `N801` and `N802` items (the parent handles those in Step 3). Each group becomes one subagent invocation.

**Issue ALL `Task` calls in a single message.** For G groups ≤ 10, that's G `Task` tool calls in the same response. For G > 10, split into batches of 10 across consecutive messages (Claude Code's parallel limit is 10 per message).

Each `Task` call invokes subagent `style-fixer` with this JSON payload:

```json
{
  "file": "<source path>",
  "model_fixable": [
    {"code": "<D1xx or N803/N806>", "row": <int>, "col": <int>, "message": "<ruff message>"},
    ...
  ]
}
```

Each subagent returns ONE line of JSON:

```json
{"file":"<path>","docstrings":<N>,"renames_local":<N>,"refused":[...],"errors":[...]}
```

Aggregate across all subagents:

- `docstrings_total` = sum of `docstrings`
- `renames_local_total` = sum of `renames_local`
- `agent_refused[]` = flat union of every `refused` list (these stay as advisory)
- `agent_errors[]` = flat union of every `errors` list

If `agent_errors[]` is non-empty, surface them in the final summary but do not halt — the user can re-run.

#### Step 3 — cross-file renames (`N801` / `N802`) handled by the parent

Class (`N801`) and top-level function (`N802`) renames have project-wide reach: the symbol may be imported, called, mocked, or named in a fixture from any other file. Subagents cannot see beyond their own file, so the parent owns this step.

Group `model_fixable[]` rename findings whose code is `N801` or `N802` by `(old_name, new_name)`. For each group:

1. **Locate every reference** project-wide:
   ```
   Grep pattern=\b<old_name>\b output_mode=files_with_matches
   ```
2. For each file in the result, `Read` it to confirm the matches are real references (not coincidental substrings inside an unrelated docstring or a string literal).
3. Apply the rename with `MultiEdit`:
   - If every match in the file is a real symbol reference, one entry with `old_string = <old_name>`, `new_string = <new_name>`, `replace_all = true`.
   - If some matches are spurious (e.g., a comment that mentions an unrelated thing with the same name), use multiple precise `Edit` calls with explicit context, one per real reference.
4. Track the touched files — they go into the staging set in Step 5.

If no `N801`/`N802` items exist in `model_fixable[]`, skip this step.

#### Step 4 — re-run ruff to verify

```
<runner> run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null || true
```

Re-classify the new JSON. If `len(critical) > 0` after fixes:

```
Halted: <N> finding(s) became critical after fix attempts. Manual review required.

<critical blocks with snippets>
```

Stop with non-zero exit.

Otherwise compute `remaining_advisory` = `len(advisory)` from the new run, plus any `model_fixable` items the model could not fix (e.g. a docstring it judged risky to invent — those should be carried into `remaining_advisory`).

#### Step 5 — stage modified files

Stage only files actually modified (skip untouched files to avoid grabbing unrelated user edits). The set of touched files = the original `<files>` PLUS any extra files touched by `N801`/`N802` cross-file renames:

```
for f in <touched files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

#### Final summary

```
Style: <fixed_count> auto-fixed, <remaining_advisory> advisory finding(s) remain.
```

`fixed_count` = (initial `len(safe_fixable)` + initial `len(model_fixable)`) − (count of those same codes still present in the post-fix JSON).

Stop with success.

### Hard rules

- **Halt on Critical = list with snippets, never ask.** Critical findings (`F*`, `E9*`) are real bugs; never offer to "fix" them. Always print the full list with snippets before halting.
- **Show the code, not just file:line.** Every finding renders as a 3-line context block. The user must SEE what they are about to fix.
- **Consent before edits.** For non-critical findings, `AskUserQuestion` once before any auto-fix or model edit.
- **Read before Edit.** Every model-driven `Edit`/`MultiEdit` is preceded by a `Read` on the target file so `old_string` is grounded in real text, not paraphrased.
- **Cross-file renames use Grep + MultiEdit.** Never rename a class/function in one file without checking callers project-wide first.
- **Never invent behavior in a docstring.** The summary line must be derivable from the function name and body. If the function is non-trivial and you cannot summarize it from the signature alone, prefer a conservative one-liner over a fabricated description.
- **`|| true` on ruff commands.** Ruff exits 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Stage only what you modified.** Never `git add -A`.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo. The model classifies ruff's JSON output directly.
