---
name: proj-init
description: Bootstrap a Python project with bt-ai standards (uv tools, configs, doc/README templates). Hybrid silent mode.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# /bt-ai:proj-init

Plugin templates root: `${CLAUDE_PLUGIN_ROOT}/templates`
Project root: !`pwd`
uv version: !`uv --version 2>&1 | head -1 || echo "uv: NOT INSTALLED"`
Poetry version: !`poetry --version 2>&1 | head -1 || echo "poetry: NOT INSTALLED"`
Detected lockfiles: !`ls -1 uv.lock poetry.lock 2>/dev/null | tr '\n' ' '`
Existing runner setting: !`python -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
try:
    data = tomllib.load(open('pyproject.toml','rb'))
    print(data.get('tool',{}).get('bt-ai',{}).get('runner','<unset>'))
except Exception:
    print('<unset>')
" 2>/dev/null || echo "<unset>"`
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
if poetry_score > 0 and uv_score == 0:
    print('poetry')
elif uv_score > 0 and poetry_score == 0:
    print('uv')
elif poetry_score > 0 and uv_score > 0:
    print('mixed')
else:
    print('bare')
" 2>/dev/null || echo "bare"`
Already-installed tools: !`python -c "
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

**Silent.** Do not narrate per-step ("Now I will install X..."). Run shell commands via `!` interpolation and emit only the final summary block.

## Logic

### Pre-flight

1. If neither `uv` nor `poetry` is installed → output exactly:

   ```
   proj-init aborted: need uv or poetry. Install uv: https://docs.astral.sh/uv/getting-started/installation/  Install poetry: https://python-poetry.org/docs/#installation
   ```

   and stop with non-zero status.

### A.0 Choose runner (install + run dispatch)

Determine the runner using this priority:

1. If `Existing runner setting` (above) is `uv` or `poetry` → reuse it silently. Skip to step A.
2. Else if **exactly one** of (`uv`, `poetry`) is installed:
   - **Project shape matches**: use it silently.
     - shape `uv` + only uv installed → use uv silently.
     - shape `poetry` + only poetry installed → use poetry silently.
     - shape `bare` (no signals either way) → use the available one silently.
   - **Project shape mismatches the only installed runner** (e.g., shape `poetry` but only uv is installed, or vice versa) → use `AskUserQuestion` (one question, two options):
     - `proceed` — Continue with the installed runner. Dev deps will be added in **the runner's native location**, which differs from the project's existing convention. Existing deps under the other runner's section remain untouched but will not be reachable via `<runner> run` until migrated.
     - `abort` — Stop. The user must install the matching runner first (uv: https://docs.astral.sh/uv/getting-started/installation/, poetry: https://python-poetry.org/docs/#installation).
     - On `abort` → output `proj-init aborted: project shape (<shape>) mismatches the only installed runner (<runner>). Install the matching runner or re-run with both available.` and stop with non-zero status.
   - **shape `mixed`** + only one runner installed → use the installed one silently. (User has both kinds of metadata; the chosen runner manages its own.)
3. Else if **both** installed → use `AskUserQuestion` (one question, two options):

   - `uv` — fast, lockfile `uv.lock`, dev deps under `[dependency-groups]`
   - `poetry` — `poetry.lock`, dev deps under `[tool.poetry.group.dev.dependencies]`

   Default suggestion priority: project shape (`poetry`/`uv`) → lockfile presence (`poetry.lock`/`uv.lock`) → fallback `uv`. For shape `mixed`, default to whichever lockfile is more recently modified; if tied or absent, default `uv` and add a one-line warning: `Note: project has both Poetry and uv metadata; choose carefully.`

After the choice is known, persist it to `pyproject.toml` so all other skills (`check-style`, `security`, etc.) dispatch consistently. If `pyproject.toml` does not yet exist, create the minimal version described in step B.1 first, then add:

```toml
[tool.bt-ai]
runner = "<uv|poetry>"
```

Persistence script:

```
!python -c "
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
runner = '<uv|poetry>'  # filled in by skill
text = open('pyproject.toml').read() if __import__('os').path.exists('pyproject.toml') else ''
if '[tool.bt-ai]' not in text:
    text += ('\n' if text and not text.endswith('\n') else '') + '[tool.bt-ai]\nrunner = \"' + runner + '\"\n'
else:
    import re
    text = re.sub(r'(\[tool\.bt-ai\][^\[]*runner\s*=\s*)\"[^\"]*\"', r'\1\"' + runner + '\"', text, count=1)
    if 'runner' not in text.split('[tool.bt-ai]')[1].split('[')[0]:
        text = text.replace('[tool.bt-ai]', '[tool.bt-ai]\nrunner = \"' + runner + '\"')
open('pyproject.toml','w').write(text)
"
```

(The skill substitutes `<uv|poetry>` with the actual choice before running.)

### A. Install dev tools

Use the **runner-filtered** tool list — drop only tools the chosen runner can already see (re-adding them would create dual specifiers). The `Already-installed tools` capture (above) is informational only; the actual filter is runner-specific:

- `runner == "uv"` reachable sections: `[project.dependencies]`, `[project.optional-dependencies.*]`, `[dependency-groups.*]`.
- `runner == "poetry"` reachable sections: `[tool.poetry.dependencies]`, `[tool.poetry.group.*.dependencies]`.

A tool declared only in the **other** runner's sections is treated as "not reachable" → it gets added by the chosen runner. This guarantees Step D verification will pass. The `Notes:` line in the final summary calls out duplication when a tool ends up declared in both runners' sections.

Compute the to-install list inline (substitute `<RUNNER>` with the chosen value before invocation):

```
!python -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import re
RUNNER = '<RUNNER>'
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
reachable = set()
if RUNNER == 'uv':
    reachable |= names(data.get('project',{}).get('dependencies', []))
    for grp_deps in (data.get('project',{}).get('optional-dependencies', {}) or {}).values():
        reachable |= names(grp_deps)
    for grp_deps in (data.get('dependency-groups') or {}).values():
        reachable |= names(grp_deps)
elif RUNNER == 'poetry':
    poetry = data.get('tool',{}).get('poetry',{})
    reachable |= set((poetry.get('dependencies') or {}).keys())
    for grp in (poetry.get('group') or {}).values():
        reachable |= set((grp.get('dependencies') or {}).keys())
reachable = {s.lower().replace('_','-') for s in reachable}
to_install = [t for t in TOOLS if t not in reachable]
print(' '.join(to_install))
" 2>/dev/null
```

Capture the stdout into `TOOLS_TO_INSTALL`. If empty (all tools already reachable via the chosen runner), skip the `add` invocation and continue to Step B; record `Tools: all reachable via <runner> (no install)` in the summary.

Then branch on the chosen runner.

If `runner == "uv"` and `TOOLS_TO_INSTALL` non-empty:

```
!uv add --dev $TOOLS_TO_INSTALL 2>&1 | tail -5
```

If `runner == "poetry"` and `TOOLS_TO_INSTALL` non-empty:

```
!poetry add --group dev $TOOLS_TO_INSTALL 2>&1 | tail -5
```

Note: `gitlint-core` is the dependency-light variant of gitlint (without the `sh` package which fails to build on Windows because of `fcntl`). It exposes the same `gitlint` CLI command and installs cleanly with both uv and poetry.

**Duplicate-section detection** (informational): after add, check whether any tool now appears in both runners' sections (e.g., `ruff` in `[project.dependencies]` and also in `[tool.poetry.group.dev.dependencies]`). If so, append to the summary: `Notes: <tool> declared in both uv and poetry sections; consider migrating to a single location.`

Capture stderr. If exit non-zero, output `proj-init aborted: <runner> add failed.` followed by the captured stderr verbatim, and stop.

### B. Drop config files (hybrid: skip-if-identical, ask-if-conflict, create-if-missing)

For `.gitlint`:

1. `!test -f .gitlint && diff -q .gitlint "${CLAUDE_PLUGIN_ROOT}/templates/gitlint" 2>&1 || echo "MISSING_OR_DIFF"`
2. If output contains `MISSING_OR_DIFF`:
   - If `.gitlint` absent → `!cp "${CLAUDE_PLUGIN_ROOT}/templates/gitlint" .gitlint`
   - If `.gitlint` differs → use AskUserQuestion (one question, three options): `keep` / `overwrite` (backup to `.gitlint.bak`) / `diff` (show, then re-ask).

For `.gitignore`:

- If `.gitignore` absent → `!cp "${CLAUDE_PLUGIN_ROOT}/templates/gitignore.python" .gitignore`
- If present → check if `__pycache__` token exists: `!grep -q "^__pycache__/$" .gitignore && echo OK || echo APPEND`. On `APPEND`, append the template: `!cat "${CLAUDE_PLUGIN_ROOT}/templates/gitignore.python" >> .gitignore`.

For `pyproject.toml`:

1. If absent → write minimal `pyproject.toml`:
   ```
   [project]
   name = "{{project-name}}"
   version = "0.0.0"
   requires-python = ">=3.12"
   ```
   Replace `{{project-name}}` with `!basename "$(pwd)"`. Then continue to step 2.
2. Read current `pyproject.toml`. For each fragment in `${CLAUDE_PLUGIN_ROOT}/templates/pyproject/`:
   - `ruff.toml.fragment` → ensures `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.lint.pydocstyle]`, `[tool.ruff.format]` sections exist with the fragment's content.
   - `pyright.toml.fragment` → `[tool.pyright]`.
   - `bandit.toml.fragment` → `[tool.bandit]`.
   - `pytest.toml.fragment` → `[tool.pytest.ini_options]`.
3. **Merge rule**: if a target section is absent → append the fragment verbatim. If present and identical to fragment → skip. If present and differs → AskUserQuestion `[k]eep / [m]erge / [r]eplace (backup pyproject.toml to pyproject.toml.bak)`.

   **`[m]erge` semantics — per-key smart merge**:

   The default `additive` rule (only add keys missing in target) silently drops fragment additions when target has its own value, which defeats the purpose for keys like `addopts` where the fragment's `--strict-markers --strict-config` would be lost if target has any `addopts`. The merge applies these rules **per key** inside each TOML table:

   - **Whitespace-separated string values** (CLI flag strings: `addopts`, `console_output_style`, etc.): tokenize on whitespace, take target tokens first, append fragment-only tokens (deduped, order-preserving). Example: target `addopts = "-ra -q"` + fragment `addopts = "-q --strict-markers --strict-config"` → `addopts = "-ra -q --strict-markers --strict-config"`.
   - **Array values** (`markers`, `filterwarnings`, `testpaths`): union — target entries first, then fragment entries that aren't already present (string equality).
   - **Sub-tables** (e.g., `[tool.ruff.lint.per-file-ignores]`): recursive merge with these same rules.
   - **Scalar values** (numbers, booleans, single-token strings like `minversion = "8.0"`): keep target value. The user's existing choice wins.
   - **Keys present only in fragment**: add to target.
   - **Keys present only in target**: keep as-is.

   Show the user a preview of the merged section before writing. AskUserQuestion `[apply / cancel]`. On `cancel`, revert to the original three-way prompt.

   Implementation reference (used by the skill at merge time; `<TARGET_SECTION>` and `<FRAGMENT_PATH>` are substituted before running):

   ```
   !python <<'PY'
   try:
       import tomllib
   except ImportError:
       import tomli as tomllib

   def is_flag_string(v):
       return isinstance(v, str) and (' ' in v or v.startswith('-'))

   def smart_merge(target, fragment):
       if isinstance(target, dict) and isinstance(fragment, dict):
           out = dict(target)
           for k, fv in fragment.items():
               if k in out:
                   out[k] = smart_merge(out[k], fv)
               else:
                   out[k] = fv
           return out
       if isinstance(target, list) and isinstance(fragment, list):
           seen = list(target)
           for item in fragment:
               if item not in seen:
                   seen.append(item)
           return seen
       if is_flag_string(target) and is_flag_string(fragment):
           toks = target.split()
           for t in fragment.split():
               if t not in toks:
                   toks.append(t)
           return ' '.join(toks)
       return target  # scalar conflict → keep target

   target_toml = tomllib.load(open('pyproject.toml','rb'))
   fragment_toml = tomllib.load(open('<FRAGMENT_PATH>','rb'))
   # Merge only the relevant section; drop into target's tree at the same key path.
   # Skill substitutes the section walker for the specific fragment.
   PY
   ```

   The skill performs the actual write back to `pyproject.toml` only after the user confirms the preview.
4. **Malformed TOML**: if `pyproject.toml` does not parse, output `proj-init aborted: pyproject.toml is malformed. Fix manually before re-running.` and stop with non-zero status. Detect with `!python -c "import sys; sys.exit(0 if __import__('tomllib').load(open('pyproject.toml','rb')) is not None else 1)" 2>&1 || echo MALFORMED` (uses the system Python — independent of which runner the project chose).

### C.5 Migrate root-level docs into `docs/` (BEFORE step C)

Detect root-level Markdown docs that match the plugin's canonical doc set, and offer to move them into `docs/` with the canonical lowercase French name. README is **never** moved (it stays at the repo root by design).

Detection table (case-insensitive match on the bare filename at the repo root):

| Root file (any case) | Canonical destination |
|---|---|
| `ARCHITECTURE.md` | `docs/architecture.md` |
| `DATA_MODEL.md`, `DATAMODEL.md`, `DATA-MODEL.md` | `docs/data-model.md` |
| `API_CONTRACT.md`, `CONTRACTS.md`, `API.md` | `docs/contracts.md` |
| `GLOSSARY.md`, `GLOSSAIRE.md` | `docs/glossaire.md` |
| `FUNCTIONAL.md`, `FONCTIONNEL.md`, `FEATURES.md` | `docs/fonctionnel.md` |
| `INDEX.md` | `docs/index.md` |

Detection script:

```
!python -c "
import os, sys
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
" 2>/dev/null`
```

If the detection output is non-empty:

1. Use `AskUserQuestion` (one question, three options):
   - `move` — Move all detected files into `docs/` with canonical names (uses `git mv` to preserve history; falls back to `mv` if not a git repo)
   - `keep` — Leave the root files alone; step C will create empty templates in `docs/` for whatever is missing
   - `show` — Print the planned `<src> -> <dest>` list, then re-ask `move / keep`
2. On `move`:
   ```
   !mkdir -p docs
   !git rev-parse --is-inside-work-tree >/dev/null 2>&1 && MV="git mv" || MV="mv"
   ```
   Then for each detected pair:
   ```
   !$MV "<src>" "<dest>"
   ```
   Append each migrated pair to a `Migrations` list for the final summary.
3. On `keep`: append `none` to the Migrations list.

If the detection output is empty: skip silently; Migrations list is `none`.

### C. Drop documentation templates (only if target absent)

Use `cp -n` (no-clobber). Never read+write — keeps context clean.

```
!mkdir -p docs .github/ISSUE_TEMPLATE
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/index.md" docs/index.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/architecture.md" docs/architecture.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/data-model.md" docs/data-model.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/contracts.md" docs/contracts.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/glossaire.md" docs/glossaire.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/docs/fonctionnel.md" docs/fonctionnel.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/README.md" README.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/github/PULL_REQUEST_TEMPLATE.md" .github/PULL_REQUEST_TEMPLATE.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/github/ISSUE_TEMPLATE/bug_report.md" .github/ISSUE_TEMPLATE/bug_report.md 2>/dev/null || true
!cp -n "${CLAUDE_PLUGIN_ROOT}/templates/github/ISSUE_TEMPLATE/feature_request.md" .github/ISSUE_TEMPLATE/feature_request.md 2>/dev/null || true
```

### D. Verify installations

Use the chosen runner. If `runner == "uv"`:

```
!uv run ruff --version && uv run bandit --version && uv run pyright --version && uv run pytest --version && uv run gitlint --version 2>&1 | head -10
```

If `runner == "poetry"`:

```
!poetry run ruff --version && poetry run bandit --version && poetry run pyright --version && poetry run pytest --version && poetry run gitlint --version 2>&1 | head -10
```

If any line is missing, the corresponding tool failed to install. Output `proj-init aborted: verification failed for <tool>.` and stop with non-zero status.

### E. NOT included (skip silently)

Do not create `.pre-commit-config.yaml`, CI workflows under `.github/workflows/`, `Dockerfile`, or `Makefile`. The user opted out.

## Output (single block, no preamble, no narration)

```
proj-init complete.
  Runner: <uv|poetry>
  Tools: ruff, bandit, pyright, pytest, pytest-cov, gitlint-core
  Configs: <list per file: created/patched/kept>
  Migrations: <list of root docs moved to docs/, or "none">
  Templates: <list per file: created/skipped>
```

Replace `<list ...>` with the actual per-file outcome of steps B, C.5, and C. No emojis. No headers in output.

## Edge cases

- `pyproject.toml` exists but malformed TOML → abort per step B.4.
- Existing `[tool.ruff]` section → AskUserQuestion `[k]eep / [m]erge / [r]eplace`. Default: `[m]erge`.
- `.git` absent → continue, but include in output: `Note: .git/ absent — gitlint config dropped but inactive.`.
- Network failure on `uv add` → exit non-zero with stderr.
- Re-run on already-initialized project → all targets identical → silent no-op summary: `proj-init complete. (no changes)`.
- Always use `${CLAUDE_PLUGIN_ROOT}/templates` (absolute), never relative `templates/`.
