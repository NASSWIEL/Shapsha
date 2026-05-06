---
name: gen-tests
description: Generate pytest tests for changed Python files (or for an explicit target). Mirrors source tree under tests/. Verifies generated tests pass; auto-repairs mechanical failures.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:gen-tests

Three modes (decided from `$ARGUMENTS`):

| Argument | Mode | Targets |
|---|---|---|
| (none) | Diff mode | `*.py` changed in working tree (staged + unstaged + untracked), excluding `tests/**` |
| One or more paths | Targeted | Each path; directories expanded to `**/*.py` |
| `all` | Full sweep | Every tracked `*.py`, excluding `tests/**`. Slow; surfaces pre-existing untested code |

Argument: $ARGUMENTS
Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`
Changed Python files: !`{ git diff --name-only --diff-filter=ACMR -- '*.py' ':!tests/**' 2>/dev/null; git diff --cached --name-only --diff-filter=ACMR -- '*.py' ':!tests/**' 2>/dev/null; git ls-files --others --exclude-standard -- '*.py' ':!tests/**' 2>/dev/null; } | sort -u | tr '\n' ' '`
All Python files (only used if $ARGUMENTS == "all"): !`git ls-files -- '*.py' ':!tests/**' 2>/dev/null | tr '\n' ' '`
Pytest version: !`R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv); $R run pytest --version 2>&1 | head -1 || echo "pytest: NOT INSTALLED"`

## Operating mode

**Silent.** No "Generating tests for X..." narration. Run discovery, delegate to `test-writer`, run pytest, optionally delegate to `test-fixer`, emit only the final summary.

**Hermetic — never write into the user's repo except the actual test files.** All discovery/parsing logic lives in `${CLAUDE_PLUGIN_ROOT}/tools/`. Do not write `gen_tests_discover.py`, `targets.json`, or any scratch helper into the user's tree. The user's git status must show only the new `tests/**.py` files plus any test-fixer edits.

## Logic

### Pre-flight

1. If `pytest: NOT INSTALLED` → output `pytest not installed. Run /bt-ai:proj-init.` exit non-zero.
2. Resolve target list:
   - `$ARGUMENTS` empty → `Changed Python files`. If empty → output `No target files.` exit 0.
   - `$ARGUMENTS == "all"` → `All Python files`. If empty → output `No tracked .py files.` exit 0.
   - Otherwise → split tokens; for each token, if it's a directory, glob `**/*.py` excluding `tests/**`; if a file, take it directly; if missing, output `Target not found: <token>.` exit non-zero. Reject any token under `tests/`: output `Target must not be under tests/.` exit non-zero.

### Discover targets

Pipe the resolved list into the bundled discovery tool:

```
!printf '%s\n' <files> | python "${CLAUDE_PLUGIN_ROOT}/tools/discover_test_targets.py"
```

The tool returns JSON:

```json
{
  "targets": [
    {"source_path": "src/foo/bar.py", "test_path": "tests/foo/test_bar.py",
     "missing_symbols": [{"name": "add", "is_async": false}, ...]}
  ],
  "skipped": [
    {"source_path": "src/handlers.py", "reason": "fastapi-handler"},
    {"source_path": "src/page.py", "reason": "streamlit-page"},
    {"source_path": "src/cli.py", "reason": "cli-entrypoint"},
    {"source_path": "src/models.py", "reason": "model-only"},
    {"source_path": "src/util.py", "reason": "all-tested"}
  ],
  "package_name": "smokepkg",
  "import_root": "smokepkg"
}
```

Skip reasons (from the discovery tool):

| Reason | Why skipped |
|---|---|
| `fastapi-handler` | File imports `fastapi`/`starlette` AND uses `@router.get`-style decorators. Best tested via `TestClient` integration tests, out of scope here. |
| `streamlit-page` | File imports `streamlit`. Streamlit pages must run inside Streamlit's runtime; unit tests are unreliable. |
| `cli-entrypoint` | File imports `click`/`typer` AND has `@*.command` decorators. Test via `CliRunner` if needed (out of scope). |
| `model-only` | File only contains class definitions (Pydantic `BaseModel`, SQLAlchemy `__tablename__`, Django `models.Model`). Auto-generated dunders are not meaningful test targets. |
| `no-public-symbols` | All names are `_private`. |
| `all-tested` | Every public name already has a `test_<name>` in the mirror file. |

The path mirror rule (deterministic):

| Source | Test path |
|---|---|
| `src/foo/bar.py` | `tests/foo/test_bar.py` |
| `foo/bar.py` (no `src/`) | `tests/foo/test_bar.py` |
| `pkg.py` (root) | `tests/test_pkg.py` |

If `targets` is empty → output:

```
All target files already have tests (or were skipped). N skipped: <reason summary>.
```

Exit 0.

### Delegate to test-writer

Invoke `Task` with agent `test-writer`. Pass JSON unchanged from discovery output (the agent expects `targets`, `package_name`, `import_root`).

Wait for agent's line: `files=<list> tests_added=<n> collection_ok=<true|false>`.

If `collection_ok=false` → output `Test collection failed.` followed by the agent's verbatim error. Exit non-zero. Do not run the verify phase.

### Verify (run + classify failures)

Run pytest on the freshly written/modified test paths and pipe through the bundled failure parser:

```
!R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py"); $R run pytest -q --no-header --tb=short <new test paths> 2>&1 | python "${CLAUDE_PLUGIN_ROOT}/tools/parse_pytest_failures.py"
```

The parser returns JSON with `passed`, `failed`, `errors`, `mechanical[]`, `semantic[]`.

**MECHANICAL kinds** (auto-fixable — forward to `test-fixer` agent without asking):
`ModuleNotFoundError`, `ImportError`, `NameError`, `fixture-not-found`, `missing-argument`, `SyntaxError`, `AttributeError-import`.

**SEMANTIC kinds** (judgment required — ask the user):
`AssertionError`, `DID-NOT-RAISE`, `WrongExceptionType`, `Other`.

#### If `failed == 0 && errors == 0`

Output `Generated tests for N files: <comma-list>. All tests pass.` Exit 0.

#### If only mechanical failures remain (one or more)

Auto-delegate to `test-fixer` agent with the mechanical list. Cap retries at 3 — if the loop doesn't converge, treat the remaining as semantic.

```json
{
  "failures": [
    {"test_id": "tests/foo/test_bar.py::test_add", "kind": "ImportError",
     "detail": "cannot import name 'add'"},
    ...
  ],
  "test_files": ["tests/foo/test_bar.py", ...],
  "package_name": "...",
  "import_root": "..."
}
```

Wait for agent's line: `repaired=<n> still_failing=<n> files=<list>`.

After agent returns, re-run pytest + parser. Repeat up to 3 times. Each iteration must reduce `failed + errors`; if not, break and treat the rest as semantic.

#### If semantic failures remain after the auto-fix loop

Use `AskUserQuestion` (single prompt, three options):

- `keep` — Keep the generated tests as-is. The user will edit them.
- `regen` — Re-run `test-writer` on the still-failing symbols only (passing the failure context as a hint).
- `discard` — Delete the test functions that still fail. (Whole files only if every test in the file fails.)

On `regen`: re-invoke `test-writer` with payload extended by `previous_failures` for the affected symbols, then re-verify (one more iteration of the loop).

On `discard`: delete only the failing `test_*` functions from the affected files (leave passing siblings intact). If a file ends up with zero tests, delete the file too.

## Output

Single line on the final state, no preamble:

| State | Output |
|---|---|
| All pass first try | `Generated tests for N files: <list>. All tests pass.` |
| All pass after auto-fix | `Generated tests for N files: <list>. <K> mechanical failures auto-repaired.` |
| Semantic remaining, user kept | `Generated tests for N files: <list>. <K> tests need user attention.` exit non-zero |
| Semantic remaining, user discarded | `Generated tests for N files: <list>. <K> tests discarded.` exit 0 |
| User regen → still semantic | `Generated tests for N files: <list>. <K> tests still need user attention after regen.` exit non-zero |
| Discovery skipped everything | `All target files already have tests (or were skipped). <N> skipped: <reason summary>.` exit 0 |

## Edge cases

- Source file has no public symbols → discovery returns it under `skipped` with reason `no-public-symbols`.
- Test file already exists → agent appends new `test_*` functions only; never overwrites existing ones.
- `package_name` and `import_root` both null → agent uses path-based imports (sys.path).
- `pyproject.toml` malformed → discovery tool falls back gracefully (`package_name=null`).
- Targeted mode with `tests/` path → rejected pre-flight.
- Auto-fix loop diverges (each iteration the count flat or rising) → break after 3, treat as semantic.
- User on `regen` and target was already at retry cap → run regen as a fresh attempt (resets the counter).
