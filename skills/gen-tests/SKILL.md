---
name: gen-tests
description: "Génère des tests pytest pour les fichiers Python modifiés (ou une cible explicite). Reflète l'arborescence sous tests/. Fan-out parallèle (un sous-agent par fichier source, en simultané). Vérifie et auto-répare les échecs mécaniques. S'arrête sur les échecs sémantiques."
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

Generate the missing pytest tests for the resolved targets via **parallel fan-out** (one `test-writer` subagent per source file, all spawned in a single message), verify they collect+pass, auto-repair mechanical failures, and emit one summary line. Halt only when semantic failures (real assertion mismatches) remain — those need the human's judgment, not another retry.

### Guards

1. `pytest: NOT INSTALLED` → output `pytest not installed. Run /bt-ai:proj-init.` Stop.
2. Resolve target list:
   - `$ARGUMENTS` empty → use `Changed Python files`. If empty → output `No target files.` Stop with success.
   - `$ARGUMENTS == "all"` → use `All Python files`. If empty → output `No tracked .py files.` Stop with success.
   - Otherwise → split tokens; for each token, if it's a directory, glob `**/*.py` excluding `tests/**`; if a file, take it directly; if missing, output `Target not found: <token>.` Stop. Reject any token under `tests/`: output `Target must not be under tests/.` Stop.

### Discover targets

The model performs target discovery directly using `Read` and `Glob`. Build two lists: `targets` (files needing test generation) and `skipped` (files filtered out, with reason).

**Step 1 — Resolve `package_name` and `import_root`** from `pyproject.toml`:
- `Read` `pyproject.toml`. Extract `[project].name` (PEP 621) or `[tool.poetry].name`. Lowercase, replace hyphens with underscores → `package_name`.
- If `src/<package_name>/` exists (`Glob` for `src/<package_name>/__init__.py`) → `import_root = package_name`.
- Else if `<package_name>/__init__.py` exists at repo root → `import_root = package_name`.
- Else if `src/__init__.py` exists or sources live under `src/` → `import_root = "src"`.
- Else → `import_root = null`, `package_name = null` (path-based imports).

**Step 2 — Path mirror** (deterministic):

| Source | Test path |
|---|---|
| `src/foo/bar.py` | `tests/foo/test_bar.py` |
| `foo/bar.py` (no `src/`) | `tests/foo/test_bar.py` |
| `pkg.py` (root) | `tests/test_pkg.py` |

**Step 3 — Skip filter.** Diff mode and `all` mode apply the filter; **targeted mode skips this step** (when the user explicitly named files, respect that intent). For each source, `Read` the file content and apply heuristics in order. The first match wins:

| Skip reason | Detection |
|---|---|
| `fastapi-handler` | Imports `fastapi` AND defines a router/app at module top level (e.g., `app = FastAPI(...)`, `router = APIRouter(...)`) |
| `streamlit-page` | Imports `streamlit` (typically `import streamlit as st`) |
| `cli-entrypoint` | Has `if __name__ == "__main__":` AND uses `argparse`, `click`, `typer`, or `sys.argv` directly |
| `model-only` | Module's only top-level non-underscore symbols are dataclasses (`@dataclass`), Pydantic models (inherit `BaseModel`), or `Enum` subclasses. No standalone functions. |
| `no-public-symbols` | No top-level `def`, `async def`, or `class` whose name does not start with `_` |

**Step 4 — Existing-tests check.** For each non-skipped source, compute its `test_path` (Step 2), then `Glob` for it. If the test file exists, `Read` it and list its top-level `def test_*` functions. For each public symbol in the source, check whether at least one test mentions the symbol name. If every public symbol has a corresponding test, skip with reason `all-tested`.

**Step 5 — Build `missing_symbols`.** For each source that survived all filters, list public symbols (top-level `def`/`async def`/`class` not starting with `_`) that have no existing test. Each entry: `{"name": "<symbol>", "is_async": <bool>}` (true only for `async def` symbols).

**Step 6 — Assemble `targets[]`.** Each target: `{"source_path", "test_path", "missing_symbols"}`. Drop targets whose `missing_symbols` is empty (treat as `all-tested`).

If `targets` is empty after this discovery → output `All target files already have tests (or were skipped). N skipped: <reason summary>.` Stop with success.

### Fan-out to test-writer (parallel)

**Issue ALL `Task` calls in a single message** — this is the parallelism that delivers the speedup. For N targets ≤ 10, that's N `Task` tool calls in the same response. For N > 10, split into batches of 10 across consecutive messages (Claude Code's parallel limit is 10 per message).

Each `Task` call invokes subagent `test-writer` with this JSON:

```json
{
  "target": {
    "source_path": "...",
    "test_path": "...",
    "missing_symbols": [...]
  },
  "package_name": "<package_name from Step 1>",
  "import_root": "<import_root from Step 1>",
  "runner": "<literal Runner from Context, uv or poetry>"
}
```

Each subagent returns a single line:

```
file=<test_path> tests_added=<n> omitted=<n> collection_ok=<true|false>
```

Aggregate across all subagents:
- `files` = list of every `file=` value
- `total_added` = sum of `tests_added`
- `total_omitted` = sum of `omitted`
- `collection_ok_all` = AND of all `collection_ok` values

If `collection_ok_all == false` → output `Halted: test collection failed.` followed by the file=... line(s) where collection_ok=false. Stop.

### Stage

For each file in `files`, run `git add -- "<file>"`.

### Verify

Run pytest on all the freshly written test paths in one batch. Replace `<runner>` with the literal Runner value from the Context above:

```
<runner> run pytest -q --no-header --tb=short <space-separated test paths from files> 2>&1
```

Read pytest's output. The "short test summary info" block at the end lists each failure (one line per `FAILED` or `ERROR`). Above it, each traceback ends with the actual error type. Build counters `passed`, `failed`, `errors` from the final pytest summary line, then for each failure produce a `{test_id, kind, detail}` entry routed to `mechanical[]` or `semantic[]`:

**MECHANICAL** (auto-fixable, route to `test-fixer`):

| `kind` | Detection |
|---|---|
| `ModuleNotFoundError` | Traceback ends with `ModuleNotFoundError: No module named '...'` |
| `ImportError` | Traceback ends with `ImportError: cannot import name '...' from '...'` |
| `NameError` | Traceback ends with `NameError: name '...' is not defined` |
| `fixture-not-found` | ERROR section contains `fixture '...' not found` |
| `missing-argument` | `TypeError: <fn>() missing N required positional argument` |
| `SyntaxError` | Traceback ends with `SyntaxError: ...` |
| `AttributeError-import` | `AttributeError: module '...' has no attribute '...'` from a stale `from X import Y` |

**SEMANTIC** (judgment-required, halt):

| `kind` | Detection |
|---|---|
| `AssertionError` | `assert <left> == <right>` (or other comparison) failure with concrete values |
| `DID-NOT-RAISE` | `Failed: DID NOT RAISE <ExceptionType>` |
| `WrongExceptionType` | `pytest.raises(...)` caught a different exception type than expected |
| `Other` | Anything not matched above |

#### If `failed == 0 && errors == 0`

Output `Generated tests for N files in parallel: <comma-list>. All tests pass.` Stop with success.

#### If only mechanical failures remain

Auto-delegate to subagent `test-fixer` with the mechanical list. Cap retries at 3. Each iteration must reduce `failed + errors`; if not, break and treat the rest as semantic.

```json
{
  "failures": [{"test_id": "...", "kind": "ImportError", "detail": "..."}],
  "test_files": ["..."],
  "package_name": "...",
  "import_root": "...",
  "runner": "<literal Runner from Context, uv or poetry>"
}
```

Wait for the agent's line: `repaired=<n> still_failing=<n> files=<list>`. After each iteration, re-stage modified files and re-run pytest, re-classifying failures the same way.

#### If semantic failures remain

Output `Halted: <n> generated test(s) need manual review.` followed by one line per semantic failure (`<test_id>: <kind> — <detail>`). Stop with non-zero exit.

The user inspects the failures, fixes them by hand, and re-runs preflight or commits manually. **Do not** ask the user keep/regen/discard.

### Hard rules

- **Fan-out parallèle**: les N appels `Task` partent dans **un seul message** du parent. Sériels = pénalité de 5-10× sur le wall-clock.
- **No AskUserQuestion.** This skill auto-fixes what is mechanically fixable, and halts cleanly on the rest.
- **Hermetic.** Never write `gen_tests_*.py`, `targets.json`, parser scripts, or any scratch helper into the user's tree. The user's `git status` shows only the new `tests/**.py` files (plus any test-fixer edits).
- **Single message per phase.** Discover (1 message of Reads/Globs), fan-out (1 message of N Tasks), stage (1 message of git adds), verify (1 message), then retry loop (1 message per iteration).
