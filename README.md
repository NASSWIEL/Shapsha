# bt-ai — plugin Claude Code

> Standardise les pratiques Python d'équipe : style, sécurité, tests, documentation, pré-commit, initialisation projet.

Plugin [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) qui regroupe sous des slash-commands (`/bt-ai:*`) un ensemble de skills silencieux, hermétiques et idempotents. Chaque skill agit sur le diff par défaut, applique les corrections sûres automatiquement, et n'interrompt que sur les signaux qui exigent réellement un jugement humain.

## Sommaire

- [Installation](#installation)
- [Pré-requis](#pré-requis)
- [Commandes au quotidien](#commandes-au-quotidien)
- [Skills](#skills)
- [Sous-agents](#sous-agents)
- [Pipeline preflight](#pipeline-preflight)
- [Philosophie de design](#philosophie-de-design)
- [Argument `all`](#argument-all)
- [Runner dispatch (`uv` / `poetry`)](#runner-dispatch-uv--poetry)
- [Hermétique : pas de fichiers scratch](#hermétique--pas-de-fichiers-scratch)
- [Arborescence](#arborescence)
- [Documentation](#documentation)
- [Licence](#licence)

## Installation

Dans Claude Code, deux commandes :

```
/plugin marketplace add NASSWIEL/bt-ai-plugin
/plugin install bt-ai@CGI-BT-AI
```

La première récupère le marketplace `CGI-BT-AI` directement depuis GitHub (pas de `git clone`). La seconde installe le plugin `bt-ai` depuis ce marketplace.

## Pré-requis

| Outil | Pourquoi | Comment l'obtenir |
|---|---|---|
| [`uv`](https://docs.astral.sh/uv/) **ou** [`poetry`](https://python-poetry.org/) | Runner Python (au moins l'un des deux) | `proj-init` détecte la forme du projet et propose le bon défaut |
| `git` | Tous les skills lisent le diff via `git diff` | Standard |
| `gh` ([GitHub CLI](https://cli.github.com)) authentifié | Création de PR par `commit-push-pr` et `preflight` | `gh auth login` |

Aucune dépendance Python n'est imposée à l'extérieur du runner choisi : ruff, bandit, pyright, pytest, gitlint-core sont installés par `proj-init` dans l'environnement du projet.

## Commandes au quotidien

| Commande | Quand | Ce qu'elle fait |
|---|---|---|
| `/bt-ai:proj-init` | Une fois, à la création du projet | Détecte la forme du projet, choisit le runner, installe les outils, dépose les configs et les templates de docs |
| `/bt-ai:check-style` | Après modification de fichiers `.py` | Lance ruff sur les fichiers modifiés, applique automatiquement les corrections sûres, n'interrompt que sur les erreurs Critiques (noms non définis, imports cassés, erreurs de syntaxe) |
| `/bt-ai:check-style all` | Avant une PR importante | Idem, mais sur l'ensemble du dépôt au lieu du diff |
| `/bt-ai:security` | Après modification de fichiers `.py` | Lance bandit sur les fichiers modifiés, affiche les findings ≥ MEDIUM/MEDIUM en mode informatif, n'interrompt que sur HIGH/HIGH (exec, eval, pickle, clés codées en dur, injection shell). Aucune correction automatique |
| `/bt-ai:gen-tests` | Après ajout/modification de code applicatif | Génère des tests pytest pour les fichiers `.py` modifiés via le sous-agent `test-writer`, lance les tests générés, répare automatiquement les échecs mécaniques (cap à 3 tentatives), interrompt sur échec sémantique |
| `/bt-ai:gen-tests src/foo.py` | Cible un fichier précis | Idem mais limité au chemin fourni |
| `/bt-ai:doc-sync` | Après changement d'API publique | Le sous-agent `doc-patcher` propose un patch minimal pour `docs/` et docstrings ; appliqué automatiquement si le patch est propre |
| `/bt-ai:readme-sync` | Après changement visible côté utilisateur (CLI, env vars, deps) | Le sous-agent `readme-patcher` propose un patch minimal pour `README.md` (ton français préservé) ; appliqué automatiquement |
| `/bt-ai:commit` | Pour committer manuellement | Compose un message Conventional Commit depuis le diff staged, le valide via gitlint, commite. Pas de push, pas de PR |
| `/bt-ai:commit-push-pr` | Pour committer + pousser + ouvrir une PR | Commite (titre anglais, corps français), pousse la branche, ouvre la PR via `gh`. Refuse la branche par défaut et le force-push |
| `/bt-ai:preflight` | Avant chaque PR | Pipeline complet : check-style → security → gen-tests → pytest → doc-sync → readme-sync → commit-push-pr. Silencieux sur le chemin heureux. Termine par l'URL de la PR |

## Skills

Chaque skill suit le même contrat : silencieux par défaut, hermétique (aucun fichier scratch écrit dans le repo utilisateur), avec un comportement clair sur le chemin heureux et une halt-line explicite sur le chemin d'erreur.

### `/bt-ai:proj-init`

Bootstrap d'un projet Python conforme aux standards bt-ai.

- **Détecte la forme du projet** (`uv`, `poetry`, `mixed`, `bare`) à partir de `pyproject.toml` et des lockfiles présents.
- **Demande explicitement le runner** (`AskUserQuestion`) quand les deux runners sont installés et que le projet est `bare` ou `mixed`. C'est la seule skill du plugin qui prompte ; partout ailleurs, l'ambiguïté n'existe pas.
- **Persiste le choix** dans `[tool.bt-ai].runner` — tous les autres skills/agents s'y réfèrent ensuite.
- **Installe les outils manquants** (`ruff`, `bandit`, `pyright`, `pytest`, `pytest-cov`, `gitlint-core`) via le runner choisi. Filtre anti-dual-spec : un outil déjà déclaré dans n'importe quelle section TOML n'est pas réinstallé.
- **Fusionne les fragments TOML** (`templates/pyproject/*.toml.fragment`) dans `pyproject.toml` via un merge intelligent : union de tokens pour les chaînes de flags, union pour les listes, conservation du scalaire cible en cas de conflit.
- **Dépose les templates** : `docs/`, `README.md`, `.gitignore`, `.gitlint`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/*`.
- **Migre les docs root-level** (`ARCHITECTURE.md`, `DATA_MODEL.md`, etc.) vers `docs/` avec `git mv` (sur prompt).

### `/bt-ai:check-style`

Lint des fichiers Python modifiés via ruff.

- **Pipeline** : `ruff check ... --output-format=json | tools/classify_ruff.py`. Aucun fichier scratch écrit.
- **Classification** : Critical (`F*`, `E9*`) / High (`B*`, `S*`) / Low (autres).
- **Auto-fix silencieux** des Low (`E`, `W`, `D`, `I`, `UP`) **et** des High whitelistées (`B007`, `B009`, `B010`, `B011`, `S101` dans `tests/`). Les fichiers fixés sont stagés via `git add`.
- **Halt** uniquement sur Critical (variables non définies, imports cassés, syntaxe invalide) — l'humain doit lire le code.
- **Advisory** sur findings High hors whitelist (surfacés mais ne stoppent pas la suite).
- **Argument `all`** pour scanner tout le repo au lieu du diff.

### `/bt-ai:security`

Analyse de sécurité bandit sur les fichiers Python modifiés.

- **Filtre** : sévérité ≥ MEDIUM **et** confiance ≥ MEDIUM (signal sur bruit).
- **Pas d'auto-fix.** Suppresser un warning sécurité silencieusement est dangereux. Skill report-only.
- **Halt** uniquement sur HIGH/HIGH (sévérité **et** confiance) : exec, eval, pickle sur données externes, clés codées en dur, injection shell.
- **Advisory** sur MEDIUM/MEDIUM, MEDIUM/HIGH, HIGH/MEDIUM (surfacés mais ne stoppent pas la suite).
- **Argument `all`** pour scanner tout le repo au lieu du diff.
- **Note** : `B104` (binding `0.0.0.0`) est skippé au niveau du fragment bandit (deploy-time, pas dev-time).

### `/bt-ai:gen-tests`

Génère puis **vérifie** les tests pytest manquants.

- **Trois modes** :
  - *Diff mode* (sans argument) — scanne les `*.py` modifiés en excluant `tests/**`.
  - *Targeted mode* (chemin en argument) — génère pour ce fichier uniquement.
  - *Full sweep* (`all`) — balaie tout le repo (révèle la dette de couverture).
- **Filtre de découverte** (`tools/discover_test_targets.py`) : skip auto des handlers FastAPI/Starlette, pages Streamlit, CLI Click/Typer, modèles purs Pydantic/SQLAlchemy/Django (mieux testés via `TestClient`/`CliRunner`).
- **Génération** : pour chaque fonction publique restante, l'agent `test-writer` produit un test golden + un cas d'erreur + une valeur limite. **Pas de `pytest.skip("TODO")`** : si une fonction est genuinement intestable sans side-effects, elle est omise.
- **Phase verify** :
  1. `pytest -q` sur les fichiers générés.
  2. Sortie parsée par `tools/parse_pytest_failures.py` qui classe MECHANICAL vs SEMANTIC.
  3. Échecs mécaniques (`ImportError`, `NameError`, fixture-not-found, missing-argument, `SyntaxError`) → délégués à l'agent `test-fixer`. Boucle ≤ 3 itérations.
  4. Échecs sémantiques (`AssertionError`, `DID-NOT-RAISE`, `WrongExceptionType`) → halt avec message clair, l'utilisateur corrige à la main.
- **Mirroring strict** : `src/foo/bar.py` → `tests/foo/test_bar.py`.

### `/bt-ai:doc-sync`

Synchronise `docs/` (Markdown français) avec le code.

- **Lit le diff** (`*.py`, `pyproject.toml`, `*.md`), capé à 500 lignes pour rester dans le contexte.
- **L'agent `doc-patcher`** lit uniquement les docs impactées (suit la section MODE D'EMPLOI de chaque template) — pas de pollution du contexte parent.
- **Sortie** : patches unified-diff minimaux, **appliqués automatiquement** via `Edit`. Les fichiers patchés sont stagés via `git add`.
- **Halt** uniquement si un patch ne s'applique pas proprement (l'utilisateur merge à la main).
- **Pas d'invention** : aucun nom de fonction, paramètre ou behavior n'est ajouté qui ne soit présent dans le diff.

### `/bt-ai:readme-sync`

Met à jour `README.md` **uniquement** si la surface utilisateur a changé.

- **Détecteurs** : `[project.scripts]`, `__all__`, env vars (`os.environ`/`os.getenv`), set de noms de dépendances dans `pyproject.toml`, fichiers d'install (`Dockerfile`, `Makefile`, `.python-version`).
- **Sans signal** côté surface : `No README change needed.` puis exit 0. Évite les faux positifs sur les refactors purement internes.
- **L'agent `readme-patcher`** (read-only) propose un patch en français, appliqué automatiquement.
- **Halt** uniquement si le patch ne s'applique pas. Le fichier patché est stagé via `git add`.

### `/bt-ai:preflight`

Suite séquentielle pré-PR. Voir [Pipeline preflight](#pipeline-preflight) pour le détail.

### `/bt-ai:commit`

Commit Conventional Commits sur les changements stagés.

- **Compose** un message à partir du diff staged : `<type>(<scope>?): <subject>`, anglais, sujet ≤ 72 caractères, impératif.
- **Valide** via gitlint (utilise `.gitlint` du projet).
- **Commit** sans push.
- **Refus** : pas de `--no-verify`, pas de `--amend` non sollicité.

### `/bt-ai:commit-push-pr`

Commit + push + ouverture de PR.

- **Compose** un Conventional Commit (titre anglais, corps français).
- **Crée automatiquement** une branche `<type>/<slug>` si l'utilisateur est sur la branche par défaut.
- **Push** la branche puis lance `gh pr create`.
- **Réutilise** `.git/COMMIT_EDITMSG` si pré-validé par `/bt-ai:preflight` (le fichier est consommé puis supprimé).
- **Refus** : `--force` push, push sur la branche par défaut, `--no-verify`.

## Sous-agents

Sous-agents à contexte isolé, périmètre minimal. Quatre dans le pipeline auto, deux disponibles pour un usage manuel.

### Pipeline auto

| Agent | Tools | Modèle | Rôle | Sortie |
|---|---|---|---|---|
| `test-writer` | Read, Write, Edit, Glob, Bash | Sonnet | Génère les tests pytest manquants (golden + erreur + boundary, **vrais** tests, pas de stub). N'écrase jamais un test existant. | Fichiers `tests/**/test_*.py` |
| `test-fixer` | Read, Edit, Glob, Bash | Haiku | Répare les échecs mécaniques après pytest (imports manquants, fixtures absentes, args manquants). One-shot — le parent rappelle si nécessaire (cap 3). | Edits in-place |
| `doc-patcher` | Read, Glob | Sonnet | Calcule les patches unified-diff minimaux pour `docs/*.md`. Lit uniquement les docs impactées. | JSON `{patches: [...]}` |
| `readme-patcher` | Read | Sonnet | Propose le patch `README.md` (surface utilisateur uniquement). Préserve le ton français existant. | JSON `{patch, sections_touched}` |

### Disponibles manuellement

| Agent | Tools | Modèle | Usage |
|---|---|---|---|
| `style-fixer` | Read, Edit, Bash | Sonnet | Applique les auto-fix ruff sur des findings spécifiques. `check-style` applique ruff directement ; cet agent existe pour des invocations ciblées via Task. |
| `security-fixer` | Read, Edit | Sonnet | Applique des fix narrow (par ex. `B113` timeout) hors blacklist. `security` est report-only par défaut ; cet agent peut être invoqué manuellement si l'utilisateur souhaite un fix mécanique. |

Tous les agents tournent en mode `Silent` : pas de narration, sortie minimale, un seul passage.

## Pipeline preflight

`/bt-ai:preflight` est une suite **séquentielle, halt-on-failure, sans prompt sur le chemin heureux**. La seule sortie quand tout va bien est l'URL de la PR :

```
$ /bt-ai:preflight
https://github.com/<org>/<repo>/pull/123
```

### Gardes initiales

Avant tout travail, le skill refuse l'exécution si :

- Pas de repo git.
- Aucun changement (ni staged ni unstaged).
- Changements unstaged uniquement → halt (preflight ne stage **jamais** les changements de l'utilisateur à sa place).
- Branche actuelle = branche par défaut → halt (créer une feature branch d'abord).
- `gh` absent ou non authentifié → halt (échouer tôt évite de gâcher 5 minutes de checks).

### Étapes

| # | Étape | Halt si |
|---|---|---|
| 1 | `check-style` | Findings Critical (`F*`, `E9*`) |
| 2 | `security` | Findings HIGH/HIGH |
| 3 | `gen-tests` (diff mode) | Échec sémantique persistant après 3 réparations mécaniques |
| 4 | `pytest -q` (full suite) | Exit non-zero |
| 5 | `doc-sync` | Patch ne s'applique pas |
| 6 | `readme-sync` | Patch ne s'applique pas |
| 7 | Compose + valide message via gitlint | Gitlint rejette après une réécriture |
| 8 | `commit-push-pr` | `gh pr create` échoue |

### Stage handoff

Chaque sous-skill `git add` ses propres outputs (fixes ruff, tests générés, patches docs/README). Au moment du commit (étape 7), le tree staged contient les changements originaux **plus** tout le travail auto-généré. Preflight lui-même ne stage rien.

### Sortie

- **Succès** : URL de PR sur une ligne, rien d'autre.
- **Halt** : `Halted at step <N>: <raison>.` suivi du détail verbatim de l'outil fautif. Aucune narration intermédiaire.

## Philosophie de design

Inspirée du plugin [`commit-commands`](https://github.com/anthropics/claude-code) d'Anthropic et des conventions [`claude-code-plugins`](https://docs.claude.com/en/docs/claude-code/plugins).

- **Silence par défaut.** Aucun "je vais faire X, puis Y…". L'utilisateur voit le diff, le résultat final, ou la halt-line. Rien d'autre.
- **Skills en tant que prompts, pas state machines.** Chaque skill est un prompt court (≤ 100 lignes) avec contexte injecté via `!command` (pré-exécuté côté shell, n'apparaît pas dans la conversation), un bloc « Your task », et une « single-message incantation » qui force des appels d'outils en parallèle.
- **`allowed-tools` étroits.** Patterns `Bash(git status:*)` au lieu de `Bash` pour qu'aucune confirmation ne soit déclenchée sur le chemin heureux.
- **Pas de prompt utilisateur dans les sous-skills.** `check-style`, `security`, `gen-tests`, `doc-sync`, `readme-sync` n'utilisent **jamais** `AskUserQuestion`. Ils auto-appliquent ou halt avec un message clair. L'utilisateur tranche au moment du commit (`git diff` avant push).
- **`AskUserQuestion` réservé aux ambiguïtés réelles.** Seul `proj-init` en utilise (choix `uv`/`poetry` quand les deux sont installés et que le projet est `bare`/`mixed`).
- **Refus systématiques** : pas de `--no-verify`, pas de `--force` push, pas de push sur la branche par défaut. Si un hook échoue, halt verbatim — l'utilisateur corrige la cause racine.
- **Idempotence.** Re-lancer un skill sans changement intermédiaire ne produit rien (pas de re-staging, pas de re-fix, pas de patch fantôme).

## Argument `all`

Trois skills acceptent l'argument optionnel `all` :

- `/bt-ai:check-style all` — lint **tout** le repo (slow ; utile une fois pour absorber la dette).
- `/bt-ai:security all` — bandit sur tout le repo.
- `/bt-ai:gen-tests all` — génère les tests manquants pour **tous** les fichiers tracés (hors `tests/**`).

Sans argument, ces trois skills agissent uniquement sur les fichiers modifiés (staged, unstaged, untracked) — comportement par défaut, recommandé pour le travail incrémental. Tout argument autre que `all` est rejeté avec un message explicite (`Unknown argument: <token>. Accepts no argument or 'all'.`).

## Runner dispatch (`uv` / `poetry`)

Tous les skills/agents lisent `[tool.bt-ai].runner` dans `pyproject.toml` (défaut : `uv`) via `tools/resolve_runner.py`, puis invoquent les outils via `$R run <tool>` où `$R` vaut `uv` ou `poetry`. Le choix est fait une fois par `proj-init` et reste cohérent ensuite.

Lecture rapide :

```
R=$(python "${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py")
$R run ruff check src/
```

`gitlint-core` est utilisé à la place de `gitlint` pour éviter la dépendance `sh` (qui échoue à compiler sur Windows à cause de `fcntl`). Le binaire CLI s'appelle toujours `gitlint`.

## Hermétique : pas de fichiers scratch

Tous les helpers Python du plugin (classification ruff/bandit, découverte des cibles de test, parsing des échecs pytest, résolution du runner) vivent sous `${CLAUDE_PLUGIN_ROOT}/tools/`. Ils sont invoqués directement par les skills via pipe.

**Aucun script auxiliaire n'est jamais écrit dans le repo de l'utilisateur.** Le `git status` après une commande bt-ai ne contient que les fichiers attendus : fixes de style, nouveaux tests, patches docs/README.

## Arborescence

```
bt-ai-plugin/
├── .claude-plugin/
│   ├── marketplace.json
│   └── plugin.json
├── agents/
│   ├── doc-patcher.md
│   ├── readme-patcher.md
│   ├── security-fixer.md
│   ├── style-fixer.md
│   ├── test-fixer.md
│   └── test-writer.md
├── commands/
│   ├── commit.md
│   └── commit-push-pr.md
├── docs/
│   └── design.md
├── skills/
│   ├── check-style/SKILL.md
│   ├── doc-sync/SKILL.md
│   ├── gen-tests/SKILL.md
│   ├── preflight/SKILL.md
│   ├── proj-init/SKILL.md
│   ├── readme-sync/SKILL.md
│   └── security/SKILL.md
├── templates/
│   ├── docs/
│   │   ├── architecture.md
│   │   ├── contracts.md
│   │   ├── data-model.md
│   │   ├── fonctionnel.md
│   │   ├── glossaire.md
│   │   └── index.md
│   ├── github/
│   │   ├── ISSUE_TEMPLATE/
│   │   │   ├── bug_report.md
│   │   │   └── feature_request.md
│   │   └── PULL_REQUEST_TEMPLATE.md
│   ├── pyproject/
│   │   ├── bandit.toml.fragment
│   │   ├── pyright.toml.fragment
│   │   ├── pytest.toml.fragment
│   │   └── ruff.toml.fragment
│   ├── gitignore.python
│   ├── gitlint
│   └── README.md
├── tools/
│   ├── classify_bandit.py
│   ├── classify_ruff.py
│   ├── discover_test_targets.py
│   ├── parse_pytest_failures.py
│   └── resolve_runner.py
├── .gitignore
├── LICENSE
└── README.md
```

## Documentation

- **[docs/design.md](docs/design.md)** — workflow complet, méthodologie, cas d'usage, justifications des choix d'outils.
- **Repository** — [github.com/NASSWIEL/bt-ai-plugin](https://github.com/NASSWIEL/bt-ai-plugin).
- **Issues** — [github.com/NASSWIEL/bt-ai-plugin/issues](https://github.com/NASSWIEL/bt-ai-plugin/issues).

## Licence

Proprietary — CGI.
