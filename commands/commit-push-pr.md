---
allowed-tools: Bash(git checkout:*), Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git push:*), Bash(git commit:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git branch:*), Bash(test:*), Bash(cat:*), Bash(rm:*), Bash(gh pr create:*), Bash(gh repo view:*), Bash(gh auth status:*)
description: Commit, push, and open a PR (English title, French body)
disable-model-invocation: true
---

# /bt-ai:commit-push-pr

## Context

- Repo state: !`git status --porcelain=v1 2>/dev/null || echo "<not-a-repo>"`
- Branch: !`git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "<not-a-repo>"`
- Default branch: !`gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main`
- GH auth: !`gh auth status >/dev/null 2>&1 && echo ok || echo missing`
- Staged stat: !`git diff --cached --stat 2>/dev/null || true`
- Staged diff: !`git diff --cached 2>/dev/null || true`
- Recent subjects: !`git log -5 --pretty=format:"%s" 2>/dev/null || true`
- Pre-validated message (preflight): !`test -s .git/COMMIT_EDITMSG 2>/dev/null && cat .git/COMMIT_EDITMSG || echo "<none>"`

## Your task

Commit the staged changes, push, and open a pull request. Do everything in a single message — multiple tool calls in one turn — with no narration between them.

### Guards (halt before any work)

1. Branch is `<not-a-repo>` → output `Not a git repository.` Stop.
2. GH auth is `missing` → output `gh auth required: run 'gh auth login'.` Stop.
3. Nothing staged AND nothing unstaged → output `Nothing to commit.` Stop.
4. Something is unstaged but nothing staged → output `Unstaged changes detected. Stage them first (git add) or run /bt-ai:preflight.` Stop.

### Step 1 — branch

If Branch equals Default branch:
- Infer Conventional Commit `<type>` (feat/fix/docs/refactor/test/chore/perf/build/ci/style/revert) from the staged diff. Pick the dominant intent.
- Build `<slug>` from the diff: ≤ 5 words, lowercase, kebab-case, no stop words.
- Run `git checkout -b <type>/<slug>`. If that name already exists locally, append `-2`, `-3`, … until unique.

If Branch is already a feature branch, skip step 1.

### Step 2 — commit

If Pre-validated message is not `<none>`:
- Use it: `git commit -F .git/COMMIT_EDITMSG`
- Then `rm -f .git/COMMIT_EDITMSG` so it cannot leak into a later run.

Else compose ONE Conventional Commit message in English from the staged diff:
- `<type>(<scope>)?: <subject>` where subject is ≤ 72 chars, imperative mood, no trailing period.
- Optional body wrapped at 100 chars only when the diff genuinely warrants context.
- No `Co-Authored-By` footer unless explicitly requested.

Commit via heredoc to preserve formatting:

```
git commit -m "$(cat <<'EOF'
<message>
EOF
)"
```

### Step 3 — push

```
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
```

### Step 4 — open PR

Title = the commit subject. Body in **French**, three sections:

```
## Contexte

<une à trois phrases : pourquoi ce changement>

## Changements

- <changement 1>
- <changement 2>

## Plan de test

- [ ] <comment vérifier>
- [ ] <autre vérification>
```

Run via heredoc:

```
gh pr create --title "<title>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

The output of `gh pr create` is the PR URL on the last line — that is the only thing you emit to the user. Print it on its own line, no preamble.

### Hard rules

- **Never force-push.** No `--force`, no `--force-with-lease`. If `git push` fails with a diverged-history error, surface the error verbatim and stop. The user resolves manually.
- **Never push to the default branch.** Step 1 prevents this; if you somehow find yourself on the default branch after step 1, stop and surface the failure.
- **Never skip hooks.** No `--no-verify`, no `--no-gpg-sign`. If a pre-commit/pre-push hook fails, surface its output verbatim and stop.
- **Do not invent PR URLs.** Only emit the URL `gh pr create` actually returned. If it failed with "a pull request for branch already exists", parse the existing URL out of the error and emit that instead.
- **Single message.** You have the capability to call multiple tools in a single response. You MUST do steps 1-4 (whichever apply) in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls and the final PR URL (or halt line).
