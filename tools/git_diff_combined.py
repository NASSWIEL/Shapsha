#!/usr/bin/env python3
"""Combined diff: working-tree + index, optionally with untracked files as new-file hunks.

Usage:
    git_diff_combined.py [--stat] [--include-untracked] [--cap N] [--grep PATTERN] [GLOB ...]

Replaces the rejected-by-harness shell pattern:
    { git diff ... ; git diff --cached ... ; for f in $(git ls-files --others ...); do ... done; } | head -N

Flags:
    --stat               Pass --stat to git diff (no untracked-file hunks).
    --include-untracked  Append untracked files as `=== NEW FILE: <path> ===` hunks.
    --cap N              Truncate output to first N lines.
    --grep PATTERN       Apply a Python regex filter line-by-line on the output.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def main() -> int:
    argv = sys.argv[1:]
    stat = False
    include_untracked = False
    cap: int | None = None
    grep: str | None = None
    globs: list[str] = []

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stat":
            stat = True
        elif a == "--include-untracked":
            include_untracked = True
        elif a == "--cap" and i + 1 < len(argv):
            i += 1
            try:
                cap = int(argv[i])
            except ValueError:
                cap = None
        elif a == "--grep" and i + 1 < len(argv):
            i += 1
            grep = argv[i]
        elif not a.startswith("--"):
            globs.append(a)
        i += 1

    flags = ["--stat"] if stat else []
    tail = ["--", *globs] if globs else []

    chunks: list[str] = []
    chunks.append(run(["git", "diff", *flags, *tail]))
    chunks.append(run(["git", "diff", "--cached", *flags, *tail]))

    if include_untracked and not stat:
        listing = run(["git", "ls-files", "--others", "--exclude-standard", *tail])
        for path in listing.splitlines():
            path = path.strip()
            if not path or not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
            except OSError:
                continue
            chunks.append(f"=== NEW FILE: {path} ===\n{body}\n")

    text = "".join(chunks)

    if grep:
        try:
            pattern = re.compile(grep)
        except re.error:
            pattern = None
        if pattern is not None:
            text = "\n".join(line for line in text.splitlines() if pattern.search(line))
            if text:
                text += "\n"

    if cap is not None:
        text = "\n".join(text.splitlines()[:cap])
        if text and not text.endswith("\n"):
            text += "\n"

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
