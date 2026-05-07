#!/usr/bin/env python3
"""Print the configured bt-ai runner, or probe a tool's version through it.

Default mode (no args) — print the runner name only:
    $ python resolve_runner.py
    uv

Probe mode (`--probe TOOL`) — resolve runner internally, then print
``<runner> run <tool> --version`` first line, or ``<tool>: NOT INSTALLED``
on any failure. Used in SKILL.md Context blocks where the
``R=$(...); $R run ...`` shell pattern is rejected by Claude Code's
permission harness as ``simple_expansion``.

Resolution order for the runner:
1. ``[tool.bt-ai].runner`` from ``pyproject.toml`` if it is ``uv`` or ``poetry``.
2. If only ``uv`` is installed on PATH → ``uv``.
3. If only ``poetry`` is installed on PATH → ``poetry``.
4. If both are installed → ``uv`` (project not initialized; default to faster).
5. If neither is installed → ``uv`` (so the resulting ``uv: command not found``
   message at least points at something the user can install).
"""
from __future__ import annotations

import shutil
import subprocess
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
    return "uv"


def resolve_runner() -> str:
    if not HAS_TOML:
        return probe_installed()
    try:
        with open("pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return probe_installed()
    runner = (data.get("tool") or {}).get("bt-ai", {}).get("runner")
    if runner in ("uv", "poetry"):
        return runner
    return probe_installed()


def probe_tool(tool: str) -> str:
    """Run ``<runner> run <tool> --version`` and return the first output line."""
    runner = resolve_runner()
    try:
        result = subprocess.run(
            [runner, "run", tool, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return f"{tool}: NOT INSTALLED"
    if result.returncode != 0:
        return f"{tool}: NOT INSTALLED"
    output = (result.stdout or result.stderr or "").strip().splitlines()
    return output[0] if output else f"{tool}: NOT INSTALLED"


def main() -> int:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--probe":
        print(probe_tool(args[1]))
        return 0
    if args and args[0] == "--probe":
        print("usage: resolve_runner.py --probe TOOL", file=sys.stderr)
        return 2
    print(resolve_runner())
    return 0


if __name__ == "__main__":
    sys.exit(main())
