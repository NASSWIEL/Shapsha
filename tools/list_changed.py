#!/usr/bin/env python3
"""List changed (modified+staged+untracked) or all-tracked files matching globs.

Usage:
    list_changed.py [--all] [--no-tests] [GLOB ...]

If no glob is given, defaults to '*.py'. Output is space-separated unique paths.
Empty string when nothing matches or when not in a git repo.

Replaces the rejected-by-harness shell pattern:
    { git diff ... ; git diff --cached ... ; git ls-files --others ... ; } | sort -u
"""
from __future__ import annotations

import subprocess
import sys


def run(cmd: list[str]) -> list[str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    globs = [a for a in args if not a.startswith("--")] or ["*.py"]
    use_all = "--all" in flags
    no_tests = "--no-tests" in flags

    if use_all:
        files = run(["git", "ls-files", "--", *globs])
    else:
        files = (
            run(["git", "diff", "--name-only", "--diff-filter=ACMR", "--", *globs])
            + run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", *globs])
            + run(["git", "ls-files", "--others", "--exclude-standard", "--", *globs])
        )

    if no_tests:
        files = [
            f for f in files
            if not (f.startswith("tests/") or "/tests/" in f or f == "tests")
        ]

    print(" ".join(sorted(set(files))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
