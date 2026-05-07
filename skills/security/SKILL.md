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
- Bandit version: !`R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv); $R run bandit --version 2>&1 | head -1 || echo "bandit: NOT INSTALLED"`

## Your task

Run bandit on the changed (or `all`) Python files, classify findings, and emit a single summary line. Surface HIGH-severity HIGH-confidence findings as halts; everything below is advisory.

### Guards

1. `$ARGUMENTS` non-empty AND not exactly `all` → output `Unknown argument: <token>. Accepts no argument or 'all'.` Stop.
2. `bandit: NOT INSTALLED` → output `bandit not installed. Run /bt-ai:proj-init.` Stop.
3. Target list (resolved per `$ARGUMENTS`) is empty → output `No .py files to scan.` Stop with success.

### Scan and classify

Pipe bandit JSON straight into the bundled classifier:

```
R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run bandit -f json -ll -ii <files> 2>/dev/null | python "${CLAUDE_PLUGIN_ROOT}/tools/classify_bandit.py"
```

`-ll` filters severity to >= MEDIUM, `-ii` confidence to >= MEDIUM. The classifier prints:

```
summary blocked=N fixable=N total=N
[<sev>/<conf>] [BLOCKED|FIXABLE] <path>:<line> <code> <message>
```

### Halt criterion

The Halt rule is narrow on purpose: bandit auto-fix is dangerous (suppressing warnings silently), so this skill is **report-only** with one halt level.

- **Halt** when ANY finding is `HIGH` severity AND `HIGH` confidence. These are bandit's strongest signals — exec, eval, pickle on untrusted data, hardcoded crypto keys, shell injection.
- **Advisory** for MEDIUM/MEDIUM, MEDIUM/HIGH, HIGH/MEDIUM. The classifier already printed them. They do not halt the suite; the user reads them and acts in a follow-up commit if needed.

To detect HIGH/HIGH, re-pipe bandit with stricter flags:

```
R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run bandit -f json -lll -iii <files> 2>/dev/null | python -c "import sys,json; raw=sys.stdin.read(); print(len(json.loads(raw or '{}').get('results',[])) if raw.strip() else 0)"
```

If the count is `0` → output:
```
Security: <total> advisory finding(s). No HIGH/HIGH blocks.
```
Stop with success.

If the count is `> 0` → output:
```
Halted: <count> HIGH/HIGH security finding(s) require manual review.
```
Stop with non-zero exit.

### Hard rules

- **No auto-fix.** Mechanically silencing a security warning is dangerous. This skill never edits user code.
- **No AskUserQuestion.** Halt or pass; the user does not need a prompt to read a printed list.
- **Hermetic.** No scratch files in the user's repo.
- **Single message.** Do classify + summary in one tool-call turn. Do not narrate.
