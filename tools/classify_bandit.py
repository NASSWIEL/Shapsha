#!/usr/bin/env python3
"""Classify bandit JSON output as FIXABLE vs BLOCKED.

Reads bandit JSON from stdin, prints a deterministic plaintext report:

    summary blocked=N fixable=N total=N
    [SEV/CONF] [BLOCKED|FIXABLE] path:line code message

The classification table mirrors skills/security/SKILL.md and
agents/security-fixer.md. Keep them in lockstep.

BLOCKED set:
  Dangerous-execution    : B102 B307 B301 B324 B501-B508 B602-B608 B610 B611 B701
  Context-sensitive      : B104 B105 B106 B107 B108

Everything else is FIXABLE. The fixer agent's per-code action table further
narrows what is actually edited; most FIXABLE items are still report-only.

Usage:
    bandit -f json ... | python classify_bandit.py
    python classify_bandit.py < bandit.json
"""
from __future__ import annotations

import json
import sys

DANGEROUS_EXEC = {
    "B102",  # exec
    "B307",  # eval
    "B301",  # pickle deserialization
    "B324",  # insecure hash (md5/sha1)
    "B610",  # SQL injection (django extra)
    "B611",  # SQL injection (django raw)
    "B701",  # jinja2 autoescape
}
DANGEROUS_EXEC.update({f"B5{n:02d}" for n in range(1, 9)})  # B501..B508
DANGEROUS_EXEC.update({f"B6{n:02d}" for n in range(2, 9)})  # B602..B608

CONTEXT_SENSITIVE = {
    "B104",  # bind to 0.0.0.0
    "B105",  # hardcoded password (string)
    "B106",  # hardcoded password (function arg)
    "B107",  # hardcoded password (default arg)
    "B108",  # hardcoded /tmp
}

BLOCKED = DANGEROUS_EXEC | CONTEXT_SENSITIVE


def truncate(s: str, n: int = 80) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("summary blocked=0 fixable=0 total=0")
        return 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid bandit JSON: {e}", file=sys.stderr)
        return 1
    results = data.get("results", []) if isinstance(data, dict) else []

    blocked = 0
    fixable = 0
    lines: list[str] = []
    for r in results:
        code = r.get("test_id") or ""
        sev = (r.get("issue_severity") or "?")[:3].upper()
        conf = (r.get("issue_confidence") or "?")[:3].upper()
        path = r.get("filename") or ""
        line = r.get("line_number") or "?"
        msg = r.get("issue_text") or ""
        cls = "BLOCKED" if code in BLOCKED else "FIXABLE"
        if cls == "BLOCKED":
            blocked += 1
        else:
            fixable += 1
        lines.append(
            f"[{sev}/{conf}] [{cls:7}] {path}:{line} {code} {truncate(msg)}"
        )

    print(f"summary blocked={blocked} fixable={fixable} total={len(results)}")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
