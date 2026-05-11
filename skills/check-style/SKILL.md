---
name: check-style
description: "Lint Python : ruff auto-fix (Pass 1) puis modèle LLM pour tout le reste — docstrings, renommages, sécurité, complexité. Fan-out parallèle. Zéro finding ignoré."
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git add:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git status:*), Bash(git rev-parse:*), Read, Edit, MultiEdit, Grep
---

# /starter:check-style

## Context

- Argument: $ARGUMENTS
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
- Changed Python files: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" 2>/dev/null`
- All Python files (only used if $ARGUMENTS == "all"): !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --all 2>/dev/null`
- Ruff version: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe ruff 2>/dev/null`

## Your task

Two-pass architecture: **ruff fixes everything it can** (cheap, fast, no LLM tokens), then the **model fixes ALL of what ruff left behind** — no advisory bucket. Never halts — everything is either fixed or refused with a reason.

- **Pass 1 — ruff** → `ruff --fix --unsafe-fixes` with all enabled codes, then `ruff format`. One shell call, ruff parallelises internally.
- **Pass 2 — re-scan** → `ruff --no-fix --output-format=json`. ALL remaining findings go to the model.
- **Per-file work** → fan-out parallèle: **one `style-fixer` subagent per impacted file, in a single message**. Each agent handles ALL codes: docstrings, renames, imports, syntax, security, complexity refactoring, and any other code.
- **Cross-file work** → done by the **parent**: `N801` (class) and `N802` (function) renames need `Grep` to find every caller, then `MultiEdit` per touched file. Subagents refuse these by design.

### Guards

1. `$ARGUMENTS` is non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `ruff: NOT INSTALLED` → output `ruff not installed. Run /starter:proj-init.` Stop.

### Resolve `<files>`

- If `$ARGUMENTS` == `all` → `<files>` = the **All Python files** list from Context (entire codebase).
- Otherwise (no argument) → `<files>` = the **Changed Python files** list from Context (diff only).

If `<files>` is empty → output `No .py files to lint.` Stop with success.

### Pass 1 — ruff fixes everything it can

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). **Append `|| true`** so ruff's exit code 1 does not surface as a scary error.

`--force-exclude` is required so `[tool.ruff].extend-exclude` (set by `proj-init`) applies even when files are passed explicitly.

```
<runner> run ruff check <files> --force-exclude --fix --unsafe-fixes --silent 2>/dev/null || true
<runner> run ruff format <files> --force-exclude 2>/dev/null || true
```

This handles F401, F541, F841, E/W/I/UP, D-fixable, B007/B009/B010/B011, and every other code ruff knows how to fix — in one shot. No pre-classification needed; ruff's `--fix --unsafe-fixes` applies every fix it has.

### Pass 2 — re-scan and classify remaining

```
<runner> run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null || true
```

The output is a JSON array. Each finding has fields `code`, `filename`, `location.row`, `location.column`, `message`, and `fix` (object or null). Everything ruff could fix is already gone. **All remaining findings go to `model_fixable[]`** — there is no advisory bucket. The model fixes everything or refuses with a reason.

Hold the list in memory. **Do not print yet.** Branch below.

### Display remaining findings — every finding gets a code snippet

**Do NOT split findings into "model auto-fix" and "advisory" sections before the fan-out.** All findings are displayed uniformly. Refused findings (if any) are surfaced only after the fan-out, in Step 5.

Render each finding as a block preceded by a separator. To get the snippet, `Read` the target file with `offset = max(1, location.row - 1)` and `limit = 3`. Format:

```
----------------------------------
  <filename>:<row>:<col> <code> — <message>
    <row-1> | <previous source line>
  > <row>   | <offending source line>
    <row+1> | <next source line>
  → <action line>
```

If the file does not have a previous/next line (top/bottom), omit that side. Plain ASCII; no colors.

The `→ <action>` line previews what the model will do:

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
| `F821` | `→ Add missing import for \`<name>\` (inferred from usage context in this file).` |
| `E999` | `→ Fix syntax error: <ruff message>. Model will read the file and repair.` |
| `S113` | `→ Add \`timeout=30\` to the requests call.` |
| `S301`/`S302` | `→ Replace pickle with \`json\` (if data is JSON-serializable).` |
| `S311` | `→ Replace \`random.<fn>\` with \`secrets.<equivalent>\`.` |
| `S324` | `→ Replace weak hash with \`sha256\` or add \`usedforsecurity=False\`.` |
| `S501`–`S503` | `→ Enable certificate verification: \`verify=True\`.` |
| `S506` | `→ Replace \`yaml.load()\` with \`yaml.safe_load()\`.` |
| `S602`/`S605`/`S607` | `→ Replace \`shell=True\` with arg list.` |
| `S608` | `→ Use parameterized query instead of f-string SQL.` |
| Other `S*` | `→ Fix security issue: <ruff message>. Model reads context and applies fix.` |
| `C901` | `→ Refactor: extract helper functions to reduce cyclomatic complexity.` |
| `C901` / `PLR0911` / `PLR0912` / `PLR0915` | `→ Refactor: simplify function to reduce branches/returns/statements.` |
| `PLR0913` | `→ Refactor: group parameters into a dataclass or TypedDict.` |
| `PLR2004` | `→ Replace magic value with a named constant.` |
| `PLW2901` | `→ Use a different variable name to avoid overwriting the loop variable.` |
| Other `PL*` / `C*` | `→ Fix: <ruff message>. Model reads context and refactors.` |
| Any other code | `→ Fix: <ruff message>. Model reads context and applies fix.` |

`<old>` (for N-codes) is extracted from the ruff `message` (it is usually quoted in backticks: ``Function name `getUser` should be lowercase``). Compute `<new>`:

- **CapWords** (`N801`): split on `_` and on lowercase→uppercase boundaries, capitalize each token, concat. `myClass` → `MyClass`, `my_class` → `MyClass`.
- **lower_snake_case** (`N802`/`N803`/`N806`): insert `_` before every uppercase letter that follows a lowercase one, lowercase everything. `getUser` → `get_user`, `MyVar` → `my_var`, `HTTPServer` → `http_server`.

`<name>` (for F821) is extracted from the ruff `message` (e.g., ``Undefined name `os``` → `os`).

### Branch 1 — No remaining findings

If `model_fixable` is empty after Pass 1:

```
Style: no findings (ruff fixed everything).
```

Stop with success.

### Branch 2 — Findings remain — fix all with model

If `len(model_fixable) > 0`:

1. Print all findings with snippets and action lines:

   ```
   Found <K> remaining finding(s) after ruff auto-fix — fixing with model:

   ----------------------------------
   <first finding: snippet + → action line>

   ----------------------------------
   <second finding: snippet + → action line>

   ...
   ```

2. **Immediately** run the fix sequence below. No `AskUserQuestion`.

### Fix sequence

#### Step 1 — fan-out to `style-fixer` (parallel, per file)

Group `model_fixable[]` by `filename`, **excluding** `N801` and `N802` items (the parent handles those in Step 2). Each group becomes one subagent invocation.

**Issue ALL `Task` calls in a single message.** For G groups ≤ 10, that's G `Task` tool calls in the same response. For G > 10, split into batches of 10 across consecutive messages (Claude Code's parallel limit is 10 per message).

Each `Task` call invokes subagent `style-fixer` with this JSON payload:

```json
{
  "file": "<source path>",
  "model_fixable": [
    {"code": "<any ruff code>", "row": <int>, "col": <int>, "message": "<ruff message>"},
    ...
  ]
}
```

Each subagent returns ONE line of JSON:

```json
{"file":"<path>","docstrings":<N>,"renames_local":<N>,"code_fixes":<N>,"refused":[...],"errors":[...]}
```

Aggregate across all subagents:

- `docstrings_total` = sum of `docstrings`
- `renames_local_total` = sum of `renames_local`
- `code_fixes_total` = sum of `code_fixes` (F821 imports added + E999 syntax fixes)
- `agent_refused[]` = flat union of every `refused` list (surfaced in final summary with reasons)
- `agent_errors[]` = flat union of every `errors` list

If `agent_errors[]` is non-empty, surface them in the final summary but do not halt — the user can re-run.

#### Step 2 — cross-file renames (`N801` / `N802`) handled by the parent

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

#### Step 3 — re-run ruff to verify

```
<runner> run ruff check <files> --force-exclude --output-format=json --no-fix 2>/dev/null || true
```

Compute `remaining` = count of findings from the new run (items the model could not fix end up in agent `refused[]`).

#### Step 4 — stage modified files

Stage only files actually modified (skip untouched files to avoid grabbing unrelated user edits). The set of touched files = the original `<files>` PLUS any extra files touched by `N801`/`N802` cross-file renames:

```
for f in <touched files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
```

#### Step 5 — handle refused findings (with user consent)

If `agent_refused[]` is non-empty after Steps 1–4:

1. For each item in `agent_refused[]`, `Read` the target file and compose a concrete proposed fix grounded in the actual source line (same quality as the action line table above).

2. Display with separators:

```
===============================================================================
  Could not auto-fix — proposed fixes (<N>):
===============================================================================

----------------------------------
  <filename>:<row>:<col> <code> — <message>
    <row-1> | <previous source line>
  > <row>   | <offending source line>
    <row+1> | <next source line>
  → Proposed fix: <concrete fix grounded in the actual code>

----------------------------------
  ...
```

3. Call `AskUserQuestion` once:
   - **header**: `Apply refused fixes`
   - **question**: `Apply fixes for these <N> issue(s) that could not be handled automatically?`
   - **multiSelect**: `false`
   - **options**:
     - label `Yes`, description `Apply all proposed fixes above`
     - label `No`, description `Skip — these will appear as remaining in the summary`

4. On `Yes`: apply each fix directly (parent, not a subagent):
   - `Read` the file to get the exact `old_string`.
   - `Edit` or `MultiEdit` the file in-place.
   - Stage: `for f in <refused files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done`
   - Count applied items as `consent_fixed`.

5. On `No`: `consent_fixed = 0`.

If `agent_refused[]` is empty, skip this step entirely (`consent_fixed = 0`).

#### Final summary

Totals:
- `auto_fixed` = items fixed by ruff (Pass 1) + style-fixer subagents + parent cross-file renames (Steps 1–4)
- `consent_fixed` = items fixed in Step 5 after user approved

If `auto_fixed + consent_fixed == initial len(model_fixable)`:
```
Style: <auto_fixed> auto-fixed, <consent_fixed> consent-fixed, 0 remaining.
```
(Omit `0 consent-fixed` segment when `consent_fixed == 0`: `Style: <auto_fixed> fixed, 0 remaining.`)

If items remain (user declined Step 5 or some fixes failed):
```
Style: <auto_fixed> auto-fixed, <consent_fixed> consent-fixed, <still_remaining> remaining.

Remaining:
  - <filename>:<row> <code> — <reason>
  ...
```

Stop with success.

### Hard rules

- **Never halt silently.** Every finding is either auto-fixed (by ruff or the model) or surfaced to the user with a concrete proposed fix and a consent prompt.
- **No advisory bucket before fan-out.** Do NOT split findings into "model auto-fix" and "advisory" sections when displaying them initially. All findings go to `style-fixer`. Refused findings appear only in Step 5, after the fan-out completes.
- **Step 5 uses one `AskUserQuestion`.** Refused findings get a consent prompt before the parent applies them directly.
- **Ruff first, model second.** Pass 1 lets ruff fix everything it can (cheap). Pass 2 uses the model only for what ruff left behind (smart). This minimises LLM token cost.
- **Show the code, not just file:line.** Every remaining finding renders as a 3-line context block. The user must SEE what the model is about to change.
- **Read before Edit.** Every model-driven `Edit`/`MultiEdit` is preceded by a `Read` on the target file so `old_string` is grounded in real text, not paraphrased.
- **Cross-file renames use Grep + MultiEdit.** Never rename a class/function in one file without checking callers project-wide first.
- **Never invent behavior in a docstring.** The summary line must be derivable from the function name and body. If the function is non-trivial and you cannot summarize it from the signature alone, prefer a conservative one-liner over a fabricated description.
- **`|| true` on ruff commands.** Ruff exits 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Stage only what you modified.** Never `git add -A`.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo.
