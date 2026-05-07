---
name: gen-tests
description: Génère des tests pytest pour les fichiers Python modifiés (ou une cible explicite). Reflète l'arborescence sous tests/. Vérifie et auto-répare les échecs mécaniques. S'arrête sur les échecs sémantiques.
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(git add:*), Bash(git diff:*), Bash(git ls-files:*), Bash(printf:*), Read, Glob
---

# /bt-ai:gen-tests

Three modes (decided from `$ARGUMENTS`):

| Argument | Mode | Targets |
|---|---|---|
| (none) | Diff mode | `*.py` changed in working tree (staged + unstaged + untracked), excluding `tests/**` |
| One or more paths | Targeted | Each path; directories expanded to `**/*.py` |
| `all` | Full sweep | Every tracked `*.py`, excluding `tests/**`. Slow; surfaces pre-existing untested code |

## Context

- Argument: $ARGUMENTS
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
- Changed Python files: !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --no-tests 2>/dev/null`
- All Python files (only used if $ARGUMENTS == "all"): !`python "${CLAUDE_PLUGIN_ROOT}/tools/list_changed.py" --all --no-tests 2>/dev/null`
- Pytest version: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" --probe pytest 2>/dev/null`

## Your task

Generate the missing pytest tests for the resolved targets, verify they collect+pass, auto-repair mechanical failures, and emit one summary line. Halt only when semantic failures (real assertion mismatches) remain — those need the human's judgment, not another retry.

### Guards

1. `pytest: NOT INSTALLED` → output `pytest not installed. Run /bt-ai:proj-init.` Stop.
2. Resolve target list:
   - `$ARGUMENTS` empty → use `Changed Python files`. If empty → output `No target files.` Stop with success.
   - `$ARGUMENTS == "all"` → use `All Python files`. If empty → output `No tracked .py files.` Stop with success.
   - Otherwise → split tokens; for each token, if it's a directory, glob `**/*.py` excluding `tests/**`; if a file, take it directly; if missing, output `Target not found: <token>.` Stop. Reject any token under `tests/`: output `Target must not be under tests/.` Stop.

### Discover targets

Targeted mode passes `--no-skip-filter` (when the user explicitly named files, respect that intent and skip the FastAPI/Streamlit/CLI heuristics). Diff and `all` modes keep the filter on.

```
# diff mode / all mode: filter on
printf '%s\n' <files> | python "${CLAUDE_PLUGIN_ROOT}/tools/discover_test_targets.py"

# targeted mode: filter off
printf '%s\n' <files> | python "${CLAUDE_PLUGIN_ROOT}/tools/discover_test_targets.py" --no-skip-filter
```

The tool returns JSON with `targets`, `skipped`, `package_name`, `import_root`. Skip reasons: `fastapi-handler`, `streamlit-page`, `cli-entrypoint`, `model-only`, `no-public-symbols`, `all-tested`.

Path mirror is deterministic:

| Source | Test path |
|---|---|
| `src/foo/bar.py` | `tests/foo/test_bar.py` |
| `foo/bar.py` (no `src/`) | `tests/foo/test_bar.py` |
| `pkg.py` (root) | `tests/test_pkg.py` |

If `targets` is empty → output `All target files already have tests (or were skipped). N skipped: <reason summary>.` Stop with success.

### Delegate to test-writer

Invoke `Task` with subagent `test-writer`. Pass the discovery JSON unchanged (it expects `targets`, `package_name`, `import_root`).

Wait for the agent's structured line: `files=<list> tests_added=<n> collection_ok=<true|false>`.

If `collection_ok=false` → output `Halted: test collection failed.` followed by the agent's verbatim error. Stop.

Stage the new/modified test files:
```
for f in <files from agent return>; do git add -- "$f"; done
```

### Verify

Run pytest on the freshly written test paths and pipe through the bundled failure parser:

```
R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run pytest -q --no-header --tb=short <new test paths> 2>&1 | python "${CLAUDE_PLUGIN_ROOT}/tools/parse_pytest_failures.py"
```

The parser returns JSON with `passed`, `failed`, `errors`, `mechanical[]`, `semantic[]`.

- **MECHANICAL** (auto-fixable): `ModuleNotFoundError`, `ImportError`, `NameError`, `fixture-not-found`, `missing-argument`, `SyntaxError`, `AttributeError-import`.
- **SEMANTIC** (judgment): `AssertionError`, `DID-NOT-RAISE`, `WrongExceptionType`, `Other`.

#### If `failed == 0 && errors == 0`

Output `Generated tests for N files: <comma-list>. All tests pass.` Stop with success.

#### If only mechanical failures remain

Auto-delegate to subagent `test-fixer` with the mechanical list. Cap retries at 3. Each iteration must reduce `failed + errors`; if not, break and treat the rest as semantic.

```json
{
  "failures": [{"test_id": "...", "kind": "ImportError", "detail": "..."}],
  "test_files": ["..."],
  "package_name": "...",
  "import_root": "..."
}
```

Wait for the agent's line: `repaired=<n> still_failing=<n> files=<list>`. After each iteration, re-stage modified files and re-run pytest+parser.

#### If semantic failures remain

Output `Halted: <n> generated test(s) need manual review.` followed by the per-test summary lines from the parser. Stop with non-zero exit.

The user inspects the failures, fixes them by hand, and re-runs preflight or commits manually. **Do not** ask the user keep/regen/discard — that prompt forced a 5-minute pause on every preflight.

### Hard rules

- **No AskUserQuestion.** This skill auto-fixes what is mechanically fixable, and halts cleanly on the rest.
- **Hermetic.** Never write `gen_tests_*.py`, `targets.json`, or any scratch helper into the user's tree. The user's `git status` shows only the new `tests/**.py` files (plus any test-fixer edits).
- **Single message.** Discover + delegate + stage + verify is one message per phase. No narration.
