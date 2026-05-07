---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git commit:*), Bash(git log:*)
description: Create a Conventional Commit on staged changes (English, no preamble)
disable-model-invocation: true
---

# /bt-ai:commit

## Context

- Repo state: !`git status --porcelain=v1`
- Staged stat: !`git diff --cached --stat`
- Staged diff: !`git diff --cached`
- Recent subjects: !`git log -5 --pretty=format:"%s"`

## Your task

Create a single Conventional Commit on the staged changes. Output the resulting `<short-hash> <subject>` on a single line. Do all of this in one message — multiple tool calls in one turn — with no narration.

### Guards

- If `git status --porcelain=v1` shows nothing staged → output `Nothing staged to commit.` Stop.
- If not in a git repository → output `Not a git repository.` Stop.

### Compose

ONE Conventional Commit message in English:
- Format: `<type>(<scope>)?: <subject>`
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- Subject ≤ 72 chars, imperative mood, no trailing period
- Body (only when warranted) wrapped at 100 chars
- No `Co-Authored-By` footer unless the user explicitly asks for it

### Commit

```
git commit -m "$(cat <<'EOF'
<message>
EOF
)"
```

Then capture and emit the result:

```
git log -1 --pretty=format:"%h %s"
```

### Hard rules

- **Never use `--no-verify`** or `--amend` to bypass hooks. If a pre-commit hook rejects the commit, surface the failure verbatim and stop.
- **Never `git add` files the user did not stage.** Only the existing staged tree is committed.
- **Single message.** You have the capability to call multiple tools in a single response. You MUST compose and commit in one message. Do not send any other text besides the tool calls and the final `<hash> <subject>` line.
