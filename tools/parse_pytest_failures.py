#!/usr/bin/env python3
"""Parse pytest failure output and classify failures as MECHANICAL vs SEMANTIC.

Reads pytest text output from stdin (use `pytest -q --tb=short` or similar),
emits a JSON payload classifying each failure. The gen-tests verify phase
forwards MECHANICAL failures to the test-fixer agent for autonomous repair
and asks the user about SEMANTIC failures.

Mechanical patterns (auto-fixable by an agent without changing test intent):
  - ImportError / ModuleNotFoundError
  - NameError on imported symbol
  - fixture not found
  - "missing 1 required positional argument" — function signature drift
  - SyntaxError inside a generated test file
  - "TypeError: ... missing required argument"

Semantic patterns (require human judgment — assertion values, mocking
strategy, etc.):
  - AssertionError on value/equality
  - "Failed: DID NOT RAISE"
  - Wrong exception type in pytest.raises
  - Anything else that does not match a mechanical pattern

Output schema:
{
  "passed": int,
  "failed": int,
  "errors": int,
  "mechanical": [
    {"test_id": "tests/foo/test_bar.py::test_x", "kind": "ImportError",
     "detail": "No module named 'foo.bar'"},
    ...
  ],
  "semantic": [
    {"test_id": "...", "kind": "AssertionError", "detail": "..."},
    ...
  ]
}

Usage:
    pytest -q <files> 2>&1 | python parse_pytest_failures.py
"""
from __future__ import annotations

import json
import re
import sys

MECHANICAL_KINDS = {
    "ModuleNotFoundError",
    "ImportError",
    "NameError",
    "fixture-not-found",
    "missing-argument",
    "SyntaxError",
    "AttributeError-import",
}
SEMANTIC_KINDS = {
    "AssertionError",
    "DID-NOT-RAISE",
    "WrongExceptionType",
    "Other",
}

FAILURE_HEADER = re.compile(r"^_+\s+(?P<id>[^\s_].*?)\s+_+\s*$")
SHORT_TEST_SUMMARY = re.compile(r"^=+\s*short test summary info\s*=+\s*$", re.IGNORECASE)
PYTEST_TOTALS = re.compile(
    r"(?:(?P<failed>\d+)\s+failed)?[, ]*"
    r"(?:(?P<passed>\d+)\s+passed)?[, ]*"
    r"(?:(?P<errors>\d+)\s+error)?",
)


def classify_block(block: str) -> tuple[str, str]:
    """Return (kind, detail) for one failure block of pytest output."""
    text = block.lower()

    if "modulenotfounderror" in text:
        m = re.search(r"ModuleNotFoundError: (.+)", block)
        return "ModuleNotFoundError", m.group(1) if m else "module not found"
    if "importerror" in text:
        m = re.search(r"ImportError: (.+)", block)
        return "ImportError", m.group(1) if m else "import failed"
    if "fixture" in text and "not found" in text:
        m = re.search(r"fixture '([^']+)' not found", block)
        return "fixture-not-found", f"fixture '{m.group(1)}' not found" if m else "fixture not found"
    if "missing" in text and "required positional argument" in text:
        m = re.search(r"missing \d+ required positional arguments?: ([^\n]+)", block)
        return "missing-argument", m.group(1).strip() if m else "missing argument"
    if "syntaxerror" in text:
        m = re.search(r"SyntaxError: (.+)", block)
        return "SyntaxError", m.group(1) if m else "syntax error"
    if "nameerror" in text:
        m = re.search(r"NameError: (.+)", block)
        return "NameError", m.group(1) if m else "name not defined"
    if "attributeerror" in text and "module" in text:
        m = re.search(r"AttributeError: (.+)", block)
        return "AttributeError-import", m.group(1) if m else "attribute error on module"
    if "did not raise" in text:
        return "DID-NOT-RAISE", "expected exception was not raised"
    if "but exception type was" in text or "wrong exception type" in text:
        return "WrongExceptionType", "exception type mismatch"
    if "assertionerror" in text:
        m = re.search(r"AssertionError(?::\s*(.+))?", block)
        return "AssertionError", (m.group(1) or "assertion failed") if m else "assertion failed"
    return "Other", "unrecognized failure"


def split_blocks(out: str) -> list[tuple[str, str]]:
    """Split pytest output into (test_id, block_text) pairs.

    Pytest in -v mode emits per-failure separators of underscores around the
    test id; in -q mode it lists FAILED entries in the short summary. We
    parse whichever format is present.
    """
    lines = out.splitlines()
    blocks: list[tuple[str, str]] = []

    # First pass: long-form failure blocks.
    i = 0
    while i < len(lines):
        m = FAILURE_HEADER.match(lines[i])
        if m:
            test_id = m.group("id").strip()
            buf = [lines[i]]
            i += 1
            while i < len(lines) and not (
                FAILURE_HEADER.match(lines[i]) or SHORT_TEST_SUMMARY.match(lines[i])
            ):
                buf.append(lines[i])
                i += 1
            blocks.append((test_id, "\n".join(buf)))
        else:
            i += 1

    # Second pass: short summary lines, only if we didn't catch them above.
    if not blocks:
        for line in lines:
            m = re.match(r"^FAILED\s+(\S+)\s*-?\s*(.*)$", line)
            if m:
                blocks.append((m.group(1), m.group(0)))
            m = re.match(r"^ERROR\s+(\S+)\s*-?\s*(.*)$", line)
            if m:
                blocks.append((m.group(1), m.group(0)))
    return blocks


def main() -> int:
    out = sys.stdin.read()
    if not out.strip():
        print(json.dumps({"passed": 0, "failed": 0, "errors": 0, "mechanical": [], "semantic": []}))
        return 0

    passed = failed = errors = 0
    # Pytest summary line, e.g. "1 failed, 2 passed in 0.01s" or "5 passed in 0.5s"
    for line in reversed(out.splitlines()):
        if " in " in line and ("passed" in line or "failed" in line or "error" in line):
            for kw, varname in [("passed", "passed"), ("failed", "failed"), ("error", "errors")]:
                m = re.search(rf"(\d+)\s+{kw}", line)
                if m:
                    if varname == "passed":
                        passed = int(m.group(1))
                    elif varname == "failed":
                        failed = int(m.group(1))
                    else:
                        errors = int(m.group(1))
            break

    mechanical = []
    semantic = []
    for test_id, block in split_blocks(out):
        kind, detail = classify_block(block)
        item = {"test_id": test_id, "kind": kind, "detail": detail.strip()}
        if kind in MECHANICAL_KINDS:
            mechanical.append(item)
        else:
            semantic.append(item)

    print(json.dumps({
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "mechanical": mechanical,
        "semantic": semantic,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
