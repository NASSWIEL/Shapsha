---
name: security
description: "Analyse de sécurité bandit sur les fichiers Python modifiés. Scanne tous les niveaux de sévérité, propose un fix concret pour chaque finding, demande consentement une fois, puis corrige tout via fan-out parallèle (un sous-agent security-fixer par fichier). Tout est corrigé ou signalé."
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

Run bandit on the changed (or `all`) Python files **without any severity filter** — scan ALL levels. For every finding, **compose a concrete proposed fix** grounded in the actual source code. Show the full list to the user with fix proposals, ask consent once, and on `Yes` fan-out one `security-fixer` subagent per impacted file in parallel. Emit a single summary line.

### Guards

1. `$ARGUMENTS` non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `bandit: NOT INSTALLED` → output `bandit not installed. Run /bt-ai:proj-init.` Stop.
3. Target list (resolved per `$ARGUMENTS`) is empty → output `No .py files to scan.` Stop with success.

### Scan — all levels

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). Run bandit with JSON output, **no severity or confidence filter**. **Append `|| true`** so bandit's exit code 1 (which only means "findings exist") does not surface as a scary error:

```
<runner> run bandit -f json <files> 2>/dev/null || true
```

No `-ll`, no `-ii`. Every finding at every severity/confidence level is captured.

Read the JSON in memory: `{"results": [{"filename", "line_number", "test_id", "issue_text", "issue_severity", "issue_confidence", "code", ...}, ...]}`.

### If no findings

Continue to **auxiliary scans** below — nothing to fix.

### If findings exist — compose fix proposals

For **every** finding, `Read` the source line and compose a concrete proposed fix grounded in the actual code. Use the templates below as a starting point — adapt to the real symbol names.

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

Print the consolidated block:

```
Found <N> security finding(s) across all severity levels:

  1. [<severity>/<confidence>] <filename>:<line_number> <test_id> — <issue_text>
     → Proposed fix: <fix proposal grounded in the actual code at this line>

  2. [<severity>/<confidence>] <filename>:<line_number> <test_id> — <issue_text>
     → Proposed fix: <...>

  ...
```

Group findings by file for readability. Within each file, sort by line number.

### Ask consent once

Call `AskUserQuestion` once with:

- **header**: `Security fixes`
- **question**: `Do you want me to fix all <N> issue(s)?`
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

Group all findings by `filename`. Each group becomes one subagent invocation.

**Issue ALL `Task` calls in a single message.** For G groups ≤ 10, that's G `Task` tool calls in the same response. For G > 10, split into batches of 10 across consecutive messages (Claude Code's parallel limit is 10 per message).

Each `Task` call invokes subagent `security-fixer` with this JSON payload:

```json
{
  "file": "<source path>",
  "findings": [
    {"test_id": "<B-code>", "line": <int>, "issue": "<bandit issue_text>", "severity": "<LOW|MEDIUM|HIGH>", "confidence": "<LOW|MEDIUM|HIGH>", "proposed": "<the proposed fix you composed for this finding>"},
    ...
  ]
}
```

`proposed` is the same fix text already shown to the user — pass it verbatim so the subagent applies what was approved.

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

- **List everything, propose everything.** Every bandit finding at every severity gets a concrete fix proposal — no "advisory only" bucket with no fix.
- **Consent once, then fan-out.** One `AskUserQuestion` for the whole batch. On `Yes`, fan-out one `security-fixer` per file. On `No`, report and stop.
- **Fix proposal must be concrete.** Read the actual line; tailor the proposal to the real symbol names. For unknown codes, read surrounding context and compose a real fix — generic "manual review" is a last resort.
- **Parent does not edit.** Edits happen inside `security-fixer` subagents only. The parent reads files (to compose proposals) and invokes `Task`.
- **All `Task` calls in one message for parallelism.** ≤ 10 per batch.
- **`|| true` on every scanner.** Bandit/pip-audit/detect-secrets exit 1 when findings exist; the user must not see "Exit code 1" framed as an error.
- **Stage only what you modified.** Never `git add -A`.
- **Hermetic.** Never write classifier scripts, scratch JSON, or log files into the user's repo.
