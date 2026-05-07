---
name: preflight
description: Suite de validation pré-PR. Enchaîne check-style, security, gen-tests, pytest, doc-sync, readme-sync, gitlint, puis commit-push-pr. Silencieux sur le chemin heureux.
disable-model-invocation: true
allowed-tools: Bash(git status:*), Bash(git rev-parse:*), Bash(git diff:*), Bash(git branch:*), Bash(gh repo view:*), Bash(gh auth status:*), Bash(command:*), Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(cat:*), Bash(test:*), Skill, Read
---

# /bt-ai:preflight

## Context

- Repo state: !`git status --porcelain=v1 2>/dev/null || echo "<not-a-repo>"`
- Branch: !`git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "<not-a-repo>"`
- Default branch: !`gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main`
- gh present: !`command -v gh >/dev/null 2>&1 && echo yes || echo no`
- gh auth ok: !`gh auth status >/dev/null 2>&1 && echo yes || echo no`
- Has staged: !`git diff --cached --quiet 2>/dev/null && echo no || echo yes`
- Has unstaged: !`git diff --quiet 2>/dev/null && echo no || echo yes`
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`

## Your task

Run the full pre-PR validation suite and open a PR. Sub-skills handle their own staging via `git add`; preflight never stages on the user's behalf. The only output on success is the PR URL.

### Guards (halt before any work)

1. Branch is `<not-a-repo>` → `Halted: not a git repository.` Stop.
2. Both Has staged and Has unstaged are `no` → `Halted: no changes to validate.` Stop.
3. Has unstaged is `yes` AND Has staged is `no` → `Halted: changes are unstaged. Stage them first (git add).` Stop. Never stage user changes silently.
4. Branch equals Default branch → `Halted: refuse to preflight on the default branch. Create a feature branch first.` Stop.
5. gh present is `no` → `Halted: gh CLI not installed. Install from https://cli.github.com and run 'gh auth login'. For a local-only flow use individual skills (/bt-ai:check-style, /bt-ai:security, /bt-ai:gen-tests, /bt-ai:doc-sync, /bt-ai:readme-sync, /bt-ai:commit).` Stop.
6. gh auth ok is `no` → `Halted: gh not authenticated. Run 'gh auth login' and retry.` Stop.

### Pipeline (sequential, halt on first failure)

Run each step in order. If a step exits non-zero, surface its message verbatim prefixed with `Halted at step <N>:` and stop. Do not narrate between steps.

**Step 1 — check-style.** Invoke `bt-ai:check-style` via the Skill tool. Auto-applies safe ruff fixes; halts only on Critical (`F*`/`E9*`) findings.

**Step 2 — security.** Invoke `bt-ai:security`. Halts only on HIGH/HIGH bandit findings.

**Step 3 — gen-tests.** Invoke `bt-ai:gen-tests` (no arguments → diff mode). Generates tests for changed Python files. Halts on test-collection failure or unresolved semantic failures.

**Step 4 — full pytest.** Run the project's full test suite (not just the freshly generated tests). Replace `<runner>` with the literal Runner value from the Context above:

```
<runner> run pytest -q 2>&1 | tail -30
```

If the exit code is non-zero, output `Halted at step 4: pytest failed.` followed by the captured tail. Stop.

**Step 5 — doc-sync.** Invoke `bt-ai:doc-sync`. Auto-applies clean patches; halts only on apply failure.

**Step 6 — readme-sync.** Invoke `bt-ai:readme-sync`. Auto-applies clean patch.

**Step 7 — commit message gate.** The staged tree now contains the user's original changes plus everything the sub-skills produced. Compose a Conventional Commit message from the staged diff:

1. Read the staged diff (already in Context above; if stale, re-read with `git diff --cached --stat` and `git diff --cached`).
2. Build the message in memory: `<type>(<scope>?): <subject>` plus optional body, English, subject ≤ 72 chars, imperative.
3. Validate via gitlint (`<runner>` = literal Runner from Context):
   ```
   echo "<message>" | <runner> run gitlint --staged --msg-stdin
   ```
4. If gitlint exits non-zero, the user's repo `.gitlint` is rejecting the message. Re-write once based on the rule that fired (gitlint prints which one). If the second attempt also fails, output `Halted at step 7: commit message did not pass gitlint after rewrite.` followed by gitlint's output verbatim. Stop.
5. On success, write the validated message to `.git/COMMIT_EDITMSG`:
   ```
   cat > .git/COMMIT_EDITMSG <<'EOF'
   <validated message>
   EOF
   ```

**Step 8 — commit-push-pr.** Invoke `bt-ai:commit-push-pr` via the Skill tool. It detects the non-empty `.git/COMMIT_EDITMSG` and uses `git commit -F`, then removes the file. The output is the PR URL on a single line.

If step 8 exits non-zero, output `Halted at step 8: commit-push-pr failed.` followed by its stderr. Stop. The `.git/COMMIT_EDITMSG` may remain — `commit-push-pr` clears it on success only.

### Hard rules

- **Never narrate intermediate steps** ("Step 1 starting…", "check-style passed…"). The only output is the final PR URL or the halt line.
- **Never stage user changes silently.** Sub-skills stage what THEY produce; preflight does not call `git add`.
- **Never force-push.** Never push to the default branch (the guard above prevents preflight on the default branch; if a sub-skill somehow ends up pushing to it, halt).
- **Never skip hooks.** No `--no-verify`, no `--no-gpg-sign`. If a hook fails, halt with the hook's message verbatim.
- **Never invent a PR URL.** Only emit the URL `gh pr create` actually returned.

You have the capability to call multiple tools in a single response. Use the Skill tool to invoke each sub-skill, and Bash for steps 4 and 7. Do not send any other text or messages besides these tool calls and the final PR URL (or halt line).
