---
name: doc-sync
description: "Synchronise les docs FR dans docs/ avec les changements de code (git diff). Remplit les placeholders {{...}} au premier passage. Fan-out parallèle (un sous-agent par doc, en simultané). Le parent met à jour index.md §2 inline."
disable-model-invocation: true
allowed-tools: Bash(python:*), Bash(git diff:*), Bash(git ls-files:*), Bash(git add:*), Bash(git status:*), Bash(git rev-parse:*), Bash(grep:*), Bash(test:*), Bash(date:*), Read, Glob, Edit, MultiEdit
---

# /starter:doc-sync

## Context

- Diff stat (tracked changes): !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --stat --cap 50 '*.py' 'pyproject.toml' '*.md' 2>/dev/null`
- Untracked files: !`git ls-files --others --exclude-standard -- '*.py' 'pyproject.toml' '*.md' 2>/dev/null | head -20`
- Diff (capped at 500 lines, includes untracked as new-file hunks): !`python "${CLAUDE_PLUGIN_ROOT}/tools/git_diff_combined.py" --include-untracked --cap 500 '*.py' 'pyproject.toml' 2>/dev/null`
- Docs with placeholders (template-fill candidates): !`grep -l -E '\{\{[^}]+\}\}|À compléter|Phrase unique' docs/*.md 2>/dev/null || true`
- docs/ exists: !`test -d docs && echo yes || echo no`
- Today's date: !`date +%Y-%m-%d 2>/dev/null`

## Your task

Detect mode (template-fill or diff-patch), fan out **N parallel `doc-patcher` subagents** (one per impacted doc), wait for all results, then update `docs/index.md` §2 freshness table inline. Stage all patched files.

### Guards

1. `docs/ exists` is `no` → output `docs/ folder absent. Run /starter:proj-init first.` Stop.
2. Diff stat is empty AND "Docs with placeholders" is empty → output `No code changes detected. Docs unchanged.` Stop with success.

If diff stat is empty BUT placeholder docs exist, that's **template-fill mode** (first authoring after proj-init). Continue.

### Mode detection

- If `Docs with placeholders` is non-empty → `mode = "template-fill"`. Targets = all 5 non-index docs that exist under `docs/`: `glossaire.md`, `data-model.md`, `contracts.md`, `fonctionnel.md`, `architecture.md`.
- Else → `mode = "diff-patch"`. Classify the diff against the routing rules below; targets = subset of the 5 whose rule fires. If unsure for a given doc, **include it** (fan-out is cheap; the subagent returns quickly if there's no relevant change).

#### Routing rules (diff-patch only)

| Doc | Fires when the diff shows… |
|---|---|
| `glossaire.md` | new business term, acronym, domain concept |
| `data-model.md` | class definitions, dataclass fields, schema changes, entity relationships |
| `contracts.md` | new endpoint, route, public method, event signature, API contract |
| `fonctionnel.md` | user-visible behavior, business rule, use case |
| `architecture.md` | new module/service, dependency added in pyproject, infrastructure change |

If `targets` is empty in diff-patch mode → output `No code changes detected. Docs unchanged.` Stop with success.

### Fan-out (parallel)

**Issue ALL `Task` calls in a single message** — this is the parallelism that delivers the speedup. For N targets, that's N `Task` tool calls in the same response, not one after another.

Each `Task` call invokes subagent `doc-patcher` with this JSON:

```json
{
  "target_doc": "docs/<one-of-the-5>.md",
  "mode": "<template-fill or diff-patch>",
  "diff": "<full diff text from Context above, may be empty in template-fill mode>",
  "scope": "<the routing-rule string for this doc, copied from the table above>",
  "docs_path": "docs/"
}
```

Wait for all subagents to return. Each returns:

```json
{"patched": ["docs/X.md"], "skipped": [...], "summary": "..."}
```

Aggregate:
- `all_patched` = flat union of every `patched` list across all subagents
- `all_skipped` = flat union of every `skipped` list

### Update index.md §2 inline

If `all_patched` is non-empty, the parent updates `docs/index.md` §2 freshness table directly via `MultiEdit`:

1. `Read` `docs/index.md`.
2. For each file in `all_patched`, locate its row in the §2 table (e.g., `| [architecture.md](architecture.md) | ... | ... | ... | ... |`).
3. Build a single `MultiEdit` call with one entry per patched doc, each replacing the row's date column with today's date (from Context above) and status with `Brouillon`. Leave PR and Owner columns unchanged unless they contain `{{...}}` placeholders, in which case replace with `—`.
4. Also update the header row "Dernière mise à jour" with today's date if it still contains a placeholder.

If `index.md` itself was in `placeholder_docs` and template-fill mode is active, the parent's `MultiEdit` should also fill the document title and tagline placeholders (`{{NOM_PROJET}}`, etc.) inline — read `pyproject.toml` for the project name. This is the only doc the parent edits content-wise; everything else is owned by subagents.

Append `docs/index.md` to `all_patched`.

### Stage and summarize

For each file in `all_patched`, run:

```
git add -- "<file>"
```

Output a single line:

- `all_patched` empty AND `all_skipped` empty → `No doc updates needed.`
- `all_skipped` empty → `Patched N docs in parallel: <comma-list>.`
- `all_skipped` non-empty → `Patched N docs: <list>. Skipped M: <comma-list of reasons>.`
- `all_patched` empty AND `all_skipped` non-empty → `No doc updates applied. M skipped: <reasons>.`

### Hard rules

- **Fan-out parallèle**: les N appels `Task` partent dans **un seul message** du parent. Sériels = pénalité de 5-10× sur le wall-clock. Si tu n'es pas sûr, fais le tous d'un coup et oublie l'optimisation fine.
- **Le parent édite UNIQUEMENT `index.md`.** Tous les autres docs sont édités par les subagents `doc-patcher`. Pas d'exception.
- **Pas d'AskUserQuestion.** L'utilisateur revoit via `git diff` avant commit.
- **Pas de scripts helper** dans le repo de l'utilisateur.
