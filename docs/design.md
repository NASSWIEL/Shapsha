# `starter` plugin — implementation documentation

**Plugin name**: `starter`
**Marketplace**: `Shapsha` (single-plugin marketplace, layout: plugin at repo root)
**Author**: shapsha-lemans <shapsha-lemans@cgi.com>
**License**: Proprietary
**Version**: 2.0.0
**Distribution**: git clone + `/plugin install` from `https://github.com/NASSWIEL/bt-ai-plugin`

This document records what is implemented, the workflow it produces, the methodology behind the choices, the use-cases each component serves, and the rationale for every tool the plugin depends on. It is a runtime reference: a contributor or auditor should be able to read this single file and understand the surface, the contracts, and the trade-offs.

---

## 1. Purpose

`starter` standardises Python engineering practice for the BT-AI team at CGI. It bundles seven model-invokable skills, two deterministic slash commands, six focused subagents (five active, one retained but unused), and a set of project templates so that new repositories start on the same footing and changes are validated with the same gates before reaching `main`.

The plugin's key design principle across all v2.0 changes is **zero silent drops**: every finding — whether from a linter, a security scanner, or an LLM-native analysis pass — either gets fixed automatically, fixed with user consent, or refused with a structured reason. Nothing is labelled "advisory" and left without a proposed fix.

The plugin's design intent is threefold:

1. **Lower the cost of doing the right thing**: linting, security scanning, test generation, doc sync, README sync, commit hygiene, and PR creation are all behind one-line slash commands.
2. **Keep the cost of getting it wrong**: auto-fix is scoped to changes that cannot alter program behaviour; consent is required before security fixes and before modifying source code to satisfy generated tests; everything else is auto-fixed (the model tries to fix ALL findings — if it genuinely can't, it refuses with a reason).
3. **Stay fast on multi-file work**: when several files need the same kind of mutation (per-file style fixes, per-file security fixes, per-file test generation, per-doc patching), the parent skill fans out one subagent per file in a single message. Subagents run in parallel; aggregate results come back as JSON.

---

## 2. Repository layout

```
skills-BT-AI/                                 ← marketplace = plugin
├── .claude-plugin/
│   ├── marketplace.json                      ← marketplace manifest
│   └── plugin.json                           ← plugin manifest
├── commands/                                 ← deterministic shell, no model judgement
│   ├── commit.md                             → /starter:commit
│   └── commit-push-pr.md                     → /starter:commit-push-pr
├── skills/                                   ← model-invokable, all disable-model-invocation: true
│   ├── check-style/SKILL.md                  → /starter:check-style
│   ├── security/SKILL.md                     → /starter:security
│   ├── gen-tests/SKILL.md                    → /starter:gen-tests
│   ├── doc-sync/SKILL.md                     → /starter:doc-sync
│   ├── readme-sync/SKILL.md                  → /starter:readme-sync
│   ├── preflight/SKILL.md                    → /starter:preflight
│   └── proj-init/SKILL.md                    → /starter:proj-init
├── agents/                                   ← silent subagents, isolated context
│   ├── style-fixer.md
│   ├── security-fixer.md
│   ├── test-writer.md
│   ├── test-fixer.md
│   ├── doc-patcher.md
│   └── readme-patcher.md
├── templates/                                ← copied verbatim by /starter:proj-init
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
├── README.md                                 ← French, plugin-installer-facing
├── LICENSE
└── DESIGN.md                                 ← original contract document
```

Two manifests describe the marketplace and the plugin separately. `marketplace.json` lists `starter` as the only plugin (source `.`); `plugin.json` declares folders for `skills`, `agents`, and `commands`.

---

## 3. Locked design decisions

| # | Decision | Value |
|---|----------|-------|
| Plugin name | `starter` (slash prefix) | `/starter:<skill>` |
| Marketplace name | `Shapsha` | repo + folder |
| Layout | plugin at repo root | single-plugin marketplace |
| Distribution | git clone + `/plugin install` | personal GitHub |
| Python toolchain | `venv` (via `uv`) **or** `poetry`, chosen at `proj-init` time | `ruff`, `bandit`, `pyright`, `pytest`, `pytest-cov`, `gitlint-core` |
| Runner persistence | `[tool.starter].runner = "venv"|"poetry"` in `pyproject.toml` | resolved by `tools/resolve_runner.py` (`venv` maps to `uv` internally) |
| Plugin repo README | French (dev-facing) | |
| Template README (proj-init drops) | French (user project) | |
| Doc templates | French | |
| Commit messages | English | Conventional Commits 1.0 |
| PR body | English subject, French body, 1–3 short bullets | one bullet per substantive change |
| Branch naming | `<type>/<slug>` | enforced at step 1 of `commit-push-pr` |
| Severity buckets (ruff) | No buckets — all remaining findings go to the model. Ruff fixes everything it can in Pass 1; the model fixes everything else in Pass 2 (refuses with reason only when genuinely ambiguous) |
| Bandit threshold | All levels — no severity or confidence filter (no `-ll -ii`) |
| Bandit fix approach | Every finding gets a concrete fix proposal; consent once; fan-out fixes all (see §4.6) |
| Test location | `tests/foo/test_bar.py` mirroring `src/foo/bar.py` |
| Silent execution | mandatory for individual skills — no narration between tool calls. `preflight` is the exception: it emits large separators (`===…===`) between steps and a one-sentence narration before every Bash command so the user can track multi-skill progress in real time. |
| Skill auto-invocation | disabled — `disable-model-invocation: true` everywhere |
| Consent before edits | `security`: consent once before fan-out (bandit + LLM findings merged). `gen-tests`: consent before modifying source code to satisfy failing tests. `check-style` Step 5: consent before the parent applies fixes that `style-fixer` refused (refused ≠ advisory — proposed fixes are always shown). `doc-sync`/`readme-sync` auto-apply without consent. |
| Per-file fan-out | `check-style`, `security`, `gen-tests`, `doc-sync` each issue all `Task` calls in a single message (≤10 per batch) |

---

## 4. Methodology

### 4.1 Three-tier component split

The plugin separates **deterministic shell** (slash commands), **rule-driven branching with prompts** (skills), and **isolated text-mutating reasoning** (subagents). Each tier has different guarantees:

| Tier | Component | Tooling | Determinism | Allowed reasoning |
|------|-----------|---------|-------------|-------------------|
| 1 | Slash commands | Bash only, allowlisted | Fully deterministic | None — pure text composition from diffs |
| 2 | Skills | Allowlisted Bash (`git`, runner, plugin tools) + Read + Edit/MultiEdit/Grep where needed + `Task` for fan-out | Branches on shell output | Pre-flight, classification, fix proposals, consent prompts, fan-out orchestration |
| 3 | Subagents | Read + Edit/MultiEdit (and Glob/Grep/Bash where the task needs it, e.g. `test-writer` needs pytest collection) | Free within tool allowlist | Per-file edits: docstrings, renames, security fixes, tests, doc patches, README patches |

This layering is what makes `Silent execution` achievable: the user-visible turn is dominated by the parent skill's single-line summary, while the reasoning happens inside isolated subagents whose intermediate context never reaches the parent. Subagents return one line of structured JSON; the parent aggregates and emits the final summary.

### 4.2 Silent-by-design

Every skill declares `**Silent.**` as the first paragraph after `## Operating mode`. The model is instructed not to emit per-step narration. Diagnostics are produced by `!` bash interpolation; the model only emits the final summary block. This avoids two real problems:

- conversational noise in CI-like workflows, and
- token bloat from intermediate progress messages.

### 4.3 No automatic model invocation

Every SKILL.md uses `disable-model-invocation: true`. The model never decides to run `check-style` on its own; the user must type `/starter:check-style`. This is a safety property: skills perform actions (file edits, commits, PRs), and surprise invocation is a foot-gun.

### 4.4 Diff-driven scope

Five skills (`check-style`, `security`, `gen-tests` diff mode, `doc-sync`, `readme-sync`) all start by computing the union of:

- `git diff --name-only --diff-filter=ACMR` (unstaged tracked changes)
- `git diff --cached --name-only --diff-filter=ACMR` (staged tracked changes)
- `git ls-files --others --exclude-standard` (untracked files)

This pattern is necessary because:

- `git diff HEAD` alone fails on **fresh repos** with `fatal: bad revision 'HEAD'`.
- `git diff` alone misses **untracked files**, which on a fresh feature branch are exactly the files the user wants validated.

The pattern is verified across all five skills.

### 4.5 Two-pass architecture: ruff first, model second

`check-style` never halts — everything is either fixed or refused with a reason. No advisory bucket. The architecture uses ruff for cheap mechanical fixes, then the LLM for intelligent fixes ruff can't handle.

**Pass 1 — ruff fixes everything it can:** `ruff check --fix --unsafe-fixes` with all enabled codes, then `ruff format`. This handles F401 (unused import), F541 (f-string without placeholders), F841 (unused variable), E/W/I/UP, D-fixable, B007/B009/B010/B011, and every other code ruff knows how to fix. One shell call, zero LLM tokens.

**Pass 2 — re-scan, fix ALL remaining with the model.** No classification into buckets — every remaining finding goes to the model. `D1xx` (docstrings), `N8xx` (renames), `F821` (undefined name), `E999` (syntax error), `S*` (security), `C90*` (complexity — refactored by extracting helpers), `PL*` (pylint — refactored or fixed), and any other code. Per-file work fans out to `style-fixer` subagents; cross-file renames (N801/N802) handled by parent via Grep + MultiEdit. If the model genuinely cannot fix something, it refuses with a structured reason — but it tries first.

**Display rule**: every remaining finding is preceded by a `----------------------------------` separator and rendered as a 3-line code snippet with an `→ action` line. All findings go to `style-fixer` — there is no pre-fan-out advisory split.

**Step 5 — refused findings with consent**: after the fan-out completes, any items in `agent_refused[]` are shown in a `===…===` block with a concrete proposed fix per item. The parent calls `AskUserQuestion` once (`Apply fixes for these N issue(s)?`). On `Yes`, the parent applies the fixes directly via `Edit`/`MultiEdit` and stages the touched files. On `No`, refused items appear in the final summary as remaining. The final summary reports: `auto-fixed / consent-fixed / remaining`.

### 4.6 Two-pass security: bandit + LLM-native analysis, consent once

**Pass 1 — bandit**: scans **all severity and confidence levels** — no `-ll -ii` filter. Results → `bandit_findings[]`. B101 assertions in test files are filtered out (pytest uses `assert` by design).

**Pass 2 — LLM-native analysis**: after the bandit pass, the parent reads each file and reasons about six categories of issues that static analysis cannot detect. Only HIGH-confidence (≥80%) findings are included:

| Tag | Category |
|---|---|
| `LLM-AUTH` | Missing access checks, IDOR, privilege escalation |
| `LLM-INJECTION` | Untrusted input → shell / SQL / eval / template / file path (source-to-sink tracing) |
| `LLM-LOGIC` | TOCTOU, race conditions, missing negative/zero validation |
| `LLM-SECRET` | Hardcoded API keys, JWT secrets, bearer tokens that bandit missed |
| `LLM-CRYPTO` | Hardcoded IVs/nonces, ECB mode, `random.seed(constant)` for security context |
| `LLM-SECOND-ORDER` | Data written to persistent storage that will later be deserialized/rendered without sanitization |

LLM findings are deduplicated against bandit results by `(filename, line)`. They are merged into `all_findings[] = bandit_findings[] + llm_findings[]`.

**Single consent**: the parent shows all findings (`B` from bandit, `L` from LLM) with `[severity/confidence] … → Proposed fix:` and calls `AskUserQuestion` **once** for the whole batch.

On `Yes`, the parent fans out one `security-fixer` subagent per file. The agent handles both B-codes and `LLM-*` tags identically (follows the `proposed` field). Refuses only when genuinely ambiguous:
- `B102` with dynamic user input → `exec-with-dynamic-input`;
- `B301`/`B302`/`B306` with complex objects → `pickle-for-complex-objects`;
- `B608` with unidentifiable DB driver → `unknown-db-driver`;
- Shell with pipes/redirects/`&&` → `complex-shell-syntax`;
- Anything the agent cannot safely resolve → `ambiguous-fix`.

Refused items surface in the final summary. On `No`, nothing is modified.

### 4.7 Subagent context isolation and parallel fan-out

Six subagents are invoked via `Task`. Each runs in a separate context window. This produces four concrete benefits:

1. **Targeted reads.** The subagent reads only the files it needs (e.g., `doc-patcher` reads `index.md` always, then only the impacted docs from a 6-doc set). Reading 4 unrelated docs would otherwise pollute the parent context.
2. **Structured input/output.** The subagent receives a typed JSON payload, not the full diff text history. The parent's earlier turns stay clean. The subagent returns a single line of JSON the parent aggregates.
3. **Narrow tool allowlist.** Each agent's `tools` line lists only what it needs. None can call `Bash` for git/network operations except `test-writer`, which needs pytest collection. Subagents never run `git`, `gh`, or any side-effecting shell command — staging and re-verification belong to the parent.
4. **Parallelism.** When several files need the same kind of mutation, the parent issues one `Task` call per file **in a single message**. Claude Code runs them in parallel up to a cap of 10 per message; for G > 10 groups, the parent splits across consecutive messages of 10. This keeps multi-file work latency proportional to the slowest single-file call, not to the sum.

### 4.7.1 Why per-file fan-out and not per-finding

Two related but inferior architectures were rejected:

- **Per-finding fan-out** (one subagent per ruff/bandit finding): blows past the 10-call cap on any non-trivial diff and forces the same file to be opened by N agents that conflict on writes.
- **One mega-agent** (single subagent receives all findings for all files): defeats the parallelism, and a single overloaded context produces lower-quality docstrings/renames than N small focused contexts.

Per-file fan-out is the sweet spot: agents never conflict on writes (one owner per file), and parallelism is bounded by file count, not finding count.

### 4.8 Hybrid file-creation policy

`/starter:proj-init` does not blindly overwrite. For each managed file:

- **Absent** → create from template.
- **Identical to template** → skip silently.
- **Differs from template** → `AskUserQuestion` with three options: `keep` / `overwrite` (with `.bak`) / `diff` (show, then re-ask).

For `pyproject.toml` specifically, fragment-merging is offered: only sections missing in the target are appended; existing sections are preserved by default. This keeps proj-init re-runnable.

### 4.9 Pre-validated commit messages via `.git/COMMIT_EDITMSG`

`/starter:preflight` step 7 composes a Conventional Commit message from the staged diff and validates it through `gitlint --staged --msg-stdin`. On success, the message is written to `.git/COMMIT_EDITMSG`. Step 8 then invokes `/starter:commit-push-pr`, which detects the file and uses `git commit -F .git/COMMIT_EDITMSG`, then `rm -f`s it. This handoff path was chosen over arguments because:

- it is robust to the user inspecting the message between preflight and the commit,
- it is recoverable: if step 8 fails, the file is cleaned up by preflight before the halt message so a retry always composes a fresh message,
- it adds zero new flags to the commit-push-pr surface.

Step 7 also removes any stale `.git/COMMIT_EDITMSG` at its start (before composing the new message) so a previous failed run can never leak its message into the current run.

---

## 5. Component reference

### 5.1 Slash commands (deterministic)

#### `/starter:commit`

**Use case**: produce a Conventional Commit on already-staged changes, English, no PR.

**Inputs**: staged diff, recent commit subjects (style reference).

**Behaviour**: composes a `<type>(<scope>?): <subject>` line under 72 chars, optional body wrapped at 100; commits via heredoc to preserve formatting.

**Output**: `<short-hash> <subject>` on success.

**Tool allowlist**: `git add`, `git status`, `git diff`, `git commit`, `git log`. No `--no-verify`. Pre-commit hook rejection is surfaced verbatim.

#### `/starter:commit-push-pr`

**Use case**: end-to-end "ship a feature": branch creation if on default branch, commit, push, PR.

**Branch handling**: if on `main`/`master`, derive `<type>/<slug>` (kebab-case, ≤5 words) from the diff and `git checkout -b`.

**Commit handling**: if `.git/COMMIT_EDITMSG` exists and is non-empty (preflight wrote it), commit via `-F` and clear the file; otherwise compose fresh.

**Push**: `git push -u origin <branch>`. No force-push.

**PR**: title = commit subject (English, Conventional Commit format). Body in **French**, **exactly 1 to 3 bullet points** — no section titles, no prose, no checklist. Each bullet is factual and derived from the staged diff. Created via `gh pr create`.

**Tool allowlist**: scoped to `git`, `gh pr create`, `gh repo view`, `gh auth status`, `test`, `cat`, `rm`. No broader shell.

### 5.2 Skills

#### `/starter:check-style`

**Use case**: lint changed Python files; auto-fix everything possible, never halt, never prompt.

**Two-pass architecture** (see §4.5): Pass 1 runs `<runner> run ruff check --fix --unsafe-fixes` followed by `<runner> run ruff format` — ruff fixes everything it can (cheap, no LLM tokens). Pass 2 re-scans with `--output-format=json --no-fix` and sends ALL remaining findings to the model — no advisory bucket. `--force-exclude` is always passed so `[tool.ruff].extend-exclude` applies to explicit file lists.

**Display**: every remaining finding is preceded by a `----------------------------------` separator and rendered as a 3-line code snippet + `→ action` line. No pre-fan-out split into advisory/non-advisory categories — all findings are displayed uniformly. Refused findings are shown only after the fan-out, in Step 5.

**Decision point** (never halts):
- No remaining findings → `Style: no findings (ruff fixed everything).` exit 0.
- Findings remain → display all with separators, snippets, and action lines, then **immediately run the fix sequence** (no consent before Step 5).

**Fix sequence**:
1. All findings per-file → fan-out: one `style-fixer` subagent per impacted file, **all `Task` calls in a single message** (≤10 per batch). Each agent fixes D1xx docstrings, N803/N806 renames, F821 imports, E999 syntax, S* security, C90*/PL* complexity/refactoring, and any other code. Aggregates `docstrings_total`, `renames_local_total`, `code_fixes_total`, `security_fixes_total`, `refactors_total`, `agent_refused[]`, `agent_errors[]`.
2. Cross-file renames (N801 class / N802 function) → handled by the **parent** via `Grep` + per-file `MultiEdit`. Subagents refuse these by design.
3. Re-run ruff to verify.
4. Stage only the files that were actually modified.
5. **Refused findings with consent**: if `agent_refused[]` is non-empty, display a `===…===` block with a concrete proposed fix per item. `AskUserQuestion` once. On `Yes`, parent applies fixes directly via `Edit`/`MultiEdit` and stages. On `No`, refused items are reported as remaining.

**Output**: `Style: <auto_fixed> auto-fixed, <consent_fixed> consent-fixed, <still_remaining> remaining.` (refused reasons listed if any).

#### `/starter:security`

**Use case**: scan changed Python files for security issues using bandit (SAST) + an LLM-native second pass (deep reasoning). Propose fixes for everything, fix on approval.

**Two-pass engine** (see §4.6):
- Pass 1: `<runner> run bandit -f json <files>` — no severity or confidence filter → `bandit_findings[]`. B101 in test files filtered.
- Pass 2: parent reads each file and reasons about 6 categories (LLM-AUTH, LLM-INJECTION, LLM-LOGIC, LLM-SECRET, LLM-CRYPTO, LLM-SECOND-ORDER) — HIGH confidence only → `llm_findings[]`. Merged: `all_findings[]`.

**Decision point**:
- `all_findings[]` empty → continue to auxiliary scans.
- Findings exist → display all `(<B> from bandit, <L> from LLM)` with `[severity/confidence]` prefix + `→ Proposed fix:`. `AskUserQuestion` once.
- `No` → findings reported, nothing modified, stop with success.
- `Yes` → fan-out one `security-fixer` per file (**all `Task` calls in a single message**). Agent handles both B-codes and LLM-* tags. Re-run bandit to verify.

**Auxiliary scans** (run only when installed): `pip-audit --strict` for CVEs; `detect-secrets scan --baseline /dev/null` for hardcoded credentials. Either may report `n/a` if absent.

**Output**: `Security: <applied> fixed, <refused> could not be auto-fixed, <remaining> remaining, <deps_vulns> dependency vuln(s), <secrets_found> potential secret(s).` Segments whose tool is `n/a` are omitted.

#### `/starter:gen-tests`

**Use case**: ensure every public function in a changed file has a corresponding pytest test.

**Three modes**:
- **Diff mode** (no args): scans changed `*.py` excluding `tests/**`.
- **Full sweep** (`all`): every tracked `*.py` excluding `tests/**`.
- **Targeted mode** (`/starter:gen-tests path1 path2 ...`): scans those files/dirs explicitly.

**Path mapping**: `src/foo/bar.py` → `tests/foo/test_bar.py`; `foo/bar.py` (no `src/` prefix) → `tests/foo/test_bar.py`; `pkg.py` at root → `tests/test_pkg.py`.

**Filter**: extracts public top-level functions, **async functions**, and class methods (no underscore prefix); matches against existing `test_*` functions in the corresponding test file; missing-only are forwarded to the agent.

**Fan-out**: per-source-file work — one `test-writer` subagent per source file with missing tests, **all `Task` calls in a single message** (≤10 per batch). Each agent writes its own test file with golden + error + boundary cases.

**Operating mode**: silent — no narration between tool calls. `git add` and `pytest` are always separate Bash calls (never chained — pytest's exit code 1 would mask a successful stage). `test-fixer` is never invoked.

**Verification and triage**: after agents write tests, the parent stages them (`git add`) then runs `pytest -q` in a separate call. Failures are triaged into two categories:

- **Mechanical** (test plumbing bugs — test-writer errors, not source deficiencies): wrong `mock.patch` target path, missing import, wrong fixture, `sys.modules` cross-contamination across test files. Fixed directly in the test file by the parent — no consent needed.
- **Semantic** (real assertion mismatches — source code deficiency): the parent reads the failing test and source, proposes concrete improvements, asks consent once (`AskUserQuestion`), applies to source files via `Edit`/`MultiEdit`, and re-runs (cap 2 iterations). Halt only if failures persist after 2 iterations.

#### `/starter:doc-sync`

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

**Routing**: per-doc work fans out — one `doc-patcher` subagent per impacted doc, all `Task` calls in a single message. Each agent returns a unified diff (or `null` if the doc needs no change). The parent applies the diffs sequentially via `Edit`/`MultiEdit`.

**Auto-apply**: patches are minimal by construction (≤30 % rewrite cap inside the agent, which never invents identifiers and preserves French tone). `doc-sync` therefore applies what comes back without an `AskUserQuestion`. A patch that fails to apply is reported but does not abort the rest.

#### `/starter:readme-sync`

**Use case**: only patch `README.md` when a **user-facing** surface changed.

**Five signals scanned** from staged + unstaged + untracked:
1. `scripts_changed` — `[project.scripts]` entries in `pyproject.toml`.
2. `all_changed` — `__all__` definitions in `*.py`.
3. `env_vars_added` — `os.environ` / `os.getenv` calls added.
4. `deps_added` — dependency lines in `pyproject.toml`.
5. `install_files_changed` — `Dockerfile`, `Makefile`, `pyproject.toml` touched.

**Discipline**: if all flags false → silent no-op. Otherwise, delegate to `readme-patcher`, which edits `README.md` directly via `Edit`/`MultiEdit`. The agent may still return `{"patched": false, "reason": "..."}` if signals fired but no semantics actually changed (e.g., dependency-version-only bump). No `AskUserQuestion`.

**French tone preservation**: hardcoded into the agent prompt.

#### `/starter:preflight`

**Use case**: pre-PR validation suite. Sequential, halt on first failure.

**Eight steps**:
1. `check-style` — two-pass: ruff auto-fixes, then model fixes remaining. Never halts (no prompt).
2. `security` — scans all levels, proposes fixes, asks consent once. Halt if user declines or findings remain after fix.
3. `gen-tests` (diff mode) — halt on collection failure or if tests still fail after 2 iterations of source code improvements.
4. `pytest -q` — halt on test failure; emits the captured tail.
5. `doc-sync` — auto-applies; halt only if a patch fails to apply.
6. `readme-sync` — auto-applies; halt only if the agent reports an error.
7. **Commit message gate**: compose Conventional Commit from staged diff; validate via `gitlint --staged --msg-stdin`; on validation success, write to `.git/COMMIT_EDITMSG`; on failure, prompt for rewrite (one retry).
8. `commit-push-pr` — consumes `.git/COMMIT_EDITMSG` if present.

**Structured output**: preflight is the only skill that emits visual structure. Before each step a large separator block is printed (`===…=== Step N — name ===…===`). Before every Bash command within a step, a one-sentence narration explains what the command does. Small separators (`---…---`) separate sub-actions within a step. On success the final output is a closing separator followed by the PR URL.

**Guards (in order — all pure checks before any side effects)**:
1. not a git repo → halt;
2. nothing staged AND nothing unstaged → halt;
3. `gh` CLI absent → halt;
4. `gh` not authenticated → halt;
5. only unstaged changes (nothing staged) → **auto-stage** with `git add -u` (tracked modified files) + `git ls-files --others --exclude-standard -- '*.py' '*.md' 'pyproject.toml'` (targeted untracked). Scratch files, compiled outputs, and `.env`-type files are left unstaged.

Guard order is critical: `gh` checks (#3/#4) run before auto-stage (#5) so files are never staged when the pipeline cannot complete.

**COMMIT_EDITMSG hygiene**: step 7 removes any stale `.git/COMMIT_EDITMSG` before composing the new message. If step 8 fails, preflight removes the file before the halt line so a retry always recomposes fresh.

**Output**: PR URL on full success; `Halted at step <N>: <reason>.` followed by the failing tool's verbatim output otherwise.

#### `/starter:proj-init`

**Use case**: bootstrap a new (or partly initialised) project with the team's standards.

**STEP 0 — runner detection (mandatory first action)**: the runner is determined before any shell command using this priority table (first match wins):

| Priority | Condition | Action |
|---|---|---|
| 1 | `[tool.starter].runner` already set in `pyproject.toml` | Reuse silently |
| 2 | `.venv/` directory exists (and no poetry markers) | `venv`, no question |
| 3 | `poetry.lock` or `[tool.poetry]` in `pyproject.toml` (no `.venv/`) | `poetry`, no question |
| 4 | Mixed signals | Ask user |
| 5 | Only `requirements.txt` (bare pyproject) | Ask user (migration case) |
| 6 | Bare project | Ask user |

When asking, the call to `AskUserQuestion` is the very first tool call — no Bash or Write precedes it. After the runner is known, the chosen tool is verified on PATH (abort with install URL if absent). The choice is persisted as `[tool.starter].runner = "venv"|"poetry"` in `pyproject.toml`. `venv` is backed by `uv` internally.

**Step 1 — install dev tools**: then:

```
uv add --dev   ruff bandit pyright pytest pytest-cov gitlint-core   # if runner == uv
poetry add --group dev ruff bandit pyright pytest pytest-cov gitlint-core   # if runner == poetry
```

**Step B — config files** (hybrid policy, see §4.8):
- `.gitlint` — copy if absent; merge-prompt if differs.
- `.gitignore` — copy if absent; append the python set if `__pycache__/` token missing.
- `pyproject.toml` — create minimal if absent; for each section (`[tool.ruff]`, `[tool.pyright]`, `[tool.bandit]`, `[tool.pytest.ini_options]`), append-if-absent / skip-if-identical / prompt-if-different.

**Step C — documentation templates**: `cp -n` (no-clobber) for `README.md` and six files under `docs/`. Never overwrites.

**Step D — verification**: runs each tool's `--version`. Failure aborts with which tool failed.

**Step E — explicit non-goals**: no `.pre-commit-config.yaml`, no CI workflows, no `Dockerfile`, no `Makefile`. The team opted out at design time.

### 5.3 Subagents

Six subagents live under `agents/`. Each runs in an isolated context, in silent mode, and returns one line of structured output. All are invoked via `Task` with a typed JSON payload composed by the parent skill.

| Agent | Model | Used by | Tools | Output | Role |
|-------|-------|---------|-------|--------|------|
| `style-fixer` | sonnet | check-style | `Read, Edit, MultiEdit` | `{"file":"...","docstrings":N,"renames_local":N,"code_fixes":N,"security_fixes":N,"refactors":N,"refused":[...],"errors":[]}` | Per-file: fixes ALL ruff codes ruff left behind — docstrings (`D1xx`), renames (`N803`/`N806`), imports (`F821`), syntax (`E999`), security (`S*`), complexity refactoring (`C901`, `PLR*`), and any other code. Refuses only cross-file renames (`N801`/`N802`) and genuinely ambiguous fixes. |
| `security-fixer` | sonnet | security | `Read, Edit, MultiEdit` | `{"file":"...","applied":N,"refused":[{"test_id":"...","line":N,"reason":"..."}],"errors":[]}` | Per-file: apply concrete security fixes for both bandit B-codes (~30 codes: B101→raise, B102→inline/refuse, B105/106/107→env var, B108→tempfile, B201→`debug=False`, B301/302/306→json, B311→`secrets`, B324→sha256, B501–503→`verify=True`, B506→`safe_load`, B602/605/607→arg list, B608→parameterized query, etc.) and LLM-sourced tags (`LLM-AUTH`, `LLM-INJECTION`, `LLM-LOGIC`, `LLM-SECRET`, `LLM-CRYPTO`, `LLM-SECOND-ORDER`). Both types are handled identically: the agent follows the `proposed` field from the parent. Refuses only when genuinely ambiguous. |
| `test-writer` | sonnet | gen-tests | `Read, Write, Edit, MultiEdit, Glob, Bash` | `file=<path> tests_added=<N> omitted=<N> collection_ok=<true\|false>` | Per-source-file: write golden + error + boundary tests for missing public symbols. Key v2.0 additions: (1) `sys.modules.setdefault` pre-mock block for heavy third-party deps before importing the module under test; (2) `sys.modules.pop("<module_under_test>", None)` immediately before the import to prevent cross-contamination from earlier test files in the same pytest session; (3) explicit `mock.patch` formula (`patch("<module_under_test>.<name_as_imported_there>")`); (4) `autospec=True` only when the patch target's parent is a real object — skipped when the parent is already a `MagicMock` from `sys.modules` pre-mocking. Single `Write` or single `MultiEdit` per file. One result line, no narration. |
| `test-fixer` | haiku | *(unused — gen-tests now fixes source code directly)* | `Read, Edit, Glob, Bash` | `{"file":"...","fixed":N,"unfixable":N}` | Repair mechanical pytest failures (missing imports, wrong fixture names, bad arg counts) on test files only. Read-only on source. Retained as a standalone agent but no longer invoked by `gen-tests`; the parent skill now proposes source code improvements when tests fail. |
| `doc-patcher` | sonnet | doc-sync | `Read, Glob, Grep, Edit, MultiEdit` | `{"file":"...","mode":"diff-patch\|template-fill","patched":bool,"reason":"..."}` | Per-doc: update ONE `docs/*.md` in place from code facts and an optional diff. Reads `index.md` plus the impacted doc only — never the full 6-doc set. ≤30 % rewrite cap; never invents identifiers; preserves French tone. |
| `readme-patcher` | sonnet | readme-sync | `Read, Edit, MultiEdit` | `{"patched":bool,"sections_touched":[...]}` or `{"patched":false,"reason":"..."}` | Patches root `README.md` when a user-facing surface changes (CLI entries, env vars, deps). May return `patched:false` if signals fired but no semantics actually changed. Preserves French tone. |

All subagents are **silent**, return a single-line JSON result, and never run `git`, `gh`, or any other side-effecting shell command (the parent skills handle staging and re-verification).

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

---

## 6. End-to-end workflows

### 6.1 New project (greenfield)

```
1. mkdir my-proj && cd my-proj && git init
   (then either: uv init                               → uv pyproject
    or:          poetry init -n && poetry install      → poetry pyproject)
2. /plugin install bt-ai (from the marketplace)
3. /starter:proj-init
   ├─ asks for runner: venv or poetry (always asks)
   ├─ persists [tool.starter].runner in pyproject.toml
   ├─ <runner> add (--dev | --group dev) ruff bandit pyright pytest pytest-cov gitlint-core
   ├─ creates .gitlint, .gitignore, docs/, README.md
   └─ patches pyproject.toml with [tool.ruff], [tool.pyright], [tool.bandit], [tool.pytest.ini_options]
4. write some code
5. /starter:preflight
   ├─ check-style → security → gen-tests → pytest → doc-sync → readme-sync → commit-msg-gate → commit-push-pr
   └─ outputs PR URL
```

### 6.2 Existing project (one-off validation)

```
1. /starter:check-style       (changed files only)
2. /starter:security
3. /starter:gen-tests src/foo (targeted mode — explicit path)
4. /starter:doc-sync          (only if docs/ exists)
5. /starter:readme-sync
6. /starter:commit            (or /starter:commit-push-pr for the full path)
```

### 6.3 Iterative loop during a feature

```
edit code → /starter:check-style → fix → /starter:security → fix → /starter:gen-tests → ... → /starter:preflight
```

Each individual skill is independent and idempotent. `/starter:preflight` re-runs them all in order; passing intermediate skills is cheap because diff-driven scope is small.

---

## 7. Use cases handled

| Use case | Skill / command | How it is handled |
|---|---|---|
| New repo bootstrap | `proj-init` | Step A always asks for runner (venv/poetry) and installs tools; B drops configs; C drops docs; D verifies |
| Fix lint on what I just changed | `check-style` | Diff-driven scope; two-pass (ruff first, model second); fan-out `style-fixer` for D1xx + N803/N806 + F821 + E999; parent handles N801/N802 cross-file; never halts |
| Security audit on what I just changed | `security` | Bandit all-level scan (Pass 1) + LLM-native analysis on 6 categories HIGH confidence only (Pass 2); merged findings; consent prompt once; fan-out `security-fixer` per file; agent handles B-codes and LLM-* tags |
| Tests for a new function | `gen-tests` (targeted) | Symbol extraction (incl. async def) → missing-only → fan-out `test-writer`; pytest verify → if failures, propose source code improvements (consent once, cap 2 iterations) |
| Tests for whole feature branch | `gen-tests` (diff mode) | Same as above but scope = all changed `.py` |
| Doc drift on architecture/data-model | `doc-sync` | Routing matrix; fan-out one `doc-patcher` per impacted doc; auto-applies returned patches |
| README drift after API surface change | `readme-sync` | Five signals; `readme-patcher` patches `README.md` directly; auto-applies |
| Quick commit on staged changes | `commit` | Compose Conventional Commit, validate, commit |
| Branch + commit + push + PR | `commit-push-pr` | Branch from default; English title + French 1–3-bullet body |
| Full pre-PR gate | `preflight` | All seven skills sequentially + commit-push-pr; structured output with `===…===` step separators and narration sentences; auto-stages unstaged changes after gh guards pass |
| Unstaged changes at preflight entry | `preflight` | Auto-staged with `git add -u` + targeted untracked (`.py`, `.md`, `pyproject.toml`) after all guards pass — scratch files and temp outputs left out |
| check-style refused findings remain | `check-style` Step 5 | `===…===` block with proposed fix per item; `AskUserQuestion`; parent applies directly on Yes |
| Re-run on already-initialised project | `proj-init` | Hybrid policy (skip-if-identical, ask-if-conflict, create-if-missing) |
| Fresh repo (no commits yet) | All diff-driven skills | Union pattern: `git diff` ∪ `git diff --cached` ∪ `git ls-files --others` |
| Untracked files with new code | All diff-driven skills | Same union pattern catches them |
| Pre-commit hook rejection | `commit`, `commit-push-pr` | Surface failure; never `--no-verify` |
| User on default branch | `commit-push-pr` | Auto-creates `<type>/<slug>` branch |
| Stale `.git/COMMIT_EDITMSG` | `preflight` step 7 | Removed at start of step 7 before composing new message; also removed by preflight on step 8 failure so retry recomposes fresh |
| All findings already fixed / nothing to do | every skill | Silent no-op summary, exit 0 |

---

## 8. Tool choices and justifications

### 8.1 `venv` (via `uv`) or `poetry` (package manager)

**Why both**: `proj-init` always asks the user to choose between `venv` and `poetry`, persists the choice in `[tool.starter].runner`, and every subsequent skill resolves the runner via `tools/resolve_runner.py`. `venv` is backed by `uv` internally — `uv` manages standard virtual environments and runs tools via `uv run <tool>`. `poetry` uses `poetry run <tool>`. Hatch and PDM are not currently supported.

**Why a runner key in `pyproject.toml`**: the alternative — re-detecting at every skill invocation by inspecting lockfiles — is brittle (a project may have stale `uv.lock` next to a fresh `poetry.lock` during a migration). Persisting the user's explicit choice removes the ambiguity.

**Trade-off**: a project that switches from one to the other manually (without re-running `proj-init`) will keep the old runner until `[tool.starter].runner` is edited. This is intentional — `proj-init` is the only place the runner can change.

### 8.2 `ruff` (lint + format)

**Why**: replaces flake8 / pycodestyle / pydocstyle / isort / pyupgrade / black with one binary. JSON output is stable and parseable; severity classification (§4.5) is by rule prefix.

**Configured rule families** (`[tool.ruff.lint] select`): `E`, `F`, `B`, `S`, `N`, `C90`, `PL`, `W`, `D`, `I`, `UP`. Pydocstyle convention `google`. Ignore `D203`, `D213` (mutually exclusive with the convention's defaults).

**Per-file ignores**: `tests/**` ignores `S101` (assert) and `D` (docstrings); `__init__.py` ignores `F401` (re-exports).

### 8.3 `bandit` (security)

**Why**: standard SAST for Python. Scans all severity and confidence levels — no filter. Every finding gets a concrete fix proposal grounded in the actual source code. The `security-fixer` agent tries to fix everything and only refuses when it genuinely cannot determine a safe replacement (§4.6), so a `Yes` to the consent prompt maximises automated remediation.

**Auxiliary scanners**: `pip-audit` (dependency CVEs) and `detect-secrets` (hardcoded credentials in changed files) run opportunistically when installed, advisory only — they never halt.

### 8.4 `pyright` (type checking)

**Why**: configured by `proj-init` as a baseline (`[tool.pyright]` fragment) but not gated by `/starter:preflight`. The team chose to make types observable without making them blocking. Verified at install time in step D.

### 8.5 `pytest` + `pytest-cov`

**Why**: industry default; `pytest -q` is what the parent uses to verify generated tests pass after exiting the test-writer fan-out. On test failure, the parent proposes source code improvements (tests are the truth — the source is fixed, not the tests), asks consent once, and applies changes (cap 2 iterations). The pytest fragment enables `--strict-markers --strict-config` to catch typos in marker names early.

### 8.6 `gitlint-core` (commit message lint)

**Why**: enforces Conventional Commits 1.0 in the preflight commit-message gate.

**Why `gitlint-core` and not `gitlint`**: `gitlint` depends on the `sh` package, which depends on the `fcntl` Python module. `fcntl` is Unix-only and absent on Windows. Installing `gitlint` (via `uv add --dev gitlint` or `poetry add --group dev gitlint`) fails to build on Windows with `consider adding fcntl to its build-system.requires`. `gitlint-core` is the dependency-light variant maintained by the same project; it exposes the same `gitlint` CLI. Verified with `<runner> run gitlint --version` → `gitlint, version 0.19.1`.

### 8.7 `gh` (GitHub CLI)

**Why**: used by `/starter:commit-push-pr` for `gh pr create`, `gh repo view`, `gh auth status`. Authoritative for PR creation; respects user's existing auth. Pre-flight in `commit-push-pr` and step 8 of `preflight` halt if `gh auth status` fails — no silent retry.

### 8.8 Conventional Commits 1.0

**Why**: the type prefix (`feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`) drives:
- branch slug derivation in `commit-push-pr` (`<type>/<slug>`),
- doc-sync routing inferences,
- changelog generation downstream.

Validation runs locally via `gitlint`; commit-push-pr also runs gitlint indirectly via the pre-commit hook if installed.

### 8.9 Plugin-level conventions

- Skills set `allowed-tools` minimally — typically scoped `Bash(git ...:*)` + scoped `Bash(<runner> ...:*)` + `Read`, plus `Edit`/`MultiEdit`/`Grep` only when the skill itself applies cross-file edits (currently `check-style` for N801/N802 renames).
- Slash commands use scoped `Bash(git status:*)`-style allowlists; they cannot run arbitrary shell.
- Subagents declare specific `tools` in frontmatter — each one only what its job requires. `Task` is implicit on the parent skill side; subagents cannot spawn further subagents.
- Hermetic plugin code: every helper Python script lives under `${CLAUDE_PLUGIN_ROOT}/tools/`. Skills never write classifier scripts, scratch JSON, or log files into the user's repo.
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
- mock or stub the user's environment when running the validation suite — pytest runs against the real environment as configured by the chosen runner (`uv sync` / `poetry install`).

These exclusions are by design. Each one was a separate decision; the user opted out so the plugin could stay small and unopinionated about deployment.

---

## 10. Constraints, edge cases, and known boundaries

### 10.1 Hard constraints

- **Silent execution** is enforced in SKILL.md prose for all individual skills; the model may not narrate. `preflight` is the deliberate exception: it emits structured separators and one narration sentence per Bash command.
- **No `--no-verify`** anywhere in the commit/push commands. Pre-commit hook failures are surfaced.
- **No force-push**. `commit-push-pr` step 3 explicitly does not pass `--force`.
- **One file per subagent.** Each fan-out agent edits exactly the file in its input — never another. Forbidden by the agent's hard rules; would cause write conflicts when the parent issues N parallel `Task` calls.
- **Subagents do not run `git`/`gh`.** Staging, re-verification, and PR creation are the parent's job. Only `test-writer` uses `Bash` (for pytest collection).
- **Try everything, refuse only when ambiguous.** `security-fixer` attempts every finding — both B-codes and LLM-* tags. Refuses only when genuinely ambiguous. Refused items surface in `refused[]` with structured reasons.
- **Consent gates.** `security`: consent once before fan-out. `gen-tests`: consent before modifying source code. `check-style` Step 5: consent before parent applies refused findings. `doc-sync`/`readme-sync`: no consent.
- **No advisory bucket.** Every finding in every skill either gets an automatic fix, a consent-gated fix, or a refusal with a structured reason. Nothing is labelled "advisory" and left without a proposed fix.
- **gen-tests stage and verify in separate Bash calls.** Never chained — pytest's exit code 1 would mask a successful `git add`.
- **gen-tests never invokes test-fixer.** Mechanical test failures are fixed directly by the parent in the test file. Semantic failures trigger source code improvement with user consent.

### 10.2 Edge cases handled

| Scenario | Component | Behaviour |
|----------|-----------|-----------|
| Fresh repo, no commits | All diff-driven skills | Union pattern returns untracked files; no `fatal: bad revision 'HEAD'` |
| `pyproject.toml` malformed | `proj-init` | `tomllib.load` check; abort with `proj-init aborted: pyproject.toml is malformed.` |
| `.gitignore` already has `__pycache__/` | `proj-init` | Skip append |
| `[tool.ruff]` already exists | `proj-init` | Prompt `[k]/[m]/[r]`, default merge |
| `.git/` absent | `proj-init` | Continue; output `Note: .git/ absent — gitlint config dropped but inactive.` |
| Network failure on `uv add` / `poetry add` | `proj-init` | Exit non-zero with stderr |
| Re-run on already-initialised project | `proj-init` | All targets identical → `proj-init complete. (no changes)` |
| Empty changed-files list | check-style, security | `No .py files to lint.` / `No .py files to scan.` exit 0 |
| All findings after ruff Pass 1 are complex (C90*/PL*) | check-style | Model tries to fix all; refused items listed with reasons; exit 0 |
| No bandit findings at any level | security | No prompt; auxiliary scans run; final summary line |
| User declines consent prompt | security | Findings reported, nothing modified, stop with success. |
| All findings already covered by tests | gen-tests | `All changed files already have tests.` exit 0 |
| Pytest collection fails on generated tests | gen-tests | `collection_ok_all == false` → halt immediately with the failing file list |
| Generated tests fail assertions | gen-tests | Propose source code improvements, ask consent once (`AskUserQuestion`), apply via `Edit`/`MultiEdit` to source files (cap 2 iterations). If still failing after 2 iterations, halt with count |
| User declines source code improvements | gen-tests | Tests staged but failing. Stop with success — the user made a choice |
| `style-fixer` cannot summarize a function from its signature | check-style | Agent returns `refused[]` with `cannot-summarize`; surfaced in final summary with reason |
| `security-fixer` cannot determine safe fix | security | Agent returns `refused[]` with structured reason (e.g., `exec-with-dynamic-input`, `unknown-db-driver`); surfaced in final summary |
| Diff > 500 lines | doc-sync | Capped at 500; agent works on the head |
| Patch fails to apply | doc-sync, readme-sync | Print failure, continue with rest (doc-sync) or halt (readme-sync) |
| All signals false | readme-sync | `No README change needed.` |
| User declines a sub-skill prompt during preflight | preflight | Sub-skill exits non-zero → preflight halts at that step |
| `.git/COMMIT_EDITMSG` exists from prior failed run | preflight step 7 | Removed at step 7 start; never reused across runs |
| sys.modules cross-contamination between test files | test-writer | `sys.modules.pop("<module>", None)` before importing module under test |
| `autospec=True` on pre-mocked MagicMock parent | test-writer | `autospec=True` omitted when parent object is already a MagicMock — avoids `InvalidSpecError` |
| Unstaged changes at preflight entry | preflight | Auto-staged (git add -u + targeted untracked) after gh guards pass |
| `gh` absent when preflight would auto-stage | preflight | gh guards (#3/#4) precede auto-stage (#5) — files never staged if `gh` is missing |
| check-style style-fixer refuses a finding | check-style Step 5 | Shown with proposed fix + `AskUserQuestion`; parent applies on Yes |
| gen-tests mechanical test failure | gen-tests | Fixed directly in test file by parent (wrong patch path, missing import, sys.modules contamination) — no consent, no test-fixer |
| `gh` not authenticated | commit-push-pr | `gh auth required: run gh auth login.` exit non-zero |
| Pre-commit hook rejects | commit, commit-push-pr | Surface verbatim; no `--no-verify` |
| PR already exists for branch | commit-push-pr | Extract URL from `gh` error, exit 0 |

### 10.3 Known boundaries (not gaps in implementation, but limits of scope)

Observed during empirical testing on real third-party projects:

- **Both runners supported, but mixing is not.** `proj-init` asks the user to choose `venv` or `poetry` and persists the choice in `[tool.starter].runner`. `venv` maps to `uv` internally. If the user later switches managers manually without re-running `proj-init`, the runner key may diverge from the actual lockfile state.
- **No default `extend-exclude` for generated code.** ANTLR parsers, protobuf stubs, etc. will produce noisy findings; projects with generated files need per-file ignores added manually.
- **`gen-tests` package-name resolution** reads `[project] name` from `pyproject.toml`. Multi-namespace projects (where `from src.X` and `from <pkg>.Y` coexist) may receive imports tied to the wrong root.
- **`doc-sync` is hardcoded to `docs/`.** Projects with root-level docs or a different docs root are not covered.
- **`readme-sync`'s `deps_added` regex** (`^[+-]\s*"[a-zA-Z]`) can false-fire on `authors`, `classifiers`, or `keywords` array changes; the agent typically returns `patched:false` in those cases, but the signal flagging is conservative.
- **Cross-file rename heuristics** (`N801`/`N802`) rely on a word-boundary `Grep` plus per-file confirmation. A symbol that appears as a substring inside an unrelated string literal can produce a false hit; the parent reads each match before applying `MultiEdit`, but for class names that double as common English words the user may want to review the diff.
- **Security agent tries everything but has limits.** The agent attempts all findings including B102/B301/B302/B306/B608 — but refuses when the code context is genuinely ambiguous (exec with dynamic input, pickle with custom objects, SQL with unknown DB driver, complex shell syntax). Refused items are surfaced with structured reasons in the final summary.

- **LLM security pass is HIGH-confidence only.** MEDIUM-confidence issues (TOCTOU in single-process tools, injection in CLI tools where attacker = user) are correctly skipped. Users who want exhaustive coverage should supplement with manual review.

These boundaries are observable from the outside; they are documented here as the honest limits of `v2.0.0`.

---

## 11. Internal traceability

| Artefact | Where it lives | Owner |
|----------|----------------|-------|
| Original contract | `DESIGN.md` (~700 lines) | shapsha-lemans |
| Plugin manifest | `.claude-plugin/plugin.json` | this plugin |
| Marketplace manifest | `.claude-plugin/marketplace.json` | this plugin |
| Skill specifications | `skills/<skill>/SKILL.md` (×7) | this plugin |
| Subagent specifications | `agents/<agent>.md` (×6) | this plugin |
| Slash command specifications | `commands/<cmd>.md` (×2) | this plugin |
| Templates | `templates/**` | this plugin |
| External observation report | conversation history | most recent run |

The plugin has been smoke-tested:

- in a sandbox (`C:\retrodoc\bt-ai-smoke`) with seeded violations (B006, B307, F821) — all detected by the engines at the configured thresholds;
- against a real third-party project (`C:\retrodoc\skills-BT-AI\retrodoc`, FastAPI/Poetry, 200 source files) — all silent no-op paths verified, all pre-flight aborts verified, plus the boundaries listed in §10.3.

What is **not yet runtime-tested** (requires interactive `/plugin install` in a Claude Code session):

- `disable-model-invocation: true` enforcement;
- `${CLAUDE_PLUGIN_ROOT}` resolution;
- `Task` delegation to the six subagents (and the parallel-fan-out cap of 10 calls per message);
- `AskUserQuestion` rendering;
- the `.git/COMMIT_EDITMSG` handoff between `preflight` step 7 and `commit-push-pr` step 2.

These are runtime-host concerns, not shell-logic concerns.

---

## 12. Versioning

Current: `2.0.0`. Bump policy:

- patch (`x.x.N`) for bug fixes that do not change skill surface or output format;
- minor (`x.N.0`) for new skills, new agents, or new options on existing skills;
- major (`N.0.0`) for changes to severity classification, the consent/fix model, or any backwards-incompatible output format change.

Version history (highlights):

- **0.1.10** — `venv` (via `uv`) and `poetry` runners supported; `proj-init` always asks; runner persisted in `[tool.starter].runner`. `gen-tests` covers `async def`. Per-file fan-out for `check-style`, `security`, `gen-tests`, `doc-sync` — all `Task` calls in a single message. Two-pass lint: ruff first, model second. Security scans all levels, proposes fixes, consent once. `gen-tests` treats tests as truth; proposes source improvements on failure. `style-fixer` and `security-fixer` agents as standalone files.

- **2.0.0** — Major revision across all skills and agents:
  - **check-style**: advisory bucket eliminated — all findings go to `style-fixer`. New display separators (`----------------------------------` per finding, `===…===` before refused section). New Step 5: refused findings shown with proposed fixes + `AskUserQuestion`; parent applies on Yes. Final summary: `auto-fixed / consent-fixed / remaining`.
  - **security**: LLM-native second pass added (Pass 2) — 6 categories (LLM-AUTH, LLM-INJECTION, LLM-LOGIC, LLM-SECRET, LLM-CRYPTO, LLM-SECOND-ORDER), HIGH confidence only, deduplicated vs bandit, merged into `all_findings[]`. `security-fixer` now handles both B-codes and LLM-* tags.
  - **gen-tests**: silent rule enforced (no narration). `git add` and `pytest` in separate Bash calls. `test-fixer` banned — parent handles mechanical failures directly. Triage: mechanical (fix in test file, no consent) vs semantic (source improvement, consent, cap 2 iterations).
  - **test-writer**: `sys.modules.setdefault` pre-mock block for heavy third-party deps. `sys.modules.pop("<module>", None)` before importing module under test (prevents cross-contamination). Explicit `mock.patch` formula with table. `autospec=True` only when parent is real (not pre-mocked). Silence formula added.
  - **proj-init**: smart runner auto-detection from filesystem (`.venv/` → venv, `poetry.lock` → poetry, `requirements.txt` → ask, bare → ask). `AskUserQuestion` is STEP 0 — first tool call when runner is ambiguous.
  - **preflight**: structured output — `===…===` separators between steps, `---…---` + narration sentence before every Bash command. Guard reorder: gh checks (#3/#4) before auto-stage (#5). Auto-stage uses `git add -u` + targeted untracked (not `git add -A`). `COMMIT_EDITMSG` cleaned at step 7 start and on step 8 failure.

The version is declared once in `.claude-plugin/plugin.json`. Skills do not embed it.
