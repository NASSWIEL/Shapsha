---
name: gen-tests
description: Generate pytest tests for changed Python files (or for an explicit target). Mirrors source tree under tests/.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:gen-tests

Two modes:

- **Diff mode** (no arguments): scan `*.py` changed in `git diff HEAD`, excluding `tests/**`.
- **Targeted mode** (one or more paths in `$ARGUMENTS`): generate for those paths only.

Argument: $ARGUMENTS
Runner: !`python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv`
Changed Python files (diff mode): !`{ git diff --name-only --diff-filter=ACMR -- '*.py' ':!tests/**' 2>/dev/null; git diff --cached --name-only --diff-filter=ACMR -- '*.py' ':!tests/**' 2>/dev/null; git ls-files --others --exclude-standard -- '*.py' ':!tests/**' 2>/dev/null; } | sort -u | tr '\n' ' '`
Pytest version: !`R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv); $R run pytest --version 2>&1 | head -1 || echo "pytest: NOT INSTALLED"`

## Operating mode

**Silent.** No "Generating tests for X..." narration. Run discovery, delegate to `test-writer` agent, emit only the final summary.

## Logic

### Pre-flight

1. If `pytest: NOT INSTALLED` → output `pytest not installed. Run /bt-ai:proj-init.` exit non-zero.

### Resolve target list

- If `$ARGUMENTS` is non-empty:
  - Treat each whitespace-separated token as a path.
  - For each path, if it's a directory, glob `**/*.py` under it (excluding `tests/**`); if it's a file, use it directly.
  - If any token does not resolve to existing path → output `Target not found: <token>.` exit non-zero.
- If `$ARGUMENTS` is empty:
  - Use the changed-files list from above.
  - If empty → output `No target files.` exit 0.

### Compute test paths

For each target source file:

- `src/foo/bar.py` → `tests/foo/test_bar.py`
- `foo/bar.py` (no `src/` prefix) → `tests/foo/test_bar.py`
- `pkg.py` at root → `tests/test_pkg.py`

### Filter — find missing test symbols

For each target file:

1. Extract top-level functions, **async functions**, and class methods (non-underscore-prefixed) using AST. Pseudocode:
   ```python
   import ast
   tree = ast.parse(open(path, encoding='utf-8').read())
   sync_syms = []
   async_syms = []
   for node in ast.walk(tree):
       if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
           sync_syms.append(node.name)
       elif isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith('_'):
           async_syms.append(node.name)
   ```
   Both `FunctionDef` and `AsyncFunctionDef` MUST be walked. Pure grep on `^def ` is insufficient because it misses `async def` (FastAPI, asyncio, etc.).
2. Read the corresponding test file if it exists. Extract existing `test_*` functions.
3. Missing symbols = source symbols not covered by any matching `test_<name>` function.
4. If a source has no public symbols → skip.
5. If all symbols already covered → skip.

If after filtering no targets remain → output `All changed files already have tests.` exit 0.

### Discover import root

Before delegating to `test-writer`, infer the import root the project's existing tests already use, so generated tests don't fail with `ImportError`:

1. Glob `tests/**.py` (excluding `__init__.py`, `conftest.py`).
2. From each test file, grep for `^(from|import) (\w[\w.]*)` (top-level imports). For each match, take the module's first dotted segment as a candidate root (e.g., `from src.api.routes import …` → `src`; `from retrodoc.generator import …` → `retrodoc`).
3. The most common candidate that **also exists** as a directory under `src/` or at repo root → set `import_root`.
4. If no existing tests OR no candidate maps to a real directory → fall back to `[project] name` (the previous behaviour).
5. If still null → fall back to `null` (path-based imports in agent).

Pass `import_root` to the agent in addition to `package_name`.

### Delegate to test-writer

Invoke `Task` with agent `test-writer`. Pass JSON:

```json
{
  "targets": [
    {
      "source_path": "src/foo/bar.py",
      "test_path": "tests/foo/test_bar.py",
      "missing_symbols": [
        {"name": "add", "is_async": false},
        {"name": "fetch_data", "is_async": true}
      ]
    }
  ],
  "package_name": "<from pyproject.toml [project] name, or null>",
  "import_root": "<discovered import root, or null>"
}
```

`package_name` is read from `pyproject.toml` `[project] name` if present, otherwise `null`. `import_root` is discovered as described above. The agent prefers `import_root` when composing import statements; if null, falls back to `package_name`; if both null, uses path-based imports.

For each `is_async: true` symbol, the agent generates a sync test function that wraps the call with `asyncio.run(...)`. This avoids requiring `pytest-asyncio`.

Wait for agent's single-line summary: `files=<list> tests_added=<n> collection_ok=<true|false>`.

### Verify

After agent returns, run:

```
!R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv); $R run pytest --collect-only <list of new/modified test paths> 2>&1 | tail -10
```

If exit is non-zero, output `Test collection failed:` followed by the captured output verbatim. Exit non-zero. Do NOT auto-rewrite the generated tests.

## Output

Single line, no preamble:

```
Generated tests for N files: <comma-list>.
```

Or one of the early-exit messages above.

## Edge cases

- Source file has no functions/classes → skip silently.
- Test file already exists → agent appends new test functions only; never overwrites existing ones.
- `package_name` is `null` and tests need imports → agent uses `from <relative-path> import ...` (sys.path-based).
- Pytest collection fails → user must inspect; do not auto-fix.
- Targeted mode with `tests/` path passed → reject: `Target must not be under tests/.` exit non-zero.
- Source contains only private functions (`_helper`) → skipped per rules above.
