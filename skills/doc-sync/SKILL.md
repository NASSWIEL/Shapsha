---
name: doc-sync
description: Synchronise les docs FR dans docs/ avec les changements de code (git diff). Remplit les placeholders {{...}} au premier passage. L'agent édite en place ; ce skill ne fait que stager.
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git add:*), Bash(git status:*), Bash(git rev-parse:*), Bash(grep:*), Bash(test:*), Read, Glob
---

# /bt-ai:doc-sync

## Context

- Diff stat (tracked changes): !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --stat --cap 50 '*.py' 'pyproject.toml' '*.md' 2>/dev/null`
- Untracked files: !`git ls-files --others --exclude-standard -- '*.py' 'pyproject.toml' '*.md' 2>/dev/null | head -20`
- Diff (capped at 500 lines, includes untracked as new-file hunks): !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --cap 500 '*.py' 'pyproject.toml' 2>/dev/null`
- Docs with placeholders (template-fill candidates): !`grep -l -E '\{\{[^}]+\}\}|À compléter|Phrase unique' docs/*.md 2>/dev/null || true`
- docs/ exists: !`test -d docs && echo yes || echo no`

## Your task

Delegate to the `doc-patcher` subagent, which edits docs in place. This skill never applies diffs and never edits docs itself — it only delegates and stages.

### Guards

1. `docs/ exists` is `no` → output `docs/ folder absent. Run /bt-ai:proj-init first.` Stop.
2. Diff stat is empty AND "Docs with placeholders" is empty → output `No code changes detected. Docs unchanged.` Stop with success.

If diff stat is empty BUT placeholder docs exist, that's **template-fill mode** (first authoring after proj-init). Continue.

### Delegate to doc-patcher

Invoke `Task` with subagent `doc-patcher`. Pass JSON:

```json
{
  "diff": "<full diff text from Context above>",
  "docs_path": "docs/",
  "placeholder_docs": ["<paths from 'Docs with placeholders' line, or empty list>"],
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

The agent edits docs in place via `Edit`/`MultiEdit` and returns:

```json
{
  "patched": ["docs/data-model.md", "docs/index.md"],
  "skipped": [{"file": "docs/architecture.md", "reason": "drift too large; needs human"}],
  "summary": "Added entity Foo with fields a, b, c."
}
```

### Stage and summarize

For each file in `patched`:

```
git add -- "<file>"
```

Then output a single line:

- `patched` empty AND `skipped` empty → `No doc updates needed.`
- `skipped` empty → `Patched N docs: <comma-list>.`
- `skipped` non-empty → `Patched N docs: <list>. Skipped M: <comma-list of reasons>.`
- `patched` empty AND `skipped` non-empty → `No doc updates applied. M skipped: <reasons>.`

Stop with success unless the agent itself reported a halt condition.

### Hard rules

- **Do not edit docs yourself.** The agent owns all doc edits. This skill only stages.
- **Do not parse or apply unified diffs.** The old contract (subagent returns diffs, parent applies) is gone. The agent edits in place via Edit/MultiEdit.
- **Do not write helper scripts** into the user's repo. If anything fails, surface the agent's reason verbatim.
- **No AskUserQuestion.** The user reviews via `git diff` before commit.
- **Single message.** Delegate + stage + summary in one tool-call turn.
