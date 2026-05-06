#!/usr/bin/env python3
"""Classify ruff JSON output by severity bucket.

Reads ruff JSON from stdin, prints a deterministic plaintext report:

    summary critical=N high=N low=N medium=N
    [CRITICAL] path:line code message
    [HIGH]     path:line code message

Severity buckets (mirror skills/check-style/SKILL.md):

  Critical : prefixes F*, E9*           (halt fix mode)
  High     : prefixes B*, S*            (ask user)
  Low      : prefixes E (non-E9), W, D, I, UP   (silent auto-fix)
  Medium   : prefixes N, C, PL          (hidden — never printed, never fixed)

Usage:
    ruff check ... --output-format=json | python classify_ruff.py
    python classify_ruff.py < ruff.json

Exit 0 always — this is a pure classifier; the calling skill decides what to
do based on the printed summary line.
"""
from __future__ import annotations

import json
import sys


def bucket(code: str) -> str:
    if code.startswith(("F", "E9")):
        return "critical"
    if code.startswith(("B", "S")):
        return "high"
    if code.startswith(("N", "C", "PL")):
        return "medium"
    if code.startswith(("E", "W", "D", "I", "UP")):
        return "low"
    return "low"


def truncate(s: str, n: int = 80) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("summary critical=0 high=0 low=0 medium=0")
        return 0
    try:
        findings = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid ruff JSON: {e}", file=sys.stderr)
        return 1
    if not isinstance(findings, list):
        print("error: ruff JSON not an array", file=sys.stderr)
        return 1

    counts = {"critical": 0, "high": 0, "low": 0, "medium": 0}
    lines: list[tuple[str, str]] = []  # (bucket_label, line)

    for f in findings:
        code = f.get("code") or ""
        path = f.get("filename") or ""
        loc = f.get("location") or {}
        row = loc.get("row") or "?"
        msg = f.get("message") or ""
        b = bucket(code)
        counts[b] += 1
        if b in ("critical", "high"):
            label = "[CRITICAL]" if b == "critical" else "[HIGH]    "
            lines.append((b, f"{label} {path}:{row} {code} {truncate(msg)}"))

    print(
        f"summary critical={counts['critical']} high={counts['high']} "
        f"low={counts['low']} medium={counts['medium']}"
    )
    # Critical first, then High; preserve filename ordering inside each bucket.
    for b in ("critical", "high"):
        for tag, line in lines:
            if tag == b:
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
