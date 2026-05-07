#!/usr/bin/env python3
"""Print ADDED/REMOVED dependency names between HEAD:pyproject.toml and the working copy.

Pure version bumps are ignored: only the set of dependency *names* matters.
Reads both PEP 621 ``[project].dependencies`` and Poetry ``[tool.poetry.dependencies]``.
Silent on no-op or missing files; never raises.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        sys.exit(0)

NAME_RE = re.compile(r"[A-Za-z0-9_.\-]+")


def names(deps) -> set[str]:
    out: set[str] = set()
    for d in deps or []:
        m = NAME_RE.match(str(d).strip())
        if m:
            out.add(m.group(0).lower())
    return out


def project_deps(toml_bytes: bytes) -> set[str] | None:
    if not toml_bytes:
        return None
    try:
        data = tomllib.loads(toml_bytes.decode("utf-8"))
    except Exception:
        return None
    proj = data.get("project", {}).get("dependencies", []) or []
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
    poetry_names = list(poetry.keys()) if isinstance(poetry, dict) else []
    return (names(proj) | names(poetry_names)) - {"python"}


def main() -> int:
    cur_path = Path("pyproject.toml")
    if not cur_path.exists():
        return 0
    try:
        cur_bytes = cur_path.read_bytes()
    except Exception:
        return 0
    try:
        head_bytes = subprocess.run(
            ["git", "show", "HEAD:pyproject.toml"],
            capture_output=True,
            check=False,
        ).stdout
    except Exception:
        head_bytes = b""

    old = project_deps(head_bytes) or set()
    new = project_deps(cur_bytes) or set()
    added = sorted(new - old)
    removed = sorted(old - new)
    if added:
        print("ADDED:", " ".join(added))
    if removed:
        print("REMOVED:", " ".join(removed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
