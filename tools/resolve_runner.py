#!/usr/bin/env python3
"""Print the configured bt-ai runner ('uv' or 'poetry').

Resolution order:
1. `[tool.bt-ai].runner` from `pyproject.toml` if it is `uv` or `poetry`.
2. If only `uv` is installed on PATH → `uv`.
3. If only `poetry` is installed on PATH → `poetry`.
4. If both are installed → `uv` (project not initialized; default to faster).
5. If neither is installed → `uv` (so the resulting `uv: command not found`
   message at least points at something the user can install).

This script exists so skills don't have to inline the Python one-liner
seven times across SKILL.md files. Invoke as:

    R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py")
    "$R" run ruff check ...
"""
from __future__ import annotations

import shutil
import sys

try:
    import tomllib  # type: ignore[import]

    HAS_TOML = True
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[import]

        HAS_TOML = True
    except ImportError:
        HAS_TOML = False


def probe_installed() -> str:
    """Return the runner name to use based on what is on PATH."""
    has_uv = shutil.which("uv") is not None
    has_poetry = shutil.which("poetry") is not None
    if has_uv and not has_poetry:
        return "uv"
    if has_poetry and not has_uv:
        return "poetry"
    # Both present → uv (default for new projects).
    # Neither present → uv (so the user gets a uv-shaped error to follow up on).
    return "uv"


def main() -> int:
    if not HAS_TOML:
        print(probe_installed())
        return 0
    try:
        with open("pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        print(probe_installed())
        return 0
    runner = (data.get("tool") or {}).get("bt-ai", {}).get("runner")
    if runner in ("uv", "poetry"):
        print(runner)
        return 0
    print(probe_installed())
    return 0


if __name__ == "__main__":
    sys.exit(main())
