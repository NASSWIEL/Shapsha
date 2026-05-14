---
name: preflight
description: "Pipeline pré-PR complet : check-style → security → gen-tests → pytest → doc-sync → readme-sync → commit-push-pr."
disable-model-invocation: true
allowed-tools: Bash(git status:*), Bash(git rev-parse:*), Bash(git diff:*), Bash(git branch:*), Bash(gh repo view:*), Bash(gh auth status:*), Bash(command:*), Bash(python:*), Bash(uv:*), Bash(poetry:*), Bash(cat:*), Bash(test:*), Skill, Read
---

# /starter:preflight

## Context

- Repo state: !`git status --porcelain=v1 2>/dev/null || echo "<not-a-repo>"`
- Branch: !`git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "<not-a-repo>"`
- Default branch: !`gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main`
- gh present: !`command -v gh >/dev/null 2>&1 && echo yes || echo no`
- gh auth ok: !`gh auth status >/dev/null 2>&1 && echo yes || echo no`
- Has staged: !`git diff --cached --quiet 2>/dev/null && echo no || echo yes`
- Has unstaged: !`git diff --quiet 2>/dev/null && echo no || echo yes`
- Runner: !`python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py" 2>/dev/null || echo uv`

## Output format

Every step is wrapped in a large separator block. Before every Bash command, output one plain sentence describing what you are about to do. Between sub-actions inside the same step, use a small separator.

**Large separator (between steps):**
```
===============================================================
  Step <N> — <step name>
===============================================================
```

**Small separator (between sub-actions within a step):**
```
----------------------------
```

**Before every Bash command**, output one sentence in the form:
> "I want to <verb phrase> so that <reason>."

Example:
> "I want to run the full test suite to verify no regressions were introduced by the current changes."

On **halt**, output the halt line immediately after the large separator of the failing step — no additional decorators needed.

On **success**, close the last step with a large separator, then output the PR URL on its own line.

## Your task

Run the full pre-PR validation suite and open a PR. Sub-skills handle their own staging via `git add`; preflight stages the user's initial changes when needed (guard #3).

### Guards (halt before any work)

1. **GitHub auth check (run first, before anything else).** If gh present is `no` OR gh auth ok is `no` → output exactly the message below and stop. Do not prefix with `Halted` or any other word — just print the message verbatim on its own line, then stop:
   ```
   Tu n'es pas encore connecté à une instance GitHub. Le pipeline preflight a besoin d'une session `gh` authentifiée pour aller jusqu'à la création de la pull request. Connecte-toi avec `gh auth login`, puis relance la commande — je reprendrai alors toutes les étapes (check-style, security, tests, doc-sync, readme-sync, commit, push, PR).
   ```
   If `gh` is not installed at all, append on a second line:
   ```
   Ouvre un nouveau terminal, installe `gh` depuis https://cli.github.com, puis fais `gh auth login`.
   ```
   Stop. Do not run any subsequent guard or step.
2. Branch is `<not-a-repo>` → `Halted: not a git repository.` Stop.
3. Both Has staged and Has unstaged are `no` → `Halted: no changes to validate.` Stop.
4. Has unstaged is `yes` AND Has staged is `no` → all guards passed; silently stage changes before proceeding. Stage tracked modifications (`git add -u`) plus untracked source/config files (`.py`, `.md`, `pyproject.toml`) — nothing else. Scratch files, compiled outputs, and anything else untracked are left unstaged:
   ```
   python -c "
   import subprocess
   subprocess.run(['git', 'add', '-u'])
   r = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '--', '*.py', '*.md', 'pyproject.toml'], capture_output=True, text=True)
   files = [f for f in r.stdout.splitlines() if f]
   if files:
       subprocess.run(['git', 'add', '--'] + files)
   " 2>/dev/null || true
   ```
   Do not halt. Do not output any message. Continue to the pipeline.

**Branch on default branch**: if `Branch` equals `Default branch`, **do not halt**. The Step 8 sub-skill (`starter:commit-push-pr`) auto-creates a feature branch named from the staged diff (Conventional Commit type + ≤5-word slug). Continue to the pipeline as usual.

### Pipeline (sequential, halt on first failure)

Run each step in order. Before invoking each step, print its large separator block. If a step exits non-zero, surface its message verbatim prefixed with `Halted at step <N>:` and stop.

---

**Step 1 — check-style**

Output before invoking:
```
===============================================================
  Step 1 — check-style
===============================================================
```
Invoke `starter:check-style` via the Skill tool. Two-pass: ruff fixes everything it can, then model fixes remaining. Never halts.

---

**Step 2 — security**

Output before invoking:
```
===============================================================
  Step 2 — security
===============================================================
```
Invoke `starter:security`. Scans all severity levels (bandit + LLM analysis), proposes fixes for every finding, asks consent once. Halts on user decline or if findings remain after fixes.

---

**Step 3 — gen-tests**

Output before invoking:
```
===============================================================
  Step 3 — gen-tests
===============================================================
```
Invoke `starter:gen-tests` (no arguments → diff mode). Generates tests for changed Python files. Halts on test-collection failure or unresolved semantic failures.

---

**Step 4 — full pytest**

Output before invoking:
```
===============================================================
  Step 4 — full pytest
===============================================================
```
Output the narration sentence, then run the command. Replace `<runner>` with the literal Runner value from the Context above:

> "I want to run the full test suite to verify that no existing tests were broken by the changes applied in the previous steps."

```
<runner> run pytest -q 2>&1 | tail -30
```

If the exit code is non-zero, output `Halted at step 4: pytest failed.` followed by the captured tail. Stop.

---

**Step 5 — doc-sync**

Output before invoking:
```
===============================================================
  Step 5 — doc-sync
===============================================================
```
Invoke `starter:doc-sync`. Auto-patches the French docs in `docs/` from the git diff. Halts only on apply failure.

---

**Step 6 — readme-sync**

Output before invoking:
```
===============================================================
  Step 6 — readme-sync
===============================================================
```
Invoke `starter:readme-sync`. Auto-patches `README.md` if user-facing surfaces changed. No-ops silently if nothing changed.

---

**Step 7 — commit message**

Output before starting:
```
===============================================================
  Step 7 — commit message
===============================================================
```

The staged tree now contains the user's original changes plus everything the sub-skills produced. Compose and validate the commit message:

0. Remove any stale `.git/COMMIT_EDITMSG` left over from a previous failed run — this ensures commit-push-pr always gets a freshly composed message, never a leftover:
   > "I want to remove any stale commit message file from a previous failed attempt to ensure a clean start."
   ```
   rm -f .git/COMMIT_EDITMSG 2>/dev/null || true
   ```

1. Output the narration sentence, then read the staged diff (re-read if the initial Context is stale):
   > "I want to inspect the full staged diff to compose an accurate Conventional Commit message covering all changes made during this pipeline."
   ```
   git diff --cached --stat
   git diff --cached
   ```

2. Build the message in memory: `<type>(<scope>?): <subject>` plus optional body, English, subject ≤ 72 chars, imperative.

3. Output the small separator, then the narration sentence, then validate via gitlint:
   ```
   ----------------------------
   ```
   > "I want to validate the commit message against the project's gitlint rules before committing."
   ```
   echo "<message>" | <runner> run gitlint --staged --msg-stdin
   ```
   If gitlint exits non-zero, rewrite once based on the rule that fired. If the second attempt also fails, output `Halted at step 7: commit message did not pass gitlint after rewrite.` followed by gitlint's output verbatim. Stop.

4. Output the small separator, then the narration sentence, then write the validated message:
   ```
   ----------------------------
   ```
   > "I want to save the validated commit message to `.git/COMMIT_EDITMSG` so that the commit-push-pr step can use it directly."
   ```
   cat > .git/COMMIT_EDITMSG <<'EOF'
   <validated message>
   EOF
   ```

---

**Step 8 — commit, push, PR**

Output before invoking:
```
===============================================================
  Step 8 — commit · push · PR
===============================================================
```
Invoke `starter:commit-push-pr` via the Skill tool. It detects the non-empty `.git/COMMIT_EDITMSG` and uses `git commit -F`, then removes the file, pushes, and opens the PR.

If step 8 exits non-zero, clean up the commit message file before halting so a retry starts fresh:
```
rm -f .git/COMMIT_EDITMSG 2>/dev/null || true
```
Then output `Halted at step 8: commit-push-pr failed.` followed by its stderr. Stop.

On success, output:
```
===============================================================
```
Then the PR URL on its own line.

### Hard rules

- **Structured output required.** Print the large separator block before every step. Print the small separator + one narration sentence before every Bash command within a step. These are mandatory — not optional.
- **Auto-stage when needed.** If all changes are unstaged at entry, preflight runs `git add -A` silently before the pipeline. Sub-skills stage what THEY produce during the pipeline.
- **Never force-push.** Never push to the default branch. If preflight starts on the default branch, `commit-push-pr` Step 1 creates a feature branch before pushing — but verify the branch is no longer the default before any `git push` actually runs; if it still is, halt.
- **Never skip hooks.** No `--no-verify`, no `--no-gpg-sign`. If a hook fails, halt with the hook's message verbatim.
- **Never invent a PR URL.** Only emit the URL `gh pr create` actually returned.

You have the capability to call multiple tools in a single response. Use the Skill tool to invoke each sub-skill, and Bash for steps 4 and 7. The only text you output is the structured separator blocks, narration sentences before Bash commands, and the final PR URL (or halt line). No other prose.
