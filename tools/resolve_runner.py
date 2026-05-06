#!/usr/bin/env python3
"""Print the configured bt-ai runner ('uv' or 'poetry').

Reads `[tool.bt-ai].runner` from `pyproject.toml` in the current directory.
Falls back to 'uv' if the file is missing, malformed, or the key is unset.

This script exists so skills don't have to inline the Python one-liner
seven times across SKILL.md files. Invoke as:

    R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py")
    "$R" run ruff check ...
"""
from __future__ import annotations

import sys

try:
    import tomllib  # type: ignore[import]
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[import]
    except ImportError:
        print("uv")
        sys.exit(0)


def main() -> int:
    try:
        with open("pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        print("uv")
        return 0
    runner = (data.get("tool") or {}).get("bt-ai", {}).get("runner")
    if runner not in ("uv", "poetry"):
        print("uv")
        return 0
    print(runner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
