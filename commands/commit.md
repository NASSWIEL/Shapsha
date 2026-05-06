---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git commit:*), Bash(git log:*)
description: Create a Conventional Commit on staged changes (English, no preamble)
disable-model-invocation: true
---

# /bt-ai:commit

Repo state: !`git status --porcelain=v1`
Staged diff stat: !`git diff --cached --stat`
Staged diff: !`git diff --cached`
Recent commit subjects (style reference): !`git log -5 --pretty=format:"%s"`

## Operating mode

**Silent.** No "Composing commit message..." narration. Compose, validate, commit. Output one line.

## Logic

1. **Pre-flight**:
   - If `git status --porcelain=v1` shows nothing staged (no `^[MARC]` lines on column 1) → output `Nothing staged to commit.` exit 0.
   - If not in a git repository → output `Not a git repository.` exit non-zero.

2. **Compose** ONE Conventional Commit message in English from the staged diff:
   - Format: `<type>(<scope>)?: <subject>`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
   - Subject ≤ 72 chars, imperative mood, no trailing period
   - Body (optional, only if the diff truly warrants more context): wrap at 100 chars
   - No "Co-Authored-By" footers unless explicitly requested

3. **Commit** using a heredoc to preserve formatting:

   ```
   !git commit -m "$(cat <<'EOF'
   <message>
   EOF
   )"
   ```

4. **Capture** the resulting commit hash and subject:

   ```
   !git log -1 --pretty=format:"%h %s"
   ```

## Output

Single line, no preamble:

```
<short-hash> <subject>
```

If commit fails (hook rejection, etc.), output the failure verbatim and exit non-zero.

## Edge cases

- Pre-commit hook rejects the commit → do NOT use `--no-verify`. Surface the failure and let the user fix the underlying issue.
- Mix of staged + unstaged → only staged is committed (standard git behavior); unstaged remains.
- Empty staged diff but staged file count > 0 (e.g., chmod-only) → still commit; the message should reflect (`chore: update file mode`).
