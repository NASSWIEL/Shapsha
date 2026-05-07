---
name: security
description: Analyse de sécurité bandit sur les fichiers Python modifiés. Affiche les findings >= MEDIUM. S'arrête uniquement sur HIGH/HIGH ; MEDIUM est consultatif.
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git rev-parse:*)
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

Run bandit on the changed (or `all`) Python files, classify findings, and emit a single summary line. Surface HIGH-severity HIGH-confidence findings as halts; everything below is advisory.

### Guards

1. `$ARGUMENTS` non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `bandit: NOT INSTALLED` → output `bandit not installed. Run /bt-ai:proj-init.` Stop.
3. Target list (resolved per `$ARGUMENTS`) is empty → output `No .py files to scan.` Stop with success.

### Scan and classify

Replace `<runner>` below with the literal Runner value from the Context above (`uv` or `poetry`). Run bandit with JSON output:

```
<runner> run bandit -f json -ll -ii <files> 2>/dev/null
```

`-ll` filters severity to >= MEDIUM, `-ii` confidence to >= MEDIUM.

The output is JSON: `{"results": [{"filename", "line_number", "test_id", "issue_text", "issue_severity", "issue_confidence", ...}, ...], ...}`. Read it and classify each result, printing one line per finding:

- `issue_severity == "HIGH"` AND `issue_confidence == "HIGH"` → **BLOCKED**. Print: `[HIGH/HIGH] [BLOCKED] <filename>:<line_number> <test_id> <issue_text>`. Increments `blocked_count`.
- Anything else (MEDIUM/MEDIUM, MEDIUM/HIGH, HIGH/MEDIUM) → **ADVISORY**. Print: `[<severity>/<confidence>] [ADVISORY] <filename>:<line_number> <test_id> <issue_text>`. Increments `advisory_count`.

### Halt criterion

The halt rule is narrow on purpose: bandit auto-fix is dangerous (suppressing warnings silently), so this skill is **report-only** with one halt level.

- `blocked_count > 0` → output:
  ```
  Halted: <blocked_count> HIGH/HIGH security finding(s) require manual review.
  ```
  Stop with non-zero exit. **Skip the auxiliary scans on halt.**

- `blocked_count == 0` → continue to auxiliary scans below.

### Auxiliary scans (opportunistic, advisory only)

Run **only when the corresponding tool is installed** (per Context lines above; if a probe returned `... NOT INSTALLED`, skip that scan). Each is advisory: it never halts the suite, only adds counts to the summary.

**pip-audit** — dependency CVEs:

```
<runner> run pip-audit --strict --progress-spinner=off 2>/dev/null
```

The output is a table with a header row, then one row per vulnerable package. Count the non-empty data rows (skip the header line and any blank lines). Call this `deps_vulns`. If pip-audit was not installed, set `deps_vulns = "n/a"`.

**detect-secrets** — hardcoded credentials in changed files:

```
<runner> run detect-secrets scan --baseline /dev/null <files> 2>/dev/null
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

- **No auto-fix.** Mechanically silencing a security warning is dangerous. This skill never edits user code.
- **No AskUserQuestion.** Halt or pass; the user does not need a prompt to read a printed list.
- **Hermetic.** Never write classifier scripts or scratch files into the user's repo. The model classifies bandit's JSON output directly.
- **Single message.** Do classify + summary in one tool-call turn. Do not narrate.
