---
allowed-tools: Bash(git checkout:*), Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git push:*), Bash(git commit:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git branch:*), Bash(test:*), Bash(cat:*), Bash(rm:*), Bash(gh pr create:*), Bash(gh repo view:*), Bash(gh auth status:*)
description: Commit, push, et ouvre une PR (titre en anglais, corps en français)
disable-model-invocation: true
---

# /starter:commit-push-pr

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
2. GH auth is `missing` → fall back to push-only mode (no PR creation). Skip step 4 and instead, after step 3, output the push confirmation followed by:
   ```
   Pushed. Skipping PR creation: gh CLI not authenticated.
   The 'gh' CLI is independent from git credentials — it needs its own login to call the GitHub API.
   To enable PR creation: run 'gh auth login' once, then retry /starter:commit-push-pr (or use 'gh pr create' manually).
   ```
   Stop with success.
3. Nothing staged AND nothing unstaged → output `Nothing to commit.` Stop.
4. Something is unstaged but nothing staged → output `Unstaged changes detected. Stage them first (git add) or run /starter:preflight.` Stop.

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

If GH auth was `missing` (push-only fallback above), do not run step 4 — emit the fallback message after step 3 and stop.

### Step 4 — open PR

Title = the commit subject (English Conventional Commit style is fine for the title).

**Body : EN FRANÇAIS — non négociable. EXACTEMENT 1 à 3 bullet points, rien d'autre.**

Règles strictes :
- Format : **uniquement des bullet points** (`- ...`). 1 minimum, 3 maximum.
- Pas de prose, pas de paragraphe, pas de phrase isolée hors bullet.
- Pas de titres `##`, pas de sections, pas de checklist (`- [ ]`).
- Chaque bullet est en français, factuel, dérivé du diff staged. Jamais inventé.
- Aucun bullet en anglais — même si le commit message est en anglais, le corps de PR reste en français.

Exemple valide :

```
- Ajoute `arithmetic.divide` qui lève `ValueError` sur diviseur zéro.
- Étend `clamp` aux bornes inversées.
- Met à jour le README pour la nouvelle commande.
```

Exemples interdits :
- Plus de 3 bullets.
- Phrase en prose hors bullet (`Ajoute le helper...` sans `-` devant).
- Bullet en anglais (`- Adds clamp helper`).
- Titres de section (`## Contexte`, `## Changements`, `## Plan de test`).
- Checklist (`- [ ] vérifier que...`).

Run via heredoc :

```
gh pr create --title "<title>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

Avant d'exécuter `gh pr create`, **relis ton body** : si tu vois plus de 3 bullets, de la prose hors bullet, ou de l'anglais, réécris-le avant d'envoyer la commande.

The output of `gh pr create` is the PR URL on the last line — that is the only thing you emit to the user. Print it on its own line, no preamble.

### Hard rules

- **Never force-push.** No `--force`, no `--force-with-lease`. If `git push` fails with a diverged-history error, surface the error verbatim and stop. The user resolves manually.
- **Never push to the default branch.** Step 1 prevents this; if you somehow find yourself on the default branch after step 1, stop and surface the failure.
- **Never skip hooks.** No `--no-verify`, no `--no-gpg-sign`. If a pre-commit/pre-push hook fails, surface its output verbatim and stop.
- **Do not invent PR URLs.** Only emit the URL `gh pr create` actually returned. If it failed with "a pull request for branch already exists", parse the existing URL out of the error and emit that instead.
- **PR body en français, 1-3 bullet points uniquement.** Le titre peut être en anglais (Conventional Commit). Le corps NON. Format imposé : `- ...` × 1 à 3, rien d'autre. Pas de prose, pas de sections, pas de checklist. Aucune exception. **La même règle s'applique aux issues GitHub** créées par le plugin (1-3 bullets en français).
- **Single message.** You have the capability to call multiple tools in a single response. You MUST do steps 1-4 (whichever apply) in a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls and the final PR URL (or halt line).
