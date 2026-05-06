#!/usr/bin/env python3
"""Discover untested public functions in changed Python files.

Reads a newline-separated list of source paths from stdin, emits a JSON
payload on stdout that the gen-tests skill forwards to the test-writer agent.

Behavior matches skills/gen-tests/SKILL.md:

  - Walks each source via ast (FunctionDef + AsyncFunctionDef).
  - Drops names starting with "_" (private).
  - Drops files that are clearly NOT pure-function code:
      * FastAPI/Starlette handlers — imports `fastapi`/`starlette` AND has
        decorators with `.get`/`.post`/`.put`/`.delete`/`.patch`/`.route`.
      * Streamlit pages — imports `streamlit`.
      * Click/Typer CLI entrypoints — imports `click` or `typer` AND has
        `@click.command`/`@cli.command`/`@app.command` decorators.
      * Pydantic models, ORM tables (SQLAlchemy `__tablename__`,
        Django `models.Model`) — class-only files where the public
        functions are dunder/auto-generated.
  - Detects the existing import root by scanning `tests/**.py` for the
    most-common first-segment import that maps to a real directory.
  - Maps source path → canonical test path mirroring the source tree:
      src/foo/bar.py     → tests/foo/test_bar.py
      foo/bar.py         → tests/foo/test_bar.py
      pkg.py (root)      → tests/test_pkg.py
  - Reads the existing test file (if present), extracts test_* function
    names, computes the missing-symbols set.

Usage:
    git diff --name-only ... | python discover_test_targets.py
    echo -e "src/foo.py\\nsrc/bar.py" | python discover_test_targets.py

    # Targeted mode (user explicitly named these files): bypass the
    # framework-skip filter so handlers / pages / CLI entrypoints still
    # get tests generated.
    echo "src/handlers.py" | python discover_test_targets.py --no-skip-filter

Output: JSON on stdout, line-prefixed errors on stderr.

The output schema matches the test-writer agent's input contract:
{
  "targets": [
    {"source_path": "...", "test_path": "...",
     "missing_symbols": [{"name": "...", "is_async": bool}, ...]},
    ...
  ],
  "skipped": [
    {"source_path": "...", "reason": "fastapi-handler|streamlit-page|cli-entrypoint|model-only|no-public-symbols|all-tested"},
    ...
  ],
  "package_name": "<from pyproject.toml [project] name, or null>",
  "import_root": "<discovered or null>"
}
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import tomllib  # type: ignore[import]

    HAS_TOML = True
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[import]

        HAS_TOML = True
    except ImportError:
        # Discovery still works without TOML — package_name() simply returns None
        # and the test-writer falls back to path-based imports.
        tomllib = None  # type: ignore[assignment]
        HAS_TOML = False

ROUTE_DECORATORS = {"get", "post", "put", "delete", "patch", "route", "head", "options"}
CLI_DECORATORS = {"command"}


def detect_skip_reason(tree: ast.AST, source: str) -> str | None:
    """Return a skip reason string if the file should not be unit-tested."""
    imported_names = _imported_modules(tree)

    # Streamlit pages
    if "streamlit" in imported_names:
        return "streamlit-page"

    # FastAPI / Starlette handlers — needs both the import AND a route-style
    # decorator on at least one top-level function. Pure utility modules that
    # happen to import FastAPI for type hints are NOT skipped.
    has_web_framework = bool(imported_names & {"fastapi", "starlette"})
    if has_web_framework and _has_route_decorator(tree):
        return "fastapi-handler"

    # CLI entrypoints
    if imported_names & {"click", "typer"} and _has_cli_decorator(tree):
        return "cli-entrypoint"

    # Pure-model files: class definitions only, no top-level def/async def.
    has_classes = any(isinstance(n, ast.ClassDef) for n in tree.body)  # type: ignore[attr-defined]
    has_top_level_def = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in tree.body  # type: ignore[attr-defined]
    )
    if has_classes and not has_top_level_def:
        body_str = source.lower()
        if (
            "models.model" in body_str
            or "__tablename__" in body_str
            or "basemodel" in body_str
        ):
            return "model-only"

    return None


def _imported_modules(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module.split(".")[0])
    return out


def _has_route_decorator(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            name = _decorator_attr_tail(dec)
            if name and name in ROUTE_DECORATORS:
                return True
    return False


def _has_cli_decorator(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            name = _decorator_attr_tail(dec)
            if name and name in CLI_DECORATORS:
                return True
    return False


def _decorator_attr_tail(dec: ast.AST) -> str | None:
    """Return the tail of a decorator like `@app.get(...)` → `get`."""
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Name):
        return dec.id
    return None


def public_symbols(tree: ast.Module) -> list[tuple[str, bool]]:
    """Return [(name, is_async)] for top-level functions and class methods.

    Only public names (not starting with "_"). Walks classes one level deep.
    """
    out: list[tuple[str, bool]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            out.append((node.name, False))
        elif isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
            out.append((node.name, True))
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if (
                    isinstance(child, ast.FunctionDef)
                    and not child.name.startswith("_")
                ):
                    out.append((child.name, False))
                elif (
                    isinstance(child, ast.AsyncFunctionDef)
                    and not child.name.startswith("_")
                ):
                    out.append((child.name, True))
    return out


def existing_test_names(test_path: Path) -> set[str]:
    if not test_path.is_file():
        return set()
    try:
        text = test_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ):
            out.add(node.name[len("test_"):])
    return out


def compute_test_path(source_path: str) -> str:
    p = Path(source_path)
    parts = list(p.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts:
        return f"tests/test_{p.stem}.py"
    parts[-1] = f"test_{p.stem}.py"
    return "tests/" + "/".join(parts)


def discover_import_root(repo: Path) -> str | None:
    tests_dir = repo / "tests"
    if not tests_dir.is_dir():
        return None
    candidates: Counter[str] = Counter()
    pat = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)")
    for test_file in tests_dir.rglob("*.py"):
        if test_file.name in ("__init__.py", "conftest.py"):
            continue
        try:
            text = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            m = pat.match(line)
            if not m:
                continue
            candidates[m.group(1).split(".")[0]] += 1
    for cand, _ in candidates.most_common():
        if (repo / cand).is_dir() or (repo / "src" / cand).is_dir():
            return cand
    return None


def package_name(repo: Path) -> str | None:
    if not HAS_TOML:
        return None
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        data = tomllib.loads(pp.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    return (data.get("project") or {}).get("name") or (
        (data.get("tool") or {}).get("poetry") or {}
    ).get("name")


def main() -> int:
    skip_filter = "--no-skip-filter" not in sys.argv[1:]
    repo = Path.cwd()
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({
            "targets": [],
            "skipped": [],
            "package_name": package_name(repo),
            "import_root": discover_import_root(repo),
        }))
        return 0

    paths = [p.strip() for p in raw.splitlines() if p.strip()]
    targets = []
    skipped = []

    for src_path in paths:
        full = repo / src_path
        if not full.is_file():
            skipped.append({"source_path": src_path, "reason": "not-found"})
            continue
        if full.suffix != ".py":
            skipped.append({"source_path": src_path, "reason": "not-python"})
            continue
        if any(part == "tests" for part in full.parts):
            skipped.append({"source_path": src_path, "reason": "is-test-file"})
            continue
        try:
            source = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            skipped.append({"source_path": src_path, "reason": f"read-error: {e}"})
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            skipped.append({"source_path": src_path, "reason": f"syntax-error: {e}"})
            continue

        if skip_filter:
            skip = detect_skip_reason(tree, source)
            if skip:
                skipped.append({"source_path": src_path, "reason": skip})
                continue

        symbols = public_symbols(tree)
        if not symbols:
            skipped.append({"source_path": src_path, "reason": "no-public-symbols"})
            continue

        test_path = compute_test_path(src_path)
        existing = existing_test_names(repo / test_path)
        missing = [
            {"name": name, "is_async": is_async}
            for name, is_async in symbols
            if name not in existing
        ]
        if not missing:
            skipped.append({"source_path": src_path, "reason": "all-tested"})
            continue

        targets.append({
            "source_path": src_path,
            "test_path": test_path,
            "missing_symbols": missing,
        })

    print(json.dumps({
        "targets": targets,
        "skipped": skipped,
        "package_name": package_name(repo),
        "import_root": discover_import_root(repo),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
