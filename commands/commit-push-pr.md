---
allowed-tools: Bash(git checkout:*), Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git push:*), Bash(git commit:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git branch:*), Bash(test:*), Bash(cat:*), Bash(rm:*), Bash(gh pr create:*), Bash(gh repo view:*), Bash(gh auth status:*)
description: Commit, push, and open a PR with a French body. Re-uses .git/COMMIT_EDITMSG if present.
disable-model-invocation: true
---

# /bt-ai:commit-push-pr

Repo state: !`git status --porcelain=v1`
Branch: !`git rev-parse --abbrev-ref HEAD`
Default branch: !`gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo "main"`
GH auth: !`gh auth status 2>&1 | head -3`
Staged diff stat: !`git diff --cached --stat`
Staged diff: !`git diff --cached`
Pre-validated commit message (if /bt-ai:preflight ran): !`test -s .git/COMMIT_EDITMSG && cat .git/COMMIT_EDITMSG || echo "<none>"`

## Operating mode

**Silent.** No "Now I will commit..." narration. Output the PR URL on success.

## Logic

### Pre-flight

1. If not a git repository → `Not a git repository.` exit non-zero.
2. If `gh auth status` shows not authenticated → `gh auth required: run gh auth login.` exit non-zero.
3. If nothing staged AND nothing unstaged → `Nothing to commit.` exit 0.
4. If something is unstaged but not staged → `Unstaged changes detected. Stage them first or run /bt-ai:preflight.` exit non-zero.

### Step 1 — Branch handling

If current branch equals default branch:

1. Determine a `<type>/<short-slug>` from the staged diff:
   - `<type>` from Conventional Commit type (feat/fix/docs/refactor/test/chore/...) inferred from diff.
   - `<slug>` = up to 5 words, kebab-case, lowercase, derived from the dominant change.
2. `!git checkout -b <type>/<slug>`. If branch already exists, append `-2`, `-3`, ...

### Step 2 — Commit message

If `.git/COMMIT_EDITMSG` exists and is non-empty (preflight wrote it) → use:

```
!git commit -F .git/COMMIT_EDITMSG
```

Then `!rm -f .git/COMMIT_EDITMSG` to avoid stale reuse.

Else compose a Conventional Commit (English) from the staged diff and commit via heredoc:

```
!git commit -m "$(cat <<'EOF'
<type>(<scope>?): <subject>

<optional body wrapped at 100>
EOF
)"
```

### Step 3 — Push

```
!git push -u origin "$(git rev-parse --abbrev-ref HEAD)" 2>&1 | tail -10
```

If push fails (e.g., diverged), surface the failure and exit non-zero. Do not force-push.

### Step 4 — Open PR

Compose PR title = commit subject.

PR body in **French**, three sections:

```
## Contexte

<une à trois phrases : pourquoi ce changement>

## Changements

- <changement 1>
- <changement 2>
- ...

## Plan de test

- [ ] <comment vérifier>
- [ ] <autre vérification>
```

Run via heredoc:

```
!gh pr create --title "<title>" --body "$(cat <<'EOF'
## Contexte
...

## Changements
- ...

## Plan de test
- [ ] ...
EOF
)"
```

Capture the PR URL from gh's stdout (last line of output is the URL).

## Output

Single line, no preamble:

```
<PR URL>
```

## Edge cases

- gh not authenticated → exit non-zero with `gh auth required: run gh auth login.`.
- Push to default branch attempted → step 1 prevented this; if somehow reached, refuse and exit non-zero.
- `.git/COMMIT_EDITMSG` exists from a previous failed run → still use it (it represents the last validated message); always `rm -f` after consuming.
- Pre-commit hook rejects → surface error, do NOT use `--no-verify`.
- PR already exists for branch → gh fails with "already exists"; surface that URL by extracting it from gh's error message and exit 0.
