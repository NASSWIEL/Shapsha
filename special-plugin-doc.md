# `bt-ai` plugin — implementation documentation

**Plugin name**: `bt-ai`
**Marketplace**: `CGI-BT-AI` (single-plugin marketplace, layout: plugin at repo root)
**Author**: shapsha-lemans <shapsha-lemans@cgi.com>
**License**: Proprietary
**Version**: 0.0.0
**Distribution**: git clone + `/plugin install` from `https://github.com/nasswiel/CGI-BT-AI`

This document records what is implemented, the workflow it produces, the methodology behind the choices, the use-cases each component serves, and the rationale for every tool the plugin depends on. It is a runtime reference: a contributor or auditor should be able to read this single file and understand the surface, the contracts, and the trade-offs.

---

## 1. Purpose

`bt-ai` standardises Python engineering practice for the BT-AI team at CGI. It bundles seven model-invokable skills, two deterministic slash commands, five focused subagents, and a set of project templates so that new repositories start on the same footing and changes are validated with the same gates before reaching `main`.

The plugin's design intent is twofold:

1. **Lower the cost of doing the right thing**: linting, security scanning, test generation, doc sync, README sync, commit hygiene, and PR creation are all behind one-line slash commands.
2. **Keep the cost of getting it wrong**: the plugin halts loudly on critical findings rather than silently masking them; auto-fix is scoped to changes that cannot alter program behaviour.

---

## 2. Repository layout

```
skills-BT-AI/                                 ← marketplace = plugin
├── .claude-plugin/
│   ├── marketplace.json                      ← marketplace manifest
│   └── plugin.json                           ← plugin manifest
├── commands/                                 ← deterministic shell, no model judgement
│   ├── commit.md                             → /bt-ai:commit
│   └── commit-push-pr.md                     → /bt-ai:commit-push-pr
├── skills/                                   ← model-invokable, all disable-model-invocation: true
│   ├── check-style/SKILL.md                  → /bt-ai:check-style
│   ├── security/SKILL.md                     → /bt-ai:security
│   ├── gen-tests/SKILL.md                    → /bt-ai:gen-tests
│   ├── doc-sync/SKILL.md                     → /bt-ai:doc-sync
│   ├── readme-sync/SKILL.md                  → /bt-ai:readme-sync
│   ├── preflight/SKILL.md                    → /bt-ai:preflight
│   └── proj-init/SKILL.md                    → /bt-ai:proj-init
├── agents/                                   ← silent subagents, isolated context
│   ├── style-fixer.md
│   ├── security-fixer.md
│   ├── test-writer.md
│   ├── doc-patcher.md
│   └── readme-patcher.md
├── templates/                                ← copied verbatim by /bt-ai:proj-init
│   ├── pyproject/
│   │   ├── ruff.toml.fragment
│   │   ├── pyright.toml.fragment
│   │   ├── bandit.toml.fragment
│   │   └── pytest.toml.fragment
│   ├── gitlint
│   ├── gitignore.python
│   ├── README.md                             ← French, user-project template
│   ├── docs/                                 ← French doc skeletons (6 files)
│   │   ├── index.md
│   │   ├── architecture.md
│   │   ├── data-model.md
│   │   ├── contracts.md
│   │   ├── glossaire.md
│   │   └── fonctionnel.md
│   └── github/
│       ├── PULL_REQUEST_TEMPLATE.md
│       └── ISSUE_TEMPLATE/
│           ├── bug_report.md
│           └── feature_request.md
├── README.md                                 ← French, plugin-installer-facing
├── LICENSE
└── DESIGN.md                                 ← original contract document
```

Two manifests describe the marketplace and the plugin separately. `marketplace.json` lists `bt-ai` as the only plugin (source `.`); `plugin.json` declares folders for `skills`, `agents`, and `commands`.

---

## 3. Locked design decisions

| # | Decision | Value |
|---|----------|-------|
| Plugin name | `bt-ai` (slash prefix) | `/bt-ai:<skill>` |
| Marketplace name | `CGI-BT-AI` | repo + folder |
| Layout | plugin at repo root | single-plugin marketplace |
| Distribution | git clone + `/plugin install` | personal GitHub |
| Python toolchain | uv-managed | `ruff`, `bandit`, `pyright`, `pytest`, `pytest-cov`, `gitlint-core` |
| Plugin repo README | French (dev-facing) | |
| Template README (proj-init drops) | French (user project) | |
| Doc templates | French | |
| Commit messages | English | Conventional Commits 1.0 |
| PR body | French | three sections: Contexte / Changements / Plan de test |
| Branch naming | `<type>/<slug>` | enforced at step 1 of `commit-push-pr` |
| Severity mapping (ruff) | Critical=`F`,`E9`; High=`B`,`S`; Low (auto-fix)=`W`,`D`,`I`,`UP`; Medium hidden=`N`,`C`,`PL` |
| Bandit threshold | severity ≥ MEDIUM AND confidence ≥ MEDIUM |
| Bandit no-auto-fix list | `B102`, `B307`, `B301`, `B324`, `B501`–`B508`, `B602`–`B608`, `B610`, `B611`, `B701` |
| Test location | `tests/foo/test_bar.py` mirroring `src/foo/bar.py` |
| Silent execution | mandatory — no narration |
| Skill auto-invocation | disabled — `disable-model-invocation: true` everywhere |

---

## 4. Methodology

### 4.1 Three-tier component split

The plugin separates **deterministic shell** (slash commands), **rule-driven branching with prompts** (skills), and **isolated text-mutating reasoning** (subagents). Each tier has different guarantees:

| Tier | Component | Tooling | Determinism | Allowed reasoning |
|------|-----------|---------|-------------|-------------------|
| 1 | Slash commands | Bash only, allowlisted | Fully deterministic | None — pure text composition from diffs |
| 2 | Skills | Bash + Read + Glob | Branches on shell output | Pre-flight, classification, prompts |
| 3 | Subagents | Read/Edit/Write only | Free within tool limits | Patches, tests, README/doc edits |

This layering is what makes `Silent execution` achievable: the user-visible turn is dominated by the parent skill's single-line summary, while the reasoning happens inside an isolated subagent whose intermediate context never reaches the parent.

### 4.2 Silent-by-design

Every skill declares `**Silent.**` as the first paragraph after `## Operating mode`. The model is instructed not to emit per-step narration. Diagnostics are produced by `!` bash interpolation; the model only emits the final summary block. This avoids two real problems:

- conversational noise in CI-like workflows, and
- token bloat from intermediate progress messages.

### 4.3 No automatic model invocation

Every SKILL.md uses `disable-model-invocation: true`. The model never decides to run `check-style` on its own; the user must type `/bt-ai:check-style`. This is a safety property: skills perform actions (file edits, commits, PRs), and surprise invocation is a foot-gun.

### 4.4 Diff-driven scope

Five skills (`check-style`, `security`, `gen-tests` diff mode, `doc-sync`, `readme-sync`) all start by computing the union of:

- `git diff --name-only --diff-filter=ACMR` (unstaged tracked changes)
- `git diff --cached --name-only --diff-filter=ACMR` (staged tracked changes)
- `git ls-files --others --exclude-standard` (untracked files)

This pattern is necessary because:

- `git diff HEAD` alone fails on **fresh repos** with `fatal: bad revision 'HEAD'`.
- `git diff` alone misses **untracked files**, which on a fresh feature branch are exactly the files the user wants validated.

The pattern is verified across all five skills.

### 4.5 Severity is binary in effect, three-bucket in display

Ruff and Bandit both produce hundreds of distinct rule codes. The plugin maps them into one of four buckets and uses bucket policy, not per-code policy:

- **Critical** halts the workflow (`F`, `E9`).
- **High** is printed and prompts the user (`B`, `S`).
- **Low** is auto-fixed silently (`W`, `D`, `I`, `UP`).
- **Medium** is hidden (`N`, `C`, `PL`) — useful as code review hints, not as gates.

This avoids the fatigue of "everything is a warning". The team negotiated which prefixes go where once; afterwards every project gets the same treatment.

### 4.6 No-auto-fix blacklist for security

Bandit findings can be syntactic (e.g., assert in tests) or semantic (e.g., `eval`). The plugin refuses auto-fix on dangerous-execution rules (`B102 exec`, `B307 eval`, `B301 pickle`, `B324 insecure hash`, `B501`–`B508` cryptography family, `B602`–`B608` subprocess, `B610`–`B611` SQL injection, `B701 jinja2 autoescape`). The rationale: these findings reflect intent, not typos; rewriting them silently would mask the issue without solving it.

The list is enforced twice — once in the parent skill (filters before delegation) and once in the `security-fixer` agent (refuses anyway). Defence in depth.

### 4.7 Subagent context isolation

Five subagents are invoked via `Task`. Each runs in a separate context window. This produces three concrete benefits:

1. The subagent reads only the documents it needs (e.g., `doc-patcher` reads `index.md` always, then only the impacted docs from a 6-doc set). Reading 4 unrelated docs would otherwise pollute the parent context.
2. The subagent receives a structured JSON payload, not the full diff text history. The parent's earlier turns stay clean.
3. The subagent's tool allowlist is minimal and different from the parent's. `doc-patcher` and `readme-patcher` only have `Read` and `Glob`; they cannot write files. The parent applies edits with its own `Edit` tool from the unified diff the subagent returned.

### 4.8 Hybrid file-creation policy

`/bt-ai:proj-init` does not blindly overwrite. For each managed file:

- **Absent** → create from template.
- **Identical to template** → skip silently.
- **Differs from template** → `AskUserQuestion` with three options: `keep` / `overwrite` (with `.bak`) / `diff` (show, then re-ask).

For `pyproject.toml` specifically, fragment-merging is offered: only sections missing in the target are appended; existing sections are preserved by default. This keeps proj-init re-runnable.

### 4.9 Pre-validated commit messages via `.git/COMMIT_EDITMSG`

`/bt-ai:preflight` step 7 composes a Conventional Commit message from the staged diff and validates it through `gitlint --staged --msg-stdin`. On success, the message is written to `.git/COMMIT_EDITMSG`. Step 8 then invokes `/bt-ai:commit-push-pr`, which detects the file and uses `git commit -F .git/COMMIT_EDITMSG`, then `rm -f`s it. This handoff path was chosen over arguments because:

- it is robust to the user inspecting the message between preflight and the commit,
- it is recoverable: if step 8 fails, the file remains and the user sees the validated message,
- it adds zero new flags to the commit-push-pr surface.

---

## 5. Component reference

### 5.1 Slash commands (deterministic)

#### `/bt-ai:commit`

**Use case**: produce a Conventional Commit on already-staged changes, English, no PR.

**Inputs**: staged diff, recent commit subjects (style reference).

**Behaviour**: composes a `<type>(<scope>?): <subject>` line under 72 chars, optional body wrapped at 100; commits via heredoc to preserve formatting.

**Output**: `<short-hash> <subject>` on success.

**Tool allowlist**: `git add`, `git status`, `git diff`, `git commit`, `git log`. No `--no-verify`. Pre-commit hook rejection is surfaced verbatim.

#### `/bt-ai:commit-push-pr`

**Use case**: end-to-end "ship a feature": branch creation if on default branch, commit, push, PR.

**Branch handling**: if on `main`/`master`, derive `<type>/<slug>` (kebab-case, ≤5 words) from the diff and `git checkout -b`.

**Commit handling**: if `.git/COMMIT_EDITMSG` exists and is non-empty (preflight wrote it), commit via `-F` and clear the file; otherwise compose fresh.

**Push**: `git push -u origin <branch>`. No force-push.

**PR**: title = commit subject; body in **French** with three sections (`## Contexte`, `## Changements`, `## Plan de test`). Created via `gh pr create`.

**Tool allowlist**: scoped to `git`, `gh pr create`, `gh repo view`, `gh auth status`, `test`, `cat`, `rm`. No broader shell.

### 5.2 Skills

#### `/bt-ai:check-style`

**Use case**: lint changed Python files; auto-fix the safe stuff, prompt the user on the risky stuff, halt on the critical stuff.

**Engine**: `uv run ruff check ... --output-format=json --no-fix` for findings; `uv run ruff check ... --fix --select=E,W,D,I,UP --silent` followed by `uv run ruff format` for the auto-fix tier.

**Severity buckets**: as listed in §3. The skill prints `[CRITICAL]` and `[HIGH]` lines, hides Medium, and silently fixes Low.

**Decision point**: if any High finding exists, `AskUserQuestion` with `[a]uto-fix / [s]how diffs / [n]o`. Auto-fix delegates to the `style-fixer` agent.

**Output**: `<fixed_count> fixed, <remaining_count> remaining.` Exit non-zero if remaining > 0.

#### `/bt-ai:security`

**Use case**: scan changed Python files for security issues at a useful signal-to-noise ratio.

**Engine**: `uv run bandit -f json -ll -ii <files>` — `-ll` filters severity ≥ MEDIUM, `-ii` filters confidence ≥ MEDIUM. Two filters, both medium: keeps the high-confidence-but-low-impact and low-confidence-but-high-impact noise out.

**Classification**: each finding is `[FIXABLE]` or `[BLOCKED]`. The blacklist (§4.6) determines blocked status.

**Decision point**: if any FIXABLE exists, `AskUserQuestion` with `[a]uto-fix / [s]how diffs / [n]o`. If only BLOCKED findings exist, no prompt — direct halt.

**Output**: `<fixed> fixed, <blocked> require manual fix.` Exit non-zero if blocked > 0.

#### `/bt-ai:gen-tests`

**Use case**: ensure every public function in a changed file has a corresponding pytest test.

**Two modes**:
- **Diff mode** (no args): scans changed `*.py` excluding `tests/**`.
- **Targeted mode** (`/bt-ai:gen-tests path1 path2 ...`): scans those files/dirs explicitly.

**Path mapping**: `src/foo/bar.py` → `tests/foo/test_bar.py`; `foo/bar.py` (no `src/` prefix) → `tests/foo/test_bar.py`; `pkg.py` at root → `tests/test_pkg.py`.

**Filter**: extracts public top-level functions and class methods (no underscore prefix); matches against existing `test_*` functions in the corresponding test file; missing-only are forwarded to the agent.

**Verification**: after the agent writes tests, the parent runs `uv run pytest --collect-only <files>` to verify collection. Failure halts and surfaces output verbatim.

#### `/bt-ai:doc-sync`

**Use case**: keep `docs/*.md` aligned with code changes without rewriting unrelated sections.

**Scope**: 6 doc files (`index.md`, `architecture.md`, `data-model.md`, `contracts.md`, `glossaire.md`, `fonctionnel.md`).

**Routing matrix** (parent passes to agent):

| Diff signal | Doc | Section to update |
|---|---|---|
| `class \w+`, dataclass fields, schema changes | `data-model.md` | Entities, relationships |
| New route, endpoint, public method, event signature | `contracts.md` | Per-API section |
| New module, dependency, infra change | `architecture.md` | Composants, dépendances |
| New business term or domain concept | `glossaire.md` | Alphabetical |
| User-visible behaviour or business rule | `fonctionnel.md` | Use cases, règles |
| Any patch above | `index.md` | §2 freshness table |

**Discipline**: agent reads `index.md` always, then **only** the impacted docs. Never reads all 6.

**Diff cap**: 500 lines, including untracked files emitted as new-file hunks.

**Decision point**: prints proposed patches, `AskUserQuestion` with `[a]pply / [s]how full diffs / [n]o`. Patches that fail to apply do not abort the rest; they are reported.

#### `/bt-ai:readme-sync`

**Use case**: only patch `README.md` when a **user-facing** surface changed.

**Five signals scanned** from staged + unstaged + untracked:
1. `scripts_changed` — `[project.scripts]` entries in `pyproject.toml`.
2. `all_changed` — `__all__` definitions in `*.py`.
3. `env_vars_added` — `os.environ` / `os.getenv` calls added.
4. `deps_added` — dependency lines in `pyproject.toml`.
5. `install_files_changed` — `Dockerfile`, `Makefile`, `pyproject.toml` touched.

**Discipline**: if all flags false → silent no-op. Otherwise, delegate to `readme-patcher`. The agent may still return `patch: null` if signals fired but no semantics actually changed (e.g., dependency-version-only bump).

**French tone preservation**: hardcoded into the agent prompt.

#### `/bt-ai:preflight`

**Use case**: pre-PR validation suite. Sequential, halt on first failure.

**Eight steps**:
1. `check-style` — halt if Critical/High remain unresolved.
2. `security` — halt if BLOCKED remain or user declined fixable.
3. `gen-tests` (diff mode) — halt on subagent failure or pytest collection failure.
4. `pytest -q` — halt on test failure; emits the captured tail.
5. `doc-sync` — halt if user declined or a patch failed to apply.
6. `readme-sync` — halt if user declined or patch failed.
7. **Commit message gate**: compose Conventional Commit from staged diff; validate via `gitlint --staged --msg-stdin`; on validation success, write to `.git/COMMIT_EDITMSG`; on failure, prompt for rewrite (one retry).
8. `commit-push-pr` — consumes `.git/COMMIT_EDITMSG` if present.

**Guard before step 1**:
- not a git repo → halt;
- nothing staged AND nothing unstaged → halt;
- something unstaged but nothing staged → halt with `Stage them first (git add).` (preflight does not silently `git add` user changes; staging remains a user action).

**Output**: PR URL on full success; `Halted at step <N>: <reason>.` followed by the failing tool's verbatim output otherwise.

#### `/bt-ai:proj-init`

**Use case**: bootstrap a new (or partly initialised) project with the team's standards.

**Step A — install dev tools**:
```
uv add --dev ruff bandit pyright pytest pytest-cov gitlint-core
```

**Step B — config files** (hybrid policy, see §4.8):
- `.gitlint` — copy if absent; merge-prompt if differs.
- `.gitignore` — copy if absent; append the python set if `__pycache__/` token missing.
- `pyproject.toml` — create minimal if absent; for each section (`[tool.ruff]`, `[tool.pyright]`, `[tool.bandit]`, `[tool.pytest.ini_options]`), append-if-absent / skip-if-identical / prompt-if-different.

**Step C — documentation templates**: `cp -n` (no-clobber) for `README.md`, six files under `docs/`, GitHub PR template, GitHub issue templates. Never overwrites.

**Step D — verification**: runs each tool's `--version`. Failure aborts with which tool failed.

**Step E — explicit non-goals**: no `.pre-commit-config.yaml`, no CI workflows, no `Dockerfile`, no `Makefile`. The team opted out at design time.

### 5.3 Subagents

| Agent | Used by | Tools | Output | Why isolated |
|-------|---------|-------|--------|--------------|
| `style-fixer` | check-style | Read, Edit, Bash | `fixed=N skipped=M files=...` | Runs ruff with `--unsafe-fixes` only on a curated safe set (`B007`, `B009`, `B010`, `B011`, `S101` in tests) |
| `security-fixer` | security | Read, Edit | `fixed=N reported=M refused=K` | Per-code action table: most findings are **report only**; only `B113` (request without timeout) is mechanically applied |
| `test-writer` | gen-tests | Read, Write, Edit, Glob, Bash | `files=... tests_added=N collection_ok=true\|false` | Generates golden path + one error case + one boundary value per missing symbol; uses parametrize when natural; never overwrites existing tests |
| `doc-patcher` | doc-sync | Read, Glob | JSON `{"patches": [...], "skipped": [...]}` | Reads `index.md` then only impacted docs; ≤30 % rewrite cap; never invents identifiers; preserves French tone |
| `readme-patcher` | readme-sync | Read | JSON `{"patch": "...", "sections_touched": [...]}` or `{"patch": null, "reason": "..."}` | Patches only signal-justified sections; preserves French tone; may return `patch: null` |

All subagents are **silent**, return a structured single result, and never run `git`, `pytest`, `gh`, or any side-effecting tool other than the minimum needed.

### 5.4 Templates

| File | Purpose |
|------|---------|
| `templates/pyproject/ruff.toml.fragment` | `[tool.ruff]`, lint select set, per-file-ignores for `tests/**` (S101, D) and `__init__.py` (F401), pydocstyle convention `google`, format `quote-style = "double"`. |
| `templates/pyproject/pyright.toml.fragment` | `[tool.pyright]` baseline. |
| `templates/pyproject/bandit.toml.fragment` | `[tool.bandit]` baseline. |
| `templates/pyproject/pytest.toml.fragment` | `[tool.pytest.ini_options]` with `--strict-markers --strict-config`. |
| `templates/gitlint` | Conventional Commits ruleset (subject regex, line lengths, type list). |
| `templates/gitignore.python` | Standard Python ignores. |
| `templates/README.md` | French, user-project README skeleton. |
| `templates/docs/{index,architecture,data-model,contracts,glossaire,fonctionnel}.md` | French doc skeletons with `MODE D'EMPLOI` blocks at end (used by `doc-patcher` for routing). |
| `templates/github/PULL_REQUEST_TEMPLATE.md` | French PR body template (Contexte / Changements / Plan de test). |
| `templates/github/ISSUE_TEMPLATE/{bug_report,feature_request}.md` | French issue templates. |

---

## 6. End-to-end workflows

### 6.1 New project (greenfield)

```
1. mkdir my-proj && cd my-proj && git init && uv init
2. /plugin install bt-ai (from the marketplace)
3. /bt-ai:proj-init
   ├─ uv adds dev tools
   ├─ creates .gitlint, .gitignore, docs/, .github/, README.md
   └─ patches pyproject.toml with [tool.ruff], [tool.pyright], [tool.bandit], [tool.pytest.ini_options]
4. write some code
5. /bt-ai:preflight
   ├─ check-style → security → gen-tests → pytest → doc-sync → readme-sync → commit-msg-gate → commit-push-pr
   └─ outputs PR URL
```

### 6.2 Existing project (one-off validation)

```
1. /bt-ai:check-style       (changed files only)
2. /bt-ai:security
3. /bt-ai:gen-tests src/foo (targeted mode — explicit path)
4. /bt-ai:doc-sync          (only if docs/ exists)
5. /bt-ai:readme-sync
6. /bt-ai:commit            (or /bt-ai:commit-push-pr for the full path)
```

### 6.3 Iterative loop during a feature

```
edit code → /bt-ai:check-style → fix → /bt-ai:security → fix → /bt-ai:gen-tests → ... → /bt-ai:preflight
```

Each individual skill is independent and idempotent. `/bt-ai:preflight` re-runs them all in order; passing intermediate skills is cheap because diff-driven scope is small.

---

## 7. Use cases handled

| Use case | Skill / command | How it is handled |
|---|---|---|
| New repo bootstrap | `proj-init` | Step A installs tools; B drops configs; C drops docs; D verifies |
| Fix lint on what I just changed | `check-style` | Diff-driven scope, auto-fix Low, prompt on High |
| Security audit on what I just changed | `security` | Bandit MEDIUM/MEDIUM, no-auto-fix blacklist, prompt on FIXABLE |
| Tests for a new function | `gen-tests` (targeted) | Symbol extraction → missing-only → agent generates skeleton |
| Tests for whole feature branch | `gen-tests` (diff mode) | Same as above but scope = all changed `.py` |
| Doc drift on architecture/data-model | `doc-sync` | Routing matrix, agent reads only impacted docs |
| README drift after API surface change | `readme-sync` | Five signals; agent patches only impacted sections |
| Quick commit on staged changes | `commit` | Compose Conventional Commit, validate, commit |
| Branch + commit + push + PR | `commit-push-pr` | Branch from default, French PR body |
| Full pre-PR gate | `preflight` | All seven skills sequentially + commit-push-pr at the end |
| Re-run on already-initialised project | `proj-init` | Hybrid policy (skip-if-identical, ask-if-conflict, create-if-missing) |
| Fresh repo (no commits yet) | All diff-driven skills | Union pattern: `git diff` ∪ `git diff --cached` ∪ `git ls-files --others` |
| Untracked files with new code | All diff-driven skills | Same union pattern catches them |
| Pre-commit hook rejection | `commit`, `commit-push-pr` | Surface failure; never `--no-verify` |
| User on default branch | `commit-push-pr` | Auto-creates `<type>/<slug>` branch |
| Stale `.git/COMMIT_EDITMSG` | `preflight` step 7 | Overwrites; consumed and removed by step 8 |
| All findings already fixed / nothing to do | every skill | Silent no-op summary, exit 0 |

---

## 8. Tool choices and justifications

### 8.1 `uv` (package manager)

**Why**: chosen as the single Python toolchain for `proj-init`. `uv` resolves environments fast, locks via `uv.lock`, and runs ad-hoc tools with `uv run` without polluting global Python. Skills use `uv run <tool>` rather than asking the user to activate a venv. The plugin assumes uv is installed; pre-flight outputs an explicit install URL if missing.

**Trade-off**: projects already using Poetry, Hatch, or PDM are not first-class citizens; `uv add --dev` writes to `[dependency-groups]` (PEP 735) which Poetry will not see. This is documented in the design contract.

### 8.2 `ruff` (lint + format)

**Why**: replaces flake8 / pycodestyle / pydocstyle / isort / pyupgrade / black with one binary. JSON output is stable and parseable; severity classification (§4.5) is by rule prefix.

**Configured rule families** (`[tool.ruff.lint] select`): `E`, `F`, `B`, `S`, `N`, `C90`, `PL`, `W`, `D`, `I`, `UP`. Pydocstyle convention `google`. Ignore `D203`, `D213` (mutually exclusive with the convention's defaults).

**Per-file ignores**: `tests/**` ignores `S101` (assert) and `D` (docstrings); `__init__.py` ignores `F401` (re-exports).

### 8.3 `bandit` (security)

**Why**: standard SAST for Python. Filters with `-ll -ii` (≥ MEDIUM severity AND ≥ MEDIUM confidence) cut the long tail of low-confidence advisories. The no-auto-fix blacklist (§4.6) prevents silent rewrites of intent-bearing findings.

### 8.4 `pyright` (type checking)

**Why**: configured by `proj-init` as a baseline (`[tool.pyright]` fragment) but not gated by `/bt-ai:preflight`. The team chose to make types observable without making them blocking. Verified at install time in step D.

### 8.5 `pytest` + `pytest-cov`

**Why**: industry default; `pytest --collect-only` is what the parent uses to verify generated tests load before exiting `gen-tests`. The pytest fragment enables `--strict-markers --strict-config` to catch typos in marker names early.

### 8.6 `gitlint-core` (commit message lint)

**Why**: enforces Conventional Commits 1.0 in the preflight commit-message gate.

**Why `gitlint-core` and not `gitlint`**: `gitlint` depends on the `sh` package, which depends on the `fcntl` Python module. `fcntl` is Unix-only and absent on Windows. `uv add --dev gitlint` fails to build on Windows with `consider adding fcntl to its build-system.requires`. `gitlint-core` is the dependency-light variant maintained by the same project; it exposes the same `gitlint` CLI. Verified with `uv run gitlint --version` → `gitlint, version 0.19.1`.

### 8.7 `gh` (GitHub CLI)

**Why**: used by `/bt-ai:commit-push-pr` for `gh pr create`, `gh repo view`, `gh auth status`. Authoritative for PR creation; respects user's existing auth. Pre-flight in `commit-push-pr` and step 8 of `preflight` halt if `gh auth status` fails — no silent retry.

### 8.8 Conventional Commits 1.0

**Why**: the type prefix (`feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`) drives:
- branch slug derivation in `commit-push-pr` (`<type>/<slug>`),
- doc-sync routing inferences,
- changelog generation downstream.

Validation runs locally via `gitlint`; commit-push-pr also runs gitlint indirectly via the pre-commit hook if installed.

### 8.9 Plugin-level conventions

- All skills set `allowed-tools` minimally (Bash + Read + Glob, plus Edit on the two skills that apply patches: `doc-sync`, `readme-sync`).
- Slash commands use scoped `Bash(git status:*)`-style allowlists; they cannot run arbitrary shell.
- Subagents declare specific `tools` in frontmatter; `doc-patcher` and `readme-patcher` cannot write files at all.
- Every skill uses `${CLAUDE_PLUGIN_ROOT}/templates` (absolute) instead of relative `templates/` so it is independent of the user's current directory.

---

## 9. What is **not** in scope

The plugin deliberately does not:

- create `.pre-commit-config.yaml`;
- create CI workflows under `.github/workflows/`;
- create `Dockerfile` or `Makefile`;
- enforce branch protection rules;
- enforce commit-author signing;
- run `pyright` or `pytest-cov` as gates inside `preflight`;
- mock or stub the user's environment when running the validation suite — pytest runs against the real environment as configured by `uv sync`.

These exclusions are by design. Each one was a separate decision; the user opted out so the plugin could stay small and unopinionated about deployment.

---

## 10. Constraints, edge cases, and known boundaries

### 10.1 Hard constraints

- **Silent execution** is enforced in SKILL.md prose; the model may not narrate.
- **No `--no-verify`** anywhere in the commit/push commands. Pre-commit hook failures are surfaced.
- **No force-push**. `commit-push-pr` step 3 explicitly does not pass `--force`.
- **Subagents cannot edit source code** outside their narrow allowlist (e.g., `test-writer` is forbidden from modifying `source_path`; `doc-patcher`/`readme-patcher` cannot write at all).
- **Bandit blacklist enforced twice** (parent + agent) for defence in depth.

### 10.2 Edge cases handled

| Scenario | Component | Behaviour |
|----------|-----------|-----------|
| Fresh repo, no commits | All diff-driven skills | Union pattern returns untracked files; no `fatal: bad revision 'HEAD'` |
| `pyproject.toml` malformed | `proj-init` | `tomllib.load` check; abort with `proj-init aborted: pyproject.toml is malformed.` |
| `.gitignore` already has `__pycache__/` | `proj-init` | Skip append |
| `[tool.ruff]` already exists | `proj-init` | Prompt `[k]/[m]/[r]`, default merge |
| `.git/` absent | `proj-init` | Continue; output `Note: .git/ absent — gitlint config dropped but inactive.` |
| Network failure on `uv add` | `proj-init` | Exit non-zero with stderr |
| Re-run on already-initialised project | `proj-init` | All targets identical → `proj-init complete. (no changes)` |
| Empty changed-files list | check-style, security | `No changed .py files.` exit 0 |
| All findings BLOCKED | security | No prompt; direct halt |
| All findings already covered by tests | gen-tests | `All changed files already have tests.` exit 0 |
| Pytest collection fails on generated tests | gen-tests | Surface output verbatim, exit non-zero, no auto-rewrite |
| Diff > 500 lines | doc-sync | Capped at 500; agent works on the head |
| Patch fails to apply | doc-sync, readme-sync | Print failure, continue with rest (doc-sync) or halt (readme-sync) |
| All signals false | readme-sync | `No README change needed.` |
| User declines a sub-skill prompt during preflight | preflight | Sub-skill exits non-zero → preflight halts at that step |
| `.git/COMMIT_EDITMSG` exists from prior failed run | preflight step 7 / commit-push-pr | Overwritten / consumed |
| `gh` not authenticated | commit-push-pr | `gh auth required: run gh auth login.` exit non-zero |
| Pre-commit hook rejects | commit, commit-push-pr | Surface verbatim; no `--no-verify` |
| PR already exists for branch | commit-push-pr | Extract URL from `gh` error, exit 0 |

### 10.3 Known boundaries (not gaps in implementation, but limits of scope)

These came out of empirical testing on a real third-party project (FastAPI codebase, ~200 .py files, Poetry-managed):

- The plugin is **uv-only**; on Poetry projects step A produces a dual-managed dev dependency state. No detection currently warns the user.
- The ruff fragment has no default `extend-exclude` for **generated code** (ANTLR parsers, protobuf stubs, etc.). Projects with generated files will see `F405`-style critical errors and need to add per-file ignores manually.
- `gen-tests` symbol extraction described in SKILL.md uses `ast.FunctionDef` and `grep '^def '`; **`async def`** is not in either. FastAPI endpoints are silently skipped.
- The `package_name` for test imports is read from `[project] name`; multi-namespace projects (where `from src.X` and `from <pkg>.Y` coexist) may receive incorrect imports.
- `doc-sync` is hardcoded to `docs/`. Projects with root-level docs are not covered.
- `readme-sync`'s `deps_added` regex (`^[+-]\s*"[a-zA-Z]`) can false-fire on `authors`, `classifiers`, or `keywords` array changes.
- `security-fixer`'s per-code action table reports B104 (bind to `0.0.0.0`) instead of fixing — this is intentional, but the parent's blacklist does not include B104, so the prompt still appears as `[FIXABLE]`.

These boundaries are observable from the outside; an external code review surfaced them. They are documented here as the honest limits of v0.0.0.

---

## 11. Internal traceability

| Artefact | Where it lives | Owner |
|----------|----------------|-------|
| Original contract | `DESIGN.md` (~700 lines) | shapsha-lemans |
| Plugin manifest | `.claude-plugin/plugin.json` | this plugin |
| Marketplace manifest | `.claude-plugin/marketplace.json` | this plugin |
| Skill specifications | `skills/<skill>/SKILL.md` (×7) | this plugin |
| Subagent specifications | `agents/<agent>.md` (×5) | this plugin |
| Slash command specifications | `commands/<cmd>.md` (×2) | this plugin |
| Templates | `templates/**` | this plugin |
| External observation report | conversation history | most recent run |

The plugin has been smoke-tested:

- in a sandbox (`C:\retrodoc\bt-ai-smoke`) with seeded violations (B006, B307, F821) — all detected by the engines at the configured thresholds;
- against a real third-party project (`C:\retrodoc\skills-BT-AI\retrodoc`, FastAPI/Poetry, 200 source files) — all silent no-op paths verified, all pre-flight aborts verified, plus the boundaries listed in §10.3.

What is **not yet runtime-tested** (requires interactive `/plugin install` in a Claude Code session):

- `disable-model-invocation: true` enforcement;
- `${CLAUDE_PLUGIN_ROOT}` resolution;
- `Task` delegation to the five subagents;
- `AskUserQuestion` rendering;
- the `.git/COMMIT_EDITMSG` handoff between `preflight` step 7 and `commit-push-pr` step 2.

These are runtime-host concerns, not shell-logic concerns.

---

## 12. Versioning

Current: `0.0.0`. Bump policy:

- patch (`0.0.x`) for bug fixes that do not change skill surface or output format;
- minor (`0.x.0`) for new skills or new options on existing skills;
- major (`x.0.0`) for changes to severity buckets, blacklist, or any backwards-incompatible output format change.

The version is declared once in `.claude-plugin/plugin.json`. Skills do not embed it.
