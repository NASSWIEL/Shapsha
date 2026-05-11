---
name: security
description: "Analyse de sécurité en deux passes : bandit (tous niveaux de sévérité) puis passe LLM-native (auth, injection, logique métier, secrets, crypto, effets de second ordre — confidence HIGH uniquement). Findings fusionnés en all_findings[], consentement unique, fan-out parallèle un sous-agent security-fixer par fichier. Tout est corrigé ou signalé."
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git rev-parse:*), Bash(git add:*), Read
---

# /starter:security

## Context

- Argument: $ARGUMENTS
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
- Changed Python files: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" 2>/dev/null`
- All Python files (only used if $ARGUMENTS == "all"): !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --all 2>/dev/null`
- Bandit version: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe bandit 2>/dev/null`
- pip-audit available: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe pip-audit 2>/dev/null`
- detect-secrets available: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe detect-secrets 2>/dev/null`

## Your task

Run bandit on the changed (or `all`) Python files **without any severity filter** — scan ALL levels. For every finding, **compose a concrete proposed fix** grounded in the actual source code. Show the full list to the user with fix proposals, ask consent once, and on `Yes` fan-out one `security-fixer` subagent per impacted file in parallel. Emit a single summary line.

### Guards

1. `$ARGUMENTS` non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `bandit: NOT INSTALLED` → output `bandit not installed. Run /starter:proj-init.` Stop.

### Resolve `<files>`

- If `$ARGUMENTS` == `all` → `<files>` = the **All Python files** list from Context (entire codebase).
- Otherwise (no argument) → `<files>` = the **Changed Python files** list from Context (diff only).

If `<files>` is empty → output `No .py files to scan.` Stop with success.

### Scan — all levels

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). Run bandit with JSON output, **no severity or confidence filter**. **Append `|| true`** so bandit's exit code 1 (which only means "findings exist") does not surface as a scary error:

```
<runner> run bandit -f json <files> 2>/dev/null || true
```

No `-ll`, no `-ii`. Every finding at every severity/confidence level is captured.

Read the JSON in memory: `{"results": [{"filename", "line_number", "test_id", "issue_text", "issue_severity", "issue_confidence", "code", ...}, ...]}`.

### Filter out B101 from test files

Remove any finding where `test_id == "B101"` AND the `filename` is under `tests/` (or matches `test_*.py` / `*_test.py`). Pytest uses `assert` by design — these are not security issues.

Call the remaining bandit results `bandit_findings[]`.

### Pass 2 — LLM security analysis (model-native)

After the bandit pass, read each file in `<files>` and reason about security issues that static analysis cannot detect. This uses the same model executing this skill — no extra tooling required.

For each file `f` in `<files>`, `Read` its full content (you will also use this read to compose bandit proposals in the next step — do both in one pass). Analyze for the 6 categories below. **Include a finding only if your confidence is HIGH (≥ 80%).** For each finding, compose a concrete proposed fix inline (same quality standard as bandit proposals).

| Category | `test_id` tag | What to look for |
|---|---|---|
| Auth/authorization | `LLM-AUTH` | Missing access checks before sensitive ops, IDOR (user A can reach user B's resource), privilege escalation via indirect call path |
| Injection paths | `LLM-INJECTION` | Untrusted input (request params, user strings, env vars, file content from disk) flowing into shell / SQL / `eval` / `exec` / template rendering / file path without sanitization — trace source-to-sink |
| Business logic | `LLM-LOGIC` | TOCTOU (`os.path.exists` then `open`), race on shared state, missing negative/zero/type validation in values that feed security decisions |
| Hardcoded secrets | `LLM-SECRET` | API keys, JWT secrets, bearer tokens, DB URLs with embedded passwords in string literals that bandit did not flag |
| Cryptography | `LLM-CRYPTO` | Hardcoded IVs or nonces, ECB mode, `random.seed(constant)` feeding a security-sensitive context |
| Second-order effects | `LLM-SECOND-ORDER` | Data written to persistent storage (DB, cache, file) that will later be deserialized, rendered, or executed without sanitization |

**Deduplication**: skip any LLM finding where a bandit finding in `bandit_findings[]` already targets the same `(filename, line_number)`.

Collect confirmed LLM findings as `llm_findings[]` (each carries its proposed fix). Then merge:

```
all_findings[] = bandit_findings[] + llm_findings[]
```

### If all_findings is empty

Continue to **auxiliary scans** below — nothing to fix.

### If all_findings is non-empty — compose and display proposals

For **every bandit finding** in `all_findings[]`, `Read` the source line (you read the file above — reuse that content) and compose a concrete proposed fix grounded in the actual code. Use the templates below as a starting point — adapt to the real symbol names. LLM findings already carry their proposed fixes from Pass 2 — do not re-derive them.

| `test_id` | Proposed fix template |
|---|---|
| `B101` | "Replace `assert <expr>` with `if not <expr>: raise <ExceptionType>(<message>)`" |
| `B102` | "Replace `exec(<code>)` with the explicit logic it represents. If the code string is static, inline it directly." |
| `B103` | "Replace `os.chmod(<path>, 0o777)` with a restrictive mode: `os.chmod(<path>, 0o755)` or `0o644`" |
| `B104` | "Bind to a specific interface instead of `0.0.0.0`: use `127.0.0.1` or the intended IP" |
| `B105`/`B106`/`B107` | "Move the literal credential to an environment variable: `os.environ['<NAME>']`" |
| `B108` | "Replace `/tmp` with `tempfile.mkdtemp()` or `tempfile.NamedTemporaryFile()`" |
| `B110` | "Replace bare `except: pass` with explicit exception handling: `except <SpecificError>: pass` or log the error" |
| `B112` | "Replace bare `except: continue` with `except <SpecificError>: continue`" |
| `B201` | "Disable Flask debug mode in production: `app.run(debug=False)`" |
| `B301`/`B302`/`B306` | "Replace pickle/marshal with `json.loads()`/`json.dumps()` for untrusted input" |
| `B303` | "Replace weak hash (`md5`/`sha1`) with `hashlib.sha256()`. If non-security use, pass `usedforsecurity=False`" |
| `B311` | "Replace `random.<fn>` with `secrets.<equivalent>` for security-sensitive context" |
| `B312` | "Replace `telnetlib` with `paramiko` (SSH) or another encrypted protocol" |
| `B320`/`B321`/`B322` | "Replace `xml.etree` with `defusedxml` to prevent XXE attacks" |
| `B324` | "Replace weak hash (`md5`/`sha1`) with `hashlib.sha256()`. If non-security use, pass `usedforsecurity=False`" |
| `B501`/`B502`/`B503` | "Enable certificate verification: pass `verify=True` (or omit the parameter)" |
| `B504` | "Use `ssl.create_default_context()` instead of manually creating an SSL context" |
| `B506` | "Replace `yaml.load()` with `yaml.safe_load()`" |
| `B507` | "Add `host_key_policy` verification — avoid `AutoAddPolicy` in production" |
| `B601` | "Replace `shell=True` in paramiko with explicit command list" |
| `B602`/`B605`/`B607` | "Replace `shell=True` with an arg list: `subprocess.run([\"cmd\", \"arg\"])`" |
| `B608` | "Use a parameterized query: `cursor.execute(sql, params)` — replace f-string/`%` formatting of SQL" |
| `B609` | "Replace wildcard in `subprocess.call` with explicit file listing via `glob.glob()`" |
| `B610`/`B611` | "Replace Django `extra()`/`RawSQL()` with ORM query methods" |
| `B701` | "Replace Jinja2 `autoescape=False` with `autoescape=True`" |
| `B702` | "Replace Mako template with Jinja2 (which has autoescape), or sanitize all inputs" |
| Other / unknown | "LLM analysis: <read the actual code around the finding and compose a context-specific fix proposal>" |

**Important**: for `Other / unknown`, do NOT fall back to "Manual review required." Read the surrounding code and compose a real proposed fix based on what the code does. Only if you truly cannot determine a safe fix after reading the context, use: "Context-dependent: <explain what the code does and what change is needed>."

### Display findings with proposals

Print the consolidated block covering all findings in `all_findings[]`:

```
Found <N> security finding(s) (<B> from bandit, <L> from LLM analysis):

  1. [<severity>/<confidence>] <filename>:<line_number> <test_id> — <issue_text>
     → Proposed fix: <fix proposal grounded in the actual code at this line>

  2. [<severity>/<confidence>] <filename>:<line_number> <test_id> — <issue_text>
     → Proposed fix: <...>

  ...
```

Bandit findings show B-codes (`B324`, `B608`, …). LLM findings show descriptive tags (`LLM-INJECTION`, `LLM-AUTH`, …). Group findings by file for readability. Within each file, sort by line number.

### Ask consent once

Call `AskUserQuestion` once with:

- **header**: `Security fixes`
- **question**: `Do you want me to fix all <N> issue(s)? (<B> from bandit, <L> from LLM analysis)`
- **multiSelect**: `false`
- **options**:
  - label `Yes`, description `Apply all proposed fixes above`
  - label `No`, description `Skip fixing — findings remain as advisory`

### On `No`

```
Security: <N> finding(s) reported, none fixed (user declined). Review the proposals above.
```

Stop with success (not an error — the user made a choice). Skip auxiliary scans.

### On `Yes` — fan-out to `security-fixer` (parallel, per file)

Group all findings in `all_findings[]` by `filename`. Each group becomes one subagent invocation.

**Issue ALL `Task` calls in a single message.** For G groups ≤ 10, that's G `Task` tool calls in the same response. For G > 10, split into batches of 10 across consecutive messages (Claude Code's parallel limit is 10 per message).

Each `Task` call invokes subagent `security-fixer` with this JSON payload:

```json
{
  "file": "<source path>",
  "findings": [
    {"test_id": "<B-code or LLM-tag>", "line": <int>, "issue": "<issue text>", "severity": "<LOW|MEDIUM|HIGH>", "confidence": "<LOW|MEDIUM|HIGH>", "proposed": "<the proposed fix you composed for this finding>"},
    ...
  ]
}
```

`proposed` is the same fix text already shown to the user — pass it verbatim so the subagent applies what was approved. Bandit findings carry B-codes (`B324`, …); LLM findings carry descriptive tags (`LLM-INJECTION`, …). The subagent treats both identically.

Each subagent returns ONE line of JSON:

```json
{"file":"<path>","applied":<N>,"refused":[{"test_id":"B102","line":17,"reason":"<why>"}],"errors":[]}
```

Aggregate across all subagents:

- `applied_total` = sum of `applied`
- `refused_total[]` = flat union of every `refused` list
- `errors_total[]` = flat union of every `errors` list

### After fan-out

1. Stage modified files:
   ```
   for f in <modified files>; do git diff --quiet -- "$f" 2>/dev/null || git add -- "$f"; done
   ```
2. Re-run bandit on the same files to verify:
   ```
   <runner> run bandit -f json <files> 2>/dev/null || true
   ```
3. Count remaining findings from the re-run.

### Auxiliary scans (opportunistic, advisory only)

Run **only when the corresponding tool is installed** (per Context lines above; if a probe returned `... NOT INSTALLED`, skip that scan). Each is advisory.

**pip-audit** — dependency CVEs:

```
<runner> run pip-audit --strict --progress-spinner=off 2>/dev/null || true
```

Count the non-empty data rows (skip the header line and blank lines). Call this `deps_vulns`. If pip-audit was not installed, set `deps_vulns = "n/a"`.

**detect-secrets** — hardcoded credentials in changed files:

```
<runner> run detect-secrets scan --baseline /dev/null <files> 2>/dev/null || true
```

JSON output: `{"results": {"<file>": [<finding>, ...], ...}}`. Sum the lengths of all per-file lists to get `secrets_found`. If detect-secrets was not installed, set `secrets_found = "n/a"`.

### Final summary

```
Security: <applied_total> fixed, <refused_count> could not be auto-fixed, <remaining> remaining after verification, <deps_vulns> dependency vuln(s), <secrets_found> potential secret(s).
```

If `refused_total[]` is non-empty, list them:

```
Could not auto-fix (<refused_count>):
  - <filename>:<line> <test_id> — <reason>
  ...
```

Omit a segment whose tool is `n/a`. Stop with success.

### Hard rules

- **Two passes, one consent.** Pass 1 = bandit (all severity levels). Pass 2 = LLM analysis (6 categories, HIGH confidence only, deduplicated vs bandit). Merged into `all_findings[]` before the single consent prompt.
- **LLM pass is HIGH-confidence only.** Do not include LLM findings below HIGH confidence — this keeps the signal-to-noise ratio acceptable. If unsure, omit.
- **List everything, propose everything.** Every finding in `all_findings[]` — bandit and LLM alike — gets a concrete fix proposal. No "advisory only" bucket with no fix.
- **Consent once, then fan-out.** One `AskUserQuestion` for the whole batch. On `Yes`, fan-out one `security-fixer` per file. On `No`, report and stop.
- **Fix proposal must be concrete.** Read the actual line; tailor the proposal to the real symbol names. For unknown codes, read surrounding context and compose a real fix — generic "manual review" is a last resort.
- **Parent does not edit.** Edits happen inside `security-fixer` subagents only. The parent reads files (to compose proposals) and invokes `Task`.
- **All `Task` calls in one message for parallelism.** ≤ 10 per batch.
- **`|| true` on every scanner.** Bandit/pip-audit/detect-secrets exit 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Stage only what you modified.** Never `git add -A`.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo.
