---
name: check-style
description: "Lint des fichiers Python modifiés avec ruff. Deux passes : ruff corrige tout ce qu'il peut (--fix --unsafe-fixes), puis le modèle corrige le reste (docstrings D1xx, renommages N8xx, noms indéfinis F821, erreurs de syntaxe E999) en fan-out parallèle. Ne s'arrête jamais — tout est corrigé ou signalé."
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

Two-pass architecture: **ruff fixes everything it can** (cheap, fast, no LLM tokens), then the **model fixes what ruff left behind** (docstrings, renames, undefined names, syntax errors). Never halts — everything is either fixed or reported as advisory.

- **Pass 1 — ruff** → `ruff --fix --unsafe-fixes` with all enabled codes, then `ruff format`. One shell call, ruff parallelises internally.
- **Pass 2 — re-scan** → `ruff --no-fix --output-format=json`. Classify remaining findings into `model_fixable[]` (LLM can fix) or `advisory[]` (report only).
- **`model_fixable[]` per-file work** → fan-out parallèle: **one `style-fixer` subagent per impacted file, in a single message**. Each agent handles `D1xx` docstrings, `N803`/`N806` renames, `F821` undefined names, and `E999` syntax errors inside its own file.
- **`model_fixable[]` cross-file work** → done by the **parent**: `N801` (class) and `N802` (function) renames need `Grep` to find every caller, then `MultiEdit` per touched file. Subagents refuse these by design.

### Guards

1. `$ARGUMENTS` is non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `ruff: NOT INSTALLED` → output `ruff not installed. Run /bt-ai:proj-init.` Stop.

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

The output is a JSON array. Each finding has fields `code`, `filename`, `location.row`, `location.column`, `message`, and `fix` (object or null). Everything ruff could fix is already gone. Classify what remains into **two** buckets:

| Bucket | Codes | Routing |
|---|---|---|
| **`model_fixable[]`** | `D100`–`D107` with null `fix` (missing docstring — ruff cannot generate text), **plus** `N801`/`N802`/`N803`/`N806` (renames), **plus** `F821` (undefined name — model adds the missing import or fixes the reference), **plus** `E999` (syntax error — model reads the raw file and fixes the syntax) | Model edits via fan-out `style-fixer` (per-file) and parent (cross-file renames). |
| **`advisory[]`** | Everything else: `B*`, `S*`, `C90*`, `PL*`, other `F*`/`E*` with null `fix` not listed above, and any `N*` outside the rename whitelist | Reported only — no automatic fix path. |

Hold the buckets in memory. **Do not print yet.** Branch below.

### Display remaining findings — every finding gets a code snippet

For every remaining finding (in any bucket), render a 3-line block. To get the snippet, `Read` the target file with `offset = max(1, location.row - 1)` and `limit = 3`. Format:

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
| `F821` | `→ Add missing import for \`<name>\` (inferred from usage context in this file).` |
| `E999` | `→ Fix syntax error: <ruff message>. Model will read the file and repair.` |

`<old>` (for N-codes) is extracted from the ruff `message` (it is usually quoted in backticks: ``Function name `getUser` should be lowercase``). Compute `<new>`:

- **CapWords** (`N801`): split on `_` and on lowercase→uppercase boundaries, capitalize each token, concat. `myClass` → `MyClass`, `my_class` → `MyClass`.
- **lower_snake_case** (`N802`/`N803`/`N806`): insert `_` before every uppercase letter that follows a lowercase one, lowercase everything. `getUser` → `get_user`, `MyVar` → `my_var`, `HTTPServer` → `http_server`.

`<name>` (for F821) is extracted from the ruff `message` (e.g., ``Undefined name `os``` → `os`).

### Branch 1 — No remaining findings

If both buckets are empty after Pass 1:

```
Style: no findings (ruff fixed everything).
```

Stop with success.

### Branch 2 — Only advisory remaining

If `len(model_fixable) == 0` AND `len(advisory) > 0`:

Print the advisory list with snippets, then stop with success:

```
Style: <N> advisory finding(s) noted (no automatic fix available):

<advisory blocks with snippets>
```

### Branch 3 — Model-fixable findings present (with optional advisory)

If `len(model_fixable) > 0`:

1. Print every remaining finding grouped by bucket, with snippets:

   ```
   Found <K> remaining finding(s) after ruff auto-fix — fixing with model:

   --- model auto-fix (<count_model>) ---
   <model_fixable blocks with snippets, each followed by its → action line>

   --- advisory only, no automatic fix (<count_advisory>) ---
   <advisory blocks with snippets>
   ```

   Omit a `---` section when its count is 0.

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
    {"code": "<D1xx or N803/N806 or F821 or E999>", "row": <int>, "col": <int>, "message": "<ruff message>"},
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
- `agent_refused[]` = flat union of every `refused` list (these stay as advisory)
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

Compute `remaining_advisory` = count of findings from the new run, plus any `model_fixable` items the model could not fix (agent `refused[]` items).

#### Step 4 — stage modified files

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

- **Never halt.** Every finding is either auto-fixed (by ruff or the model) or reported as advisory. No `critical[]` bucket, no halting, no `AskUserQuestion`.
- **Ruff first, model second.** Pass 1 lets ruff fix everything it can (cheap). Pass 2 uses the model only for what ruff left behind (smart). This minimises LLM token cost.
- **Show the code, not just file:line.** Every remaining finding renders as a 3-line context block. The user must SEE what the model is about to change.
- **Read before Edit.** Every model-driven `Edit`/`MultiEdit` is preceded by a `Read` on the target file so `old_string` is grounded in real text, not paraphrased.
- **Cross-file renames use Grep + MultiEdit.** Never rename a class/function in one file without checking callers project-wide first.
- **Never invent behavior in a docstring.** The summary line must be derivable from the function name and body. If the function is non-trivial and you cannot summarize it from the signature alone, prefer a conservative one-liner over a fabricated description.
- **`|| true` on ruff commands.** Ruff exits 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Stage only what you modified.** Never `git add -A`.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo. The model classifies ruff's JSON output directly.
