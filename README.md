# bt-ai — plugin Claude Code

Standardise les pratiques Python d'équipe : style, sécurité, tests, documentation, pré-commit, initialisation projet.

## Installation

Dans Claude Code, deux commandes :

```
/plugin marketplace add NASSWIEL/bt-ai-plugin
/plugin install bt-ai@CGI-BT-AI
```

La première récupère le marketplace `CGI-BT-AI` directement depuis GitHub (pas de `git clone` à faire). La seconde installe le plugin `bt-ai` depuis ce marketplace.

## Pré-requis

- [uv](https://docs.astral.sh/uv/) **ou** [poetry](https://python-poetry.org/) installé (`/bt-ai:proj-init` détecte la forme du projet et propose un défaut)
- `git`
- `gh` (GitHub CLI) authentifié pour `/bt-ai:commit-push-pr` et `/bt-ai:preflight`

## Commandes

| Commande | Rôle |
|---|---|
| `/bt-ai:proj-init` | Bootstrap d'un projet Python (outils + configs + templates) |
| `/bt-ai:check-style` | Lint des fichiers modifiés (ruff). Argument `all` pour passer tout le repo. |
| `/bt-ai:security` | Analyse sécurité des fichiers modifiés (bandit). Argument `all` idem. |
| `/bt-ai:gen-tests` | Génère + vérifie les tests pytest manquants. Argument `all` ou chemins explicites. |
| `/bt-ai:doc-sync` | Synchronise `docs/` avec le code |
| `/bt-ai:readme-sync` | Met à jour `README.md` si la surface utilisateur change |
| `/bt-ai:preflight` | Suite complète avant PR |
| `/bt-ai:commit` | Commit Conventional Commits |
| `/bt-ai:commit-push-pr` | Commit + push + ouverture PR |

## Argument `all`

Trois skills acceptent l'argument optionnel `all` :

- `/bt-ai:check-style all` — lint **tout** le repo (slow ; utile une fois pour absorber la dette).
- `/bt-ai:security all` — bandit sur tout le repo.
- `/bt-ai:gen-tests all` — génère les tests manquants pour **tous** les fichiers tracés (hors `tests/**`), pas seulement ceux du diff.

Sans argument, tous trois agissent uniquement sur les fichiers modifiés (staged, unstaged, untracked) — comportement par défaut, recommandé pour le travail incrémental. Tout argument autre que `all` est rejeté avec un message explicite.

## Détail des skills

### `/bt-ai:proj-init`
Bootstrap d'un projet Python conforme aux standards bt-ai.
- Détecte la forme du projet (`uv` / `poetry` / `mixed` / `bare`) à partir de `pyproject.toml` et des lockfiles présents.
- **Demande explicitement le runner** (`AskUserQuestion`) quand les deux runners sont installés et que le projet est `bare` ou `mixed`. Pas de choix silencieux dans les cas ambigus.
- Écrit `[tool.bt-ai].runner = "uv"` ou `"poetry"` (utilisé par tous les autres skills).
- Installe les outils manquants (ruff, bandit, pytest, pyright, gitlint-core, pytest-cov) via le runner choisi.
- **Filtre anti-dual-spec** : un outil déclaré dans **n'importe quelle** section TOML (uv ou poetry) est considéré comme déjà présent — pas de réinstall, pas de déclaration en double.
- Fusionne les fragments TOML (`templates/pyproject/*.toml.fragment`) dans `pyproject.toml` via un merge intelligent par clé : union de tokens pour les chaînes de flags, union pour les listes, conservation du scalaire cible en cas de conflit.
- Copie les templates `docs/`, `README.md`, `.gitignore`, templates GitHub (PR + Issue) et `.gitlint`.

### `/bt-ai:check-style`
Lint des fichiers Python modifiés via ruff. Pipeline :

```
ruff check ... --output-format=json | python ${CLAUDE_PLUGIN_ROOT}/tools/classify_ruff.py
```

Aucun fichier scratch n'est écrit dans le repo de l'utilisateur — la classification se fait dans le tool bundle du plugin.

- Classification : Critical (`F*`, `E9*`) / High (`B*`, `S*`) / Low (autres).
- Auto-fix silencieux des Low (`E`, `W`, `D`, `I`, `UP`).
- Demande confirmation avant d'appliquer les fix unsafe sur High (sous-ensemble whitelisté : `B007`, `B009`, `B010`, `B011`, `S101` dans `tests/`).
- Refuse les renames (`N*`) et les Critical : exit non-zero, l'humain tranche.
- Délègue les corrections à l'agent `style-fixer`.

### `/bt-ai:security`
Analyse bandit des fichiers Python modifiés. Même pattern : `bandit -f json | classify_bandit.py`.

- Filtre : sévérité ≥ MEDIUM **et** confiance ≥ MEDIUM (signal/bruit).
- Classifie FIXABLE vs BLOCKED. BLOCKED couvre les catégories à risque (`B102` exec, `B301` pickle, `B602` shell=True, etc.) que l'agent ne touche jamais.
- `B104` (binding `0.0.0.0`) est aussi skippé au niveau du fragment bandit (préoccupation deploy-time, pas dev-time).
- Délègue les fix à l'agent `security-fixer` qui n'agit que sur la whitelist FIXABLE.

### `/bt-ai:gen-tests`
Génère + **vérifie** les tests pytest manquants.

**Trois modes** :
- **Diff mode** (sans argument) : scanne les `*.py` modifiés en excluant `tests/**`.
- **Targeted mode** (chemins en argument) : génère pour ces fichiers uniquement.
- **Full sweep** (`all`) : balaie tout le repo (slow ; révèle la dette de couverture).

**Filtre de découverte** — `${CLAUDE_PLUGIN_ROOT}/tools/discover_test_targets.py` skip automatiquement :

| Type | Skip reason | Pourquoi |
|---|---|---|
| Handlers FastAPI/Starlette (`@router.get` etc.) | `fastapi-handler` | Mieux testés via `TestClient` (out of scope) |
| Pages Streamlit (`import streamlit`) | `streamlit-page` | Doivent tourner dans le runtime Streamlit |
| CLI Click/Typer (`@*.command`) | `cli-entrypoint` | Test via `CliRunner` (out of scope) |
| Fichiers de modèles purs (Pydantic, SQLAlchemy, Django models) | `model-only` | Dunders auto-générés, pas de cibles utiles |

Pour chaque fonction publique restante (function/method/AsyncFunction via AST), l'agent `test-writer` produit **de vrais tests** : golden path + un cas d'erreur + une valeur limite. **Pas de `pytest.skip("TODO")`** : si une fonction est génuinement intestable sans side-effects, elle est omise (pas de stub trompeur).

**Phase verify (boucle d'auto-réparation)** :
1. `pytest -q` sur les fichiers générés.
2. Sortie parsée par `${CLAUDE_PLUGIN_ROOT}/tools/parse_pytest_failures.py` qui classe chaque échec MECHANICAL vs SEMANTIC.
3. **Échecs mécaniques** (ImportError, NameError, fixture-not-found, missing-argument, SyntaxError) → délégués automatiquement à l'agent `test-fixer`. Boucle jusqu'à 3 itérations.
4. **Échecs sémantiques** (AssertionError, DID-NOT-RAISE, WrongExceptionType) → demande utilisateur (`keep` / `regen` / `discard`).

Mirroring strict : `src/foo/bar.py` → `tests/foo/test_bar.py`. Toujours.

### `/bt-ai:doc-sync`
Synchronise `docs/` avec le code.
- Lit le diff (`*.py`, `pyproject.toml`, `*.md`), capé à 500 lignes.
- L'agent `doc-patcher` lit uniquement les docs impactées (suit la section MODE D'EMPLOI de chaque template) — pas de pollution du contexte parent.
- Retourne des patches unified-diff minimaux, appliqués via `Edit` après approbation utilisateur (`[a]/[s]/[n]`).

### `/bt-ai:readme-sync`
Met à jour `README.md` **uniquement** si la surface utilisateur a changé.
- Détecteurs : `[project.scripts]`, `__all__`, env vars (`os.environ`/`os.getenv`), set de noms de dépendances dans `pyproject.toml`.
- Sans signal côté surface : `No user-facing changes detected. README unchanged.`, exit 0.
- L'agent `readme-patcher` (read-only) propose des patches en français ; l'application reste la décision de l'utilisateur.

### `/bt-ai:preflight`
Suite séquentielle pré-PR. Voir [Logique du preflight](#logique-du-preflight).

### `/bt-ai:commit` et `/bt-ai:commit-push-pr`
- `/bt-ai:commit` : compose un message Conventional Commit (anglais, sujet ≤ 72 char, impératif) à partir du diff staged et commit.
- `/bt-ai:commit-push-pr` : commit + push + `gh pr create` avec titre EN et corps FR. Crée automatiquement une branche `<type>/<slug>` si l'utilisateur est sur la branche par défaut. Ré-utilise `.git/COMMIT_EDITMSG` si pré-validé par `/bt-ai:preflight`.

## Agents

6 sous-agents Sonnet, contexte isolé, périmètre minimal :

| Agent | Tools | Rôle |
|---|---|---|
| `style-fixer` | Read, Edit, Bash | Applique les auto-fix ruff (safe + whitelist unsafe). Refuse renames, Critical, manuel. |
| `security-fixer` | Read, Edit | Applique les fix bandit hors blacklist. Par défaut "report-only" — la majorité reste manuelle. |
| `test-writer` | Read, Write, Edit, Glob, Bash | Génère les tests pytest manquants (golden + erreur + boundary, **vrais** tests, pas de stub). N'écrase jamais un test existant. |
| `test-fixer` | Read, Edit, Glob, Bash | Répare les échecs mécaniques après `pytest` (imports, fixtures, args manquants). Edits sur les tests uniquement, jamais sur le code source. |
| `doc-patcher` | Read, Glob | Calcule les patches unified-diff minimaux pour `docs/*.md`. Lit uniquement les docs impactées. |
| `readme-patcher` | Read | Propose les patches `README.md` (surface utilisateur uniquement). Read-only ; le parent applique. |

## Logique du preflight

`/bt-ai:preflight` est une suite **séquentielle, halt-on-failure**. Chaque étape passe silencieusement ou s'arrête avec une raison sur une ligne. Les sous-skills gèrent leurs propres prompts (fix/skip, `[a]/[s]/[n]`) ; un exit non-zéro d'un sous-skill arrête preflight.

**Garde initiale** :
- Pas de repo git → halt.
- Aucun changement (ni staged ni unstaged) → halt.
- Changements unstaged uniquement → halt (l'utilisateur contrôle le staging, preflight ne fait pas `git add` à sa place).

**Étapes** :

1. **check-style** — halt si Critical/High non résolus.
2. **security** — halt si BLOCKED restant.
3. **gen-tests (diff mode)** — halt si génération ou pytest verify échouent durablement ; "tous déjà testés" est un pass.
4. **pytest** — `$R run pytest -q` ; halt si non-zéro avec les 30 dernières lignes.
5. **doc-sync** — halt si l'utilisateur refuse les patches ou si l'application échoue.
6. **readme-sync** — halt si README désynchronisé non corrigé.
7. **commit message gate** — compose un Conventional Commit depuis `git diff --cached`, valide via `gitlint --staged --msg-stdin`. Une réécriture est possible ; deux échecs → halt. Le message validé est écrit dans `.git/COMMIT_EDITMSG`.
8. **commit-push-pr** — consomme `.git/COMMIT_EDITMSG` via `git commit -F`, push, ouvre la PR. La sortie standard est l'URL de la PR.

**Sortie** :
- Succès : URL de PR.
- Halt : `Halted at step <N>: <raison>.` suivi du détail verbatim de l'outil fautif. Pas de narration intermédiaire.

## Mode silencieux

Tous les skills exécutent les outils sans narration. Pas de "je fais ceci, je fais cela". Chaque commande retourne uniquement son résultat final ou une question explicite via `AskUserQuestion`.

## Hermétique : pas de fichiers scratch dans le repo utilisateur

Tous les helpers Python du plugin (classification ruff/bandit, découverte des cibles de test, parsing des échecs pytest, résolution du runner) vivent sous `${CLAUDE_PLUGIN_ROOT}/tools/`. Ils sont invoqués directement par les skills via pipe. **Aucun script auxiliaire n'est jamais écrit dans le repo de l'utilisateur.** Le `git status` après une commande bt-ai ne contient que les fichiers attendus (fix de style, nouveaux tests, patches docs).

## Runner dispatch

Tous les skills/agents lisent `[tool.bt-ai].runner` dans `pyproject.toml` (défaut : `uv`) via `${CLAUDE_PLUGIN_ROOT}/tools/resolve_runner.py`, et invoquent les outils via `$R run <tool>` où `$R` vaut `uv` ou `poetry`. Configuré par `/bt-ai:proj-init` ; reste cohérent ensuite.

## Cycle de travail recommandé

1. Nouveau projet : `/bt-ai:proj-init`
2. Pendant le développement : utiliser les skills à la demande
3. Avant chaque PR : `/bt-ai:preflight`

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

## Architecture

Voir [docs/design.md](docs/design.md) pour la documentation complète : workflow, méthodologie, cas d'usage, justifications des choix d'outils.

## Licence

Proprietary — CGI.
