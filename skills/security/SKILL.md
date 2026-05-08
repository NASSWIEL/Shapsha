---
name: security
description: "Analyse de sécurité bandit sur les fichiers Python modifiés. Liste tous les findings HIGH/HIGH avec une proposition de correction. Demande consentement une fois pour tout corriger via fan-out parallèle (un sous-agent security-fixer par fichier, en simultané). MEDIUM reste consultatif."
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git rev-parse:*), Bash(git add:*), Read
---

# /bt-ai:security

## Context

- Argument: $ARGUMENTS
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
- Changed Python files: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" 2>/dev/null`
- All Python files (only used if $ARGUMENTS == "all"): !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --all 2>/dev/null`
- Bandit version: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe bandit 2>/dev/null`
- pip-audit available: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe pip-audit 2>/dev/null`
- detect-secrets available: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe detect-secrets 2>/dev/null`

## Your task

Run bandit on the changed (or `all`) Python files, classify findings, **list every HIGH/HIGH finding with a concrete proposed fix**, ask the user once whether to apply all fixes, and emit a single summary line. MEDIUM is advisory — no question, no fix.

On `Yes`, the parent does **not** edit files itself: it groups blocked findings by `filename` and **fans out one `security-fixer` subagent per file in parallel** (single message, up to 10 `Task` calls per batch). Each subagent reads its own file, applies the proposed fixes, and returns one line of JSON. The parent aggregates the results and re-runs bandit to verify.

### Guards

1. `$ARGUMENTS` non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `bandit: NOT INSTALLED` → output `bandit not installed. Run /bt-ai:proj-init.` Stop.
3. Target list (resolved per `$ARGUMENTS`) is empty → output `No .py files to scan.` Stop with success.

### Scan and classify

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). Run bandit with JSON output. **Append `|| true`** so bandit's exit code 1 (which only means "findings exist") does not surface as a scary error in the user's terminal:

```
<runner> run bandit -f json -ll -ii <files> 2>/dev/null || true
```

`-ll` filters severity to >= MEDIUM, `-ii` confidence to >= MEDIUM.

Read the JSON in memory: `{"results": [{"filename", "line_number", "test_id", "issue_text", "issue_severity", "issue_confidence", "code", ...}, ...]}`. Classify each result into two buckets — do **not** print per-finding lines yet:

| Bucket | Detection | Path |
|---|---|---|
| **`blocked[]`** | `issue_severity == "HIGH"` AND `issue_confidence == "HIGH"` | Must propose fix + ask consent. |
| **`advisory[]`** | Anything else (MEDIUM/MEDIUM, MEDIUM/HIGH, HIGH/MEDIUM) | Reported in final summary; no fix proposal. |

### Branch on Blocked

#### If `len(blocked) == 0`

Continue to **auxiliary scans** below — no question to ask.

#### If `len(blocked) > 0`

For each finding in `blocked[]`, **read the source line** (`Read` the file, look at `line_number`) and compose a concrete proposed fix grounded in the actual code, using the templates below as a starting point. Adapt to the real symbol names — never invent code that is not consistent with the file.

| `test_id` | Proposed fix template |
|---|---|
| `B101` | "Replace `assert <expr>` with `if not <expr>: raise <ExceptionType>(<message>)`" |
| `B102` | "Avoid `exec()` — replace with the explicit logic it represents" |
| `B105`/`B106`/`B107` | "Move the literal credential to an environment variable: `os.environ['<NAME>']` (and document the variable in README)" |
| `B201` | "Disable Flask debug mode in production: `app.run(debug=False)` or remove the call" |
| `B301`/`B302`/`B306` | "Replace pickle/marshal with `json` for untrusted input, or restrict source" |
| `B311` | "Replace `random.<fn>` with `secrets.<equivalent>` for cryptographic context" |
| `B324` | "Replace weak hash (md5/sha1) with `hashlib.sha256`. If used for non-security purposes, pass `usedforsecurity=False`." |
| `B501`/`B502`/`B503` | "Enable certificate verification: pass `verify=True` (or omit the parameter)" |
| `B602`/`B605`/`B607` | "Replace `shell=True` with an arg list: `subprocess.run([\"cmd\", \"arg\"], shell=False)`" |
| `B608` | "Use a parameterized query: `cursor.execute(sql, params)` — drop f-string/`%` formatting of SQL" |
| Other / unknown | "Manual review required: <bandit's `issue_text` verbatim>" |

Print the consolidated proposal block, exactly:

```
Found <N> security issue(s) with HIGH severity and HIGH confidence:

  1. <filename>:<line_number> <test_id> — <issue_text>
     → Proposed fix: <fix proposal grounded in the actual code at this line>

  2. <filename>:<line_number> <test_id> — <issue_text>
     → Proposed fix: <...>

  ...
```

Then call `AskUserQuestion` once with:

- **header**: `Security fixes`
- **question**: `Do you want me to fix all these issues?`
- **multiSelect**: `false`
- **options**:
  - label `Yes`, description `Apply all proposed fixes above`
  - label `No`, description `Halt without modifying any file`

#### On `No`

```
Halted: <N> HIGH/HIGH security finding(s) require manual review.
```

Stop with non-zero exit. Skip auxiliary scans.

#### On `Yes` — fan-out to `security-fixer` (parallel, per file)

Group `blocked[]` by `filename`. Each group becomes one subagent invocation.

**Issue ALL `Task` calls in a single message.** For G groups ≤ 10, that's G `Task` tool calls in the same response. For G > 10, split into batches of 10 across consecutive messages (Claude Code's parallel limit is 10 per message).

Each `Task` call invokes subagent `security-fixer` with this JSON payload:

```json
{
  "file": "<source path>",
  "findings": [
    {"test_id": "<B-code>", "line": <int>, "issue": "<bandit issue_text>", "proposed": "<the proposed fix you composed for this finding>"},
    ...
  ]
}
```

`proposed` is the same fix text already shown to the user above — pass it verbatim so the subagent applies what was approved.

Each subagent returns ONE line of JSON:

```json
{"file":"<path>","applied":<N>,"refused":[{"test_id":"B102","line":17,"reason":"manual-review-required"}],"errors":[]}
```

Aggregate across all subagents:

- `applied_total` = sum of `applied`
- `agent_refused[]` = flat union of every `refused` list (these stay as advisory)
- `agent_errors[]` = flat union of every `errors` list

If `agent_errors[]` is non-empty, surface them in the final summary but do not halt — the user can re-run.

#### After fan-out

1. Stage modified files. The set of touched files = the keys of the groups above:
   ```
   for f in <modified files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
   ```
2. Re-run bandit on the same files to verify:
   ```
   <runner> run bandit -f json -ll -ii <files> 2>/dev/null || true
   ```
3. Re-classify. If `len(blocked) > 0` after re-run, output:
   ```
   Halted: <N> HIGH/HIGH security finding(s) remain after fix attempts. Manual review required.
   ```
   List the remaining `blocked[]` items the same way as above (include any `agent_refused[]` entries — they explain why some items were not fixed). Stop with non-zero exit.
4. Else continue to auxiliary scans.

### Auxiliary scans (opportunistic, advisory only)

Run **only when the corresponding tool is installed** (per Context lines above; if a probe returned `... NOT INSTALLED`, skip that scan). Each is advisory: it never halts the suite.

**pip-audit** — dependency CVEs:

```
<runner> run pip-audit --strict --progress-spinner=off 2>/dev/null || true
```

The output is a table with a header row, then one row per vulnerable package. Count the non-empty data rows (skip the header line and any blank lines). Call this `deps_vulns`. If pip-audit was not installed, set `deps_vulns = "n/a"`.

**detect-secrets** — hardcoded credentials in changed files:

```
<runner> run detect-secrets scan --baseline /dev/null <files> 2>/dev/null || true
```

The output is JSON: `{"results": {"<file>": [<finding>, ...], ...}, ...}`. Sum the lengths of all per-file lists in `results` to get `secrets_found`. If detect-secrets was not installed, set `secrets_found = "n/a"`.

### Final summary

```
Security: <advisory_count> advisory bandit finding(s), <deps_vulns> dependency vuln(s), <secrets_found> potential secret(s). No HIGH/HIGH blocks.
```

Omit a segment whose tool is `n/a`. If both auxiliary tools are missing, the line collapses to:

```
Security: <advisory_count> advisory bandit finding(s). No HIGH/HIGH blocks.
```

Stop with success.

### Hard rules

- **Propose, list, ask once, then fan out.** Never invoke a subagent before the user says `Yes` to `AskUserQuestion`. Never split the consent question per finding — one question for the whole batch.
- **Fix proposal must be concrete.** Read the actual line; tailor the proposal to the real symbol names. Generic "review this" is only acceptable for `Other / unknown` cases. The proposal text gets passed verbatim to the subagent.
- **Parent does not edit.** Edits happen inside `security-fixer` subagents only. The parent reads files (to compose proposals) and invokes `Task` — that is all.
- **All `Task` calls in one message for parallelism.** ≤ 10 per batch. The parallel limit is enforced by Claude Code; sequential issuance defeats the speedup.
- **`|| true` on every scanner.** Bandit/pip-audit/detect-secrets exit 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Stage only what you modified.** Never `git add -A`.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo. The model classifies bandit's JSON output directly.
