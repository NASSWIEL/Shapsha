---
name: doc-sync
description: Sync French docs in docs/ with code changes from git diff. Subagent reads only impacted templates per their MODE D'EMPLOI section.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Edit
---

# /bt-ai:doc-sync

Diff stat (tracked changes): !`{ git diff --stat -- '*.py' 'pyproject.toml' '*.md' 2>/dev/null; git diff --cached --stat -- '*.py' 'pyproject.toml' '*.md' 2>/dev/null; } | head -50`
Untracked files: !`git ls-files --others --exclude-standard -- '*.py' 'pyproject.toml' '*.md' 2>/dev/null | head -20`
Diff (capped at 500 lines, includes untracked as new-file hunks): !`{ git diff -- '*.py' 'pyproject.toml' 2>/dev/null; git diff --cached -- '*.py' 'pyproject.toml' 2>/dev/null; for f in $(git ls-files --others --exclude-standard -- '*.py' 'pyproject.toml' 2>/dev/null); do [ -f "$f" ] && { echo "=== NEW FILE: $f ==="; cat "$f"; echo; }; done; } | head -500`

## Operating mode

**Silent.** No "Reading docs..." narration. Delegate to `doc-patcher` agent (which has its own context — reading 6 docs there does not pollute parent), then apply patches via parent's `Edit` tool only with user approval.

## Logic

### Pre-flight

1. If diff stat is empty (no changes in `*.py`, `pyproject.toml`, or `*.md`) → output `No code changes detected. Docs unchanged.` exit 0.
2. If `docs/` folder is absent → output `docs/ folder absent. Run /bt-ai:proj-init first.` exit non-zero.
3. If not a git repository → output `Not a git repository.` exit non-zero.

### Delegate to doc-patcher

Invoke `Task` with agent `doc-patcher`. Pass JSON:

```json
{
  "diff": "<full text from above, capped at 500 lines>",
  "docs_path": "docs/",
  "routing": {
    "data-model.md": "class definitions, dataclass fields, schema changes, entity relationships",
    "contracts.md": "new endpoint, route, public method, event signature, API contract",
    "architecture.md": "new module/service, dependency added in pyproject, infrastructure change",
    "glossaire.md": "new business term, acronym, domain concept",
    "fonctionnel.md": "user-visible behavior, business rule, use case",
    "index.md": "always update §2 (freshness table) for any other doc patched"
  }
}
```

Wait for agent's structured JSON return:

```json
{
  "patches": [{"file": "docs/data-model.md", "patch": "<unified diff>", "summary": "..."}, ...],
  "skipped": [{"file": "docs/architecture.md", "reason": "..."}]
}
```

### Branch on agent response

- **`patches` empty AND `skipped` empty** → output `No doc updates needed.` exit 0.
- **`patches` non-empty** → continue to ask user.
- **`skipped` non-empty** → include the skip reasons in the final report regardless.

### Print proposed patches

For each patch entry, print one line:

```
<file>: <summary>
```

If any `skipped` entries exist, print also:

```
SKIPPED <file>: <reason>
```

### Ask user

AskUserQuestion with three options:

- `a` — Apply all proposed patches
- `s` — Show full diffs first (print each patch verbatim, then re-ask `apply / cancel`)
- `n` — Skip; do not apply

### Apply

If user picks `a` (or `apply` after `s`), for each patch:

- Use `Edit` to apply the unified diff. If a hunk does not apply cleanly, output `Patch failed for <file>:` followed by the patch text, and continue to the next file (do not abort all).
- After all successful patches, stage them so preflight and follow-up commits see them:
  ```
  !for f in <successfully patched files>; do git add -- "$f"; done
  ```

### Skip handling

If user picks `n`, do not apply anything. Exit 0.

## Output

Single line, no preamble:

```
Patched N docs: <comma-list>.
```

Or:

```
No doc updates needed.
```

Or:

```
Patched N docs: <list>. Skipped M: <list>.
```

Exit non-zero if any patch failed to apply (so `/preflight` can halt).

## Edge cases

- Diff > 500 lines → already capped; subagent works on the head.
- Existing doc has placeholders `{{...}}` → agent should fill only the impacted section, leave other placeholders intact.
- Agent proposes a patch that doesn't apply cleanly → print as text under `Patch failed`, exit non-zero so `/preflight` halts. User merges manually.
- All 6 docs need rewriting (drift > 30%) → agent returns mostly `skipped` with reason `drift too large`. Surface this; do not attempt mass rewrite.
- `pyproject.toml` only diff (no `*.py` changes) → still process; may impact `architecture.md` (deps).
