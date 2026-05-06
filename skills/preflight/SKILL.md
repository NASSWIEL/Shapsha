---
name: preflight
description: Pre-PR validation suite. Runs check-style, security, gen-tests, pytest, doc-sync, readme-sync, gitlint gate, then commit-push-pr.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:preflight

Runner: !`python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv`
Repo state: !`git status --porcelain=v1`
Branch: !`git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "<not-a-repo>"`
Default branch: !`gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo "main"`
GH auth: !`gh auth status 2>&1 | head -1`
Has staged: !`git diff --cached --quiet 2>/dev/null && echo "no" || echo "yes"`
Has unstaged: !`git diff --quiet 2>/dev/null && echo "no" || echo "yes"`

## Operating mode

**Sequential, halt-on-failure.** Each step either passes silently or halts with a one-line reason. Sub-skills run their own interactive prompts; their non-zero exits halt preflight.

**Runner**: shell calls that run Python tools (pytest, gitlint) resolve the runner with `R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv);` then invoke `$R run <tool>`. Dispatches to `uv run` or `poetry run` as set by `/bt-ai:proj-init`.

## Logic

### Guard

1. If branch shows `<not-a-repo>` → output `Halted at guard: not a git repository.` exit non-zero.
2. If `Has staged` is `no` AND `Has unstaged` is `no` → output `Halted at guard: no changes to validate.` exit non-zero.
3. If `Has unstaged` is `yes` AND `Has staged` is `no` → stage user changes? No — refuse and instruct: output `Halted at guard: changes are unstaged. Stage them first (git add).` exit non-zero. (Reason: preflight should not silently `git add` user changes; user controls staging.)

### Step 1 — check-style

Invoke skill `bt-ai:check-style`. The skill itself handles user prompts for fix/skip on Critical+High findings.

If the skill exits non-zero (i.e., Critical or High findings remain unresolved) → output `Halted at step 1: critical/high style findings unresolved.` exit non-zero.

### Step 2 — security

Invoke skill `bt-ai:security`. Skill handles user prompts and FIXABLE/BLOCKED classification.

If non-zero exit (BLOCKED findings remain or user skipped FIXABLE-and-now-blocked) → output `Halted at step 2: security findings require manual fix.` exit non-zero.

### Step 3 — gen-tests (diff mode)

Invoke skill `bt-ai:gen-tests` (no arguments → diff mode).

If non-zero (subagent failure or pytest collection failure on generated tests) → output `Halted at step 3: gen-tests failed.` followed by the skill's error verbatim. Exit non-zero.

If zero exit, continue. "All changed files already have tests" is a valid pass.

### Step 4 — pytest

```
!R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv); $R run pytest -q 2>&1 | tail -30
```

If exit non-zero → output `Halted at step 4: pytest failed.` followed by the captured tail. Exit non-zero.

### Step 5 — doc-sync

Invoke skill `bt-ai:doc-sync`. Skill handles user prompts for `[a]/[s]/[n]`.

If non-zero exit (user declined patches OR a patch failed to apply) → output `Halted at step 5: docs out of sync.` exit non-zero.

If zero exit, continue. "No doc updates needed" is a valid pass.

### Step 6 — readme-sync

Invoke skill `bt-ai:readme-sync`. Skill handles user prompts.

If non-zero → output `Halted at step 6: README out of sync.` exit non-zero.

### Step 7 — commit message gate

1. Stage what is currently unstaged in tracked files:
   - We are NOT calling `git add` here — preflight requires staged content from the start (see Guard step 3). At this step, all changes the user wants in the commit are already staged.
2. Compose a Conventional Commit message (English) from the staged diff:

   ```
   !git diff --cached --stat
   !git diff --cached
   ```

   Build the message in memory: `<type>(<scope>?): <subject>` plus optional body.
3. Validate via gitlint:

   ```
   !R=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb')).get('tool',{}).get('bt-ai',{}).get('runner','uv'))" 2>/dev/null || echo uv); echo "<message>" | $R run gitlint --staged --msg-stdin 2>&1
   ```

   Exit code 0 = valid. Non-zero = rule violation; gitlint prints the rule that failed.

4. **On failure**: print the gitlint output verbatim. Use AskUserQuestion to ask the user to provide a corrected message (single text field). Re-validate.

5. **On second failure**: output `Halted at step 7: commit message did not pass gitlint after rewrite.` exit non-zero.

6. **On success**: write the validated message to `.git/COMMIT_EDITMSG`:

   ```
   !cat > .git/COMMIT_EDITMSG <<'EOF'
   <validated message>
   EOF
   ```

### Step 8 — commit, push, PR

Invoke slash command `/bt-ai:commit-push-pr`. It will detect the non-empty `.git/COMMIT_EDITMSG` and use it via `git commit -F`, then `rm -f` it.

If non-zero exit → output `Halted at step 8: commit-push-pr failed.` followed by the skill's stderr. Exit non-zero. The `.git/COMMIT_EDITMSG` may remain — `commit-push-pr` clears it on success only.

## Output

On success: the PR URL (passed through from `commit-push-pr`).

On halt: single line `Halted at step <N>: <reason>.` followed by the failure detail (verbatim from the failing tool).

No preamble. No "Step 1 starting..." narration between steps.

## Edge cases

- Step 1-6 user picks `[n]` (skip) on a sub-skill prompt → that skill exits non-zero → preflight halts at that step. This is correct: declining means changes are unresolved.
- `.git/COMMIT_EDITMSG` already exists (stale from prior run) → we overwrite at step 7; commit-push-pr clears it after consumption.
- Step 4 pytest collection passes but tests fail → halt at step 4 with full failure tail.
- gh not authenticated → halt at step 8 with `gh auth required` from commit-push-pr.
- User on default branch → step 8 (commit-push-pr) creates a `<type>/<slug>` branch automatically.
- All steps pass but user has nothing committed (impossible given guards) → fail-safe error at step 8.
- Step 7 user provides empty corrected message → treat as second failure and halt.
