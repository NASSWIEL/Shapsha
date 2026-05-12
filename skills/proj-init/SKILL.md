---
name: proj-init
description: "Initialise un projet Python : choix venv/poetry, outils, configs ruff/bandit/pytest, gabarits docs et README."
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /starter:proj-init

Plugin templates root: `${CLAUDE_PLUGIN_ROOT}/templates`
Project root: !`pwd`
Existing runner setting: !`python -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
try:
    data = tomllib.load(open('pyproject.toml','rb'))
    print(data.get('tool',{}).get('starter',{}).get('runner','<unset>'))
except Exception:
    print('<unset>')
" 2>/dev/null || echo "<unset>"`
venv directory: !`test -d .venv && echo "EXISTS" || echo "ABSENT"`
requirements.txt: !`test -f requirements.txt && echo "EXISTS" || echo "ABSENT"`
Project shape: !`python -c "
import os
try:
    import tomllib
except ImportError:
    import tomli as tomllib
try:
    data = tomllib.load(open('pyproject.toml','rb'))
except Exception:
    data = {}
has_poetry = bool(data.get('tool', {}).get('poetry'))
has_dep_groups = bool(data.get('dependency-groups'))
poetry_score = (1 if has_poetry else 0) + (1 if os.path.exists('poetry.lock') else 0)
uv_score = (1 if has_dep_groups else 0) + (1 if os.path.exists('uv.lock') else 0)
has_venv = os.path.isdir('.venv')
has_req = os.path.isfile('requirements.txt')
if poetry_score > 0 and uv_score == 0 and not has_venv:
    print('poetry')
elif (uv_score > 0 or has_venv) and poetry_score == 0:
    print('uv')
elif poetry_score > 0 and uv_score > 0:
    print('mixed')
elif has_req:
    print('requirements')
else:
    print('bare')
" 2>/dev/null || echo "bare"`
Already-installed tools (any section): !`python -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import re
TOOLS = ['ruff','bandit','pyright','pytest','pytest-cov','gitlint-core']
def names(deps):
    out = set()
    for d in deps or []:
        m = re.match(r'[A-Za-z0-9_.\-]+', str(d).strip())
        if m: out.add(m.group(0).lower())
    return out
try:
    data = tomllib.load(open('pyproject.toml','rb'))
except Exception:
    data = {}
seen = set()
seen |= names(data.get('project',{}).get('dependencies', []))
for grp_deps in (data.get('project',{}).get('optional-dependencies', {}) or {}).values():
    seen |= names(grp_deps)
poetry = data.get('tool',{}).get('poetry',{})
seen |= set((poetry.get('dependencies') or {}).keys())
for grp in (poetry.get('group') or {}).values():
    seen |= set((grp.get('dependencies') or {}).keys())
for grp_deps in (data.get('dependency-groups') or {}).values():
    seen |= names(grp_deps)
seen = {s.lower().replace('_','-') for s in seen}
already = sorted(t for t in TOOLS if t in seen)
print(' '.join(already) if already else '<none>')
" 2>/dev/null || echo "<none>"`

## Operating mode

**Silent.** Emit ONLY the final summary block at the very end. No text before, between, or after tool calls. No "Starting…", no "Now installing…", no "Tools installed.", no "All fragments missing.", no "Now check for…". The user sees:

1. The tool calls (visible to the harness, not narrated by you).
2. The summary block — your one and only sanctioned text output.

If you find yourself about to write a narrative sentence between tool calls, stop. Either the action is in a tool call (silent) or it is in the final summary (terminal). There is no third channel.

**Hermetic.** All helper logic stays in this SKILL.md (inline Python via `python -c`). Do not write helper scripts (`detect_*.py`, `migrate_*.py`) into the user's repo.

## Logic

### STEP 0 — Choose runner (MANDATORY FIRST ACTION)

**Determine the runner using the decision table below — in order, first match wins. Do not run any other Bash, Write, or Read before this step is complete.**

| Priority | Condition | Action |
|---|---|---|
| 1 | `Existing runner setting` is `uv`, `venv`, or `poetry` | Use it silently — user already chose. Skip to Step 1. |
| 2 | `venv directory` == `EXISTS` AND `Project shape` != `poetry` | Runner = `venv`. No question. |
| 3 | `Project shape` == `poetry` AND `venv directory` == `ABSENT` | Runner = `poetry`. No question. |
| 4 | `Project shape` == `mixed` | Runner is ambiguous — ask (question hint: `mixed`). |
| 5 | `requirements.txt` == `EXISTS` AND `Project shape` == `bare` | Migrating from requirements — ask (question hint: `requirements`). |
| 6 | `Project shape` == `bare` (nothing detected) | Fresh project — ask (question hint: `bare`). |

**When "ask" is required** (rows 4–6), call `AskUserQuestion` RIGHT NOW:

- **header**: `Environnement`
- **question**: `venv ou poetry pour ce projet ?` + one-line hint:
  - `bare` → `Aucune préférence détectée — projet vierge.`
  - `requirements` → `Un fichier requirements.txt est présent. Quel runner veux-tu utiliser ?`
  - `mixed` → `Le projet contient à la fois des métadonnées poetry et uv ; choisis celui que tu veux utiliser désormais.`
- **multiSelect**: `false`
- **options**:
  - label `venv` — description `Environnement virtuel standard (via uv). Lockfile uv.lock, dev deps sous [dependency-groups]`
  - label `poetry` — description `Lockfile poetry.lock, dev deps sous [tool.poetry.group.dev.dependencies]`

After the runner is determined (auto-detected or user-chosen), verify the tool is on PATH — and install it automatically if missing:

- `venv` → run `uv --version 2>&1`. If it fails:
  1. Output: `uv non trouvé — installation en cours...`
  2. Run (tries curl first, falls back to PowerShell on Windows):
     ```
     curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1 || powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" 2>&1
     ```
  3. Re-run `uv --version 2>&1`.
     - Success → output `uv installé avec succès.` and continue.
     - Still fails → output `proj-init aborted: impossible d'installer uv automatiquement. Install manuel : https://docs.astral.sh/uv/getting-started/installation/` stop.

- `poetry` → run `poetry --version 2>&1`. If it fails:
  1. Output: `poetry non trouvé — installation en cours...`
  2. Run:
     ```
     curl -sSL https://install.python-poetry.org | python3 - 2>&1
     ```
  3. Re-run `poetry --version 2>&1`.
     - Success → output `poetry installé avec succès.` and continue.
     - Still fails → output `proj-init aborted: impossible d'installer poetry automatiquement. Install manuel : https://python-poetry.org/docs/#installation` stop.

### Step 1 — Persist runner choice

After the runner is known, persist it to `pyproject.toml` so all other skills (`check-style`, `security`, etc.) dispatch consistently. If `pyproject.toml` does not yet exist, create the minimal version described in Step 3.1 first, then add:

```toml
[tool.starter]
runner = "<venv|poetry>"
```

Persistence script (the skill substitutes `<RUNNER>` before running):

```
!python -c "
import os, re
runner = '<RUNNER>'
text = open('pyproject.toml').read() if os.path.exists('pyproject.toml') else ''
if '[tool.starter]' not in text:
    sep = '\n' if text and not text.endswith('\n') else ''
    text += f'{sep}[tool.starter]\nrunner = \"{runner}\"\n'
else:
    pattern = re.compile(r'(\[tool\.bt-ai\][^[]*?runner\s*=\s*)\"[^\"]*\"', re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(rf'\g<1>\"{runner}\"', text, count=1)
    else:
        text = text.replace('[tool.starter]', f'[tool.starter]\nrunner = \"{runner}\"', 1)
open('pyproject.toml','w').write(text)
"
```

### Step 2 — Install dev tools — never dual-spec

A tool is **already declared** when it appears in **ANY** of these sections:

- uv side: `[project.dependencies]`, `[project.optional-dependencies.*]`, `[dependency-groups.*]`
- poetry side: `[tool.poetry.dependencies]`, `[tool.poetry.group.*.dependencies]`

If a tool is declared anywhere — even in a section the chosen runner does NOT manage — **skip the install**. The reasons:

- Re-adding via `uv add` when the tool is in `[tool.poetry.group.dev.dependencies]` creates a duplicate spec under `[dependency-groups.dev]`. Two specs, two version constraints, conflicting locks.
- The user's intent ("ruff is part of this project") is already expressed; we should not silently change which runner manages it.
- Verification (Step D) succeeds either way: `uv run ruff` works as long as ruff is installed in the active venv, regardless of which TOML section declared it.

Compute the to-install list (substitute `<RUNNER>` with the chosen value before invocation):

```
!python -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import re
TOOLS = ['ruff','bandit','pyright','pytest','pytest-cov','gitlint-core']
def names(deps):
    out = set()
    for d in deps or []:
        m = re.match(r'[A-Za-z0-9_.\-]+', str(d).strip())
        if m: out.add(m.group(0).lower())
    return out
try:
    data = tomllib.load(open('pyproject.toml','rb'))
except Exception:
    data = {}
declared = set()
declared |= names(data.get('project',{}).get('dependencies', []))
for grp_deps in (data.get('project',{}).get('optional-dependencies', {}) or {}).values():
    declared |= names(grp_deps)
for grp_deps in (data.get('dependency-groups') or {}).values():
    declared |= names(grp_deps)
poetry = data.get('tool',{}).get('poetry',{})
declared |= set((poetry.get('dependencies') or {}).keys())
for grp in (poetry.get('group') or {}).values():
    declared |= set((grp.get('dependencies') or {}).keys())
declared = {s.lower().replace('_','-') for s in declared}
to_install = [t for t in TOOLS if t not in declared]
print(' '.join(to_install))
" 2>/dev/null
```

Capture stdout into `TOOLS_TO_INSTALL`. If empty (all tools already declared somewhere) → skip the `add` invocation, record `Tools: all reachable (no install)` in the summary, continue to Step B.

If non-empty, branch on chosen runner:

- `venv` (uses `uv` under the hood):
  ```
  !uv add --dev $TOOLS_TO_INSTALL 2>&1 | tail -5
  ```
- `poetry`:
  ```
  !poetry add --group dev $TOOLS_TO_INSTALL 2>&1 | tail -5
  ```

Note: `gitlint-core` is the dependency-light variant of gitlint (without the `sh` package which fails to build on Windows because of `fcntl`). Same `gitlint` CLI; clean install on both runners.

If the install command exits non-zero → output `proj-init aborted: install failed.` followed by the captured stderr verbatim. Stop with non-zero status.

### Step 3 — Drop config files (hybrid: skip-if-identical, ask-if-conflict, create-if-missing)

For `.gitlint`:

1. `!test -f .gitlint && diff -q .gitlint "${CLAUDE_PLUGIN_ROOT}/templates/gitlint" 2>&1 || echo "MISSING_OR_DIFF"`
2. If `MISSING_OR_DIFF`:
   - `.gitlint` absent → `!cp "${CLAUDE_PLUGIN_ROOT}/templates/gitlint" .gitlint`
   - `.gitlint` differs → `AskUserQuestion`: `keep` / `overwrite` (backup to `.gitlint.bak`) / `diff` (show, then re-ask).

For `.gitignore`:

- absent → `!cp "${CLAUDE_PLUGIN_ROOT}/templates/gitignore.python" .gitignore`
- present → `!grep -q "^__pycache__/$" .gitignore && echo OK || echo APPEND`. On `APPEND`, append: `!cat "${CLAUDE_PLUGIN_ROOT}/templates/gitignore.python" >> .gitignore`.

For `pyproject.toml`:

1. Absent → write minimal:
   ```toml
   [project]
   name = "{{project-name}}"
   version = "0.0.0"
   requires-python = ">=3.12"
   ```
   Replace `{{project-name}}` with `!basename "$(pwd)"`. Continue to step 2.

2. Read current `pyproject.toml`. For each fragment in `${CLAUDE_PLUGIN_ROOT}/templates/pyproject/`:
   - `ruff.toml.fragment` → `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.lint.pydocstyle]`, `[tool.ruff.format]`.
   - `pyright.toml.fragment` → `[tool.pyright]`.
   - `bandit.toml.fragment` → `[tool.bandit]`.
   - `pytest.toml.fragment` → `[tool.pytest.ini_options]`.

3. **Merge rule**: target absent → append fragment verbatim. Identical → skip. Differs → `AskUserQuestion` `[k]eep / [m]erge / [r]eplace (backup pyproject.toml to pyproject.toml.bak)`.

   **`[m]erge` semantics — per-key smart merge** (so the fragment's flags don't get silently dropped):

   - **Whitespace-separated string values** (`addopts`, `console_output_style`): tokenize on whitespace, target tokens first, append fragment-only tokens (deduped, order-preserving). Example: target `addopts = "-ra -q"` + fragment `addopts = "-q --strict-markers --strict-config"` → `addopts = "-ra -q --strict-markers --strict-config"`.
   - **Array values** (`markers`, `filterwarnings`, `testpaths`): union — target entries first, fragment entries appended if absent.
   - **Sub-tables** (`[tool.ruff.lint.per-file-ignores]`): recursive same rules.
   - **Scalar values** (numbers, booleans, single-token strings): keep target. User's existing choice wins.
   - **Keys present only in fragment**: add to target.
   - **Keys present only in target**: keep as-is.

   Show a preview of the merged section before writing. `AskUserQuestion` `[apply / cancel]`. On `cancel`, revert to the original three-way prompt.

4. **Malformed TOML**: `!python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))" 2>&1 || echo MALFORMED`. On `MALFORMED` → output `proj-init aborted: pyproject.toml is malformed. Fix manually before re-running.` exit non-zero.

### Step 3.5 — Migrate root-level docs into `docs/`

Detect root-level Markdown docs that match the canonical doc set, and offer to move them. README is **never** moved.

| Root file (any case) | Canonical destination |
|---|---|
| `ARCHITECTURE.md` | `docs/architecture.md` |
| `DATA_MODEL.md`, `DATAMODEL.md`, `DATA-MODEL.md` | `docs/data-model.md` |
| `API_CONTRACT.md`, `CONTRACTS.md`, `API.md` | `docs/contracts.md` |
| `GLOSSARY.md`, `GLOSSAIRE.md` | `docs/glossaire.md` |
| `FUNCTIONAL.md`, `FONCTIONNEL.md`, `FEATURES.md` | `docs/fonctionnel.md` |
| `INDEX.md` | `docs/index.md` |

Detection (inline Python; nothing written to user repo):

```
!python -c "
import os
mapping = {
    'architecture.md': 'docs/architecture.md',
    'data_model.md': 'docs/data-model.md',
    'datamodel.md': 'docs/data-model.md',
    'data-model.md': 'docs/data-model.md',
    'api_contract.md': 'docs/contracts.md',
    'contracts.md': 'docs/contracts.md',
    'api.md': 'docs/contracts.md',
    'glossary.md': 'docs/glossaire.md',
    'glossaire.md': 'docs/glossaire.md',
    'functional.md': 'docs/fonctionnel.md',
    'fonctionnel.md': 'docs/fonctionnel.md',
    'features.md': 'docs/fonctionnel.md',
    'index.md': 'docs/index.md',
}
found = []
for entry in os.listdir('.'):
    if not entry.lower().endswith('.md') or entry.lower() == 'readme.md':
        continue
    if not os.path.isfile(entry):
        continue
    dest = mapping.get(entry.lower())
    if dest and not os.path.exists(dest):
        found.append(entry + '|' + dest)
print('\n'.join(found))
" 2>/dev/null
```

If non-empty:

1. `AskUserQuestion`: `move` / `keep` / `show`.
2. On `move`:
   ```
   !mkdir -p docs
   !git rev-parse --is-inside-work-tree >/dev/null 2>&1 && MV="git mv" || MV="mv"
   ```
   For each pair: `!$MV "<src>" "<dest>"`. Append to `Migrations` list.
3. On `keep`: `Migrations` list is `none`.

If empty: skip silently; `Migrations` list is `none`.

### Step 4 — Drop documentation templates (only if target absent)

`cp -n` (no-clobber). Never read+write — keeps context clean.

```
!mkdir -p docs
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/index.md" docs/index.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/architecture.md" docs/architecture.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/data-model.md" docs/data-model.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/contracts.md" docs/contracts.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/glossaire.md" docs/glossaire.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/fonctionnel.md" docs/fonctionnel.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/README.md" README.md 2>/dev/null || true
```

### Step 5 — Verify installations

Use the chosen runner.

`venv` (uses `uv run` under the hood):
```
!uv run ruff --version && uv run bandit --version && uv run pyright --version && uv run pytest --version && uv run gitlint --version 2>&1 | head -10
```

`poetry`:
```
!poetry run ruff --version && poetry run bandit --version && poetry run pyright --version && poetry run pytest --version && poetry run gitlint --version 2>&1 | head -10
```

If any line is missing → `proj-init aborted: verification failed for <tool>.` exit non-zero.

### E. NOT included (skip silently)

No `.pre-commit-config.yaml`, no CI workflows under `.github/workflows/`, no `Dockerfile`, no `Makefile`. The user opted out.

## Output (single block, no preamble, no narration)

```
proj-init complete.
  Runner: <venv|poetry>
  Tools: ruff, bandit, pyright, pytest, pytest-cov, gitlint-core
  Configs: <list per file: created/patched/kept>
  Migrations: <list of root docs moved to docs/, or "none">
  Templates: <list per file: created/skipped>
```

Replace `<list ...>` with the actual per-file outcome. No emojis. No headers in output.

## Edge cases

- `pyproject.toml` exists but malformed → abort per Step 3.4.
- Existing `[tool.ruff]` section → `AskUserQuestion` `[k]eep / [m]erge / [r]eplace`. Default: `[m]erge`.
- `.git` absent → continue, but include in output: `Note: .git/ absent — gitlint config dropped but inactive.`.
- Network failure on `uv add` → exit non-zero with stderr.
- Re-run on already-initialized project → all targets identical → silent no-op summary: `proj-init complete. (no changes)`.
- Always use `${CLAUDE_PLUGIN_ROOT}/templates` (absolute), never relative `templates/`.
- A tool already declared in the OTHER runner's section is silently skipped — no dual-spec is ever introduced. The Verify step will still pass because the tool is installed in the active venv.
