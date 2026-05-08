# bt-ai — plugin Claude Code

> Standardise les pratiques Python d'équipe : style, sécurité, tests, documentation, pré-commit.

Plugin [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) qui regroupe sous des slash-commands (`/bt-ai:*`) un ensemble de skills silencieux, hermétiques et idempotents. Chaque skill agit sur le diff par défaut, applique les corrections sûres automatiquement, et n'interrompt que sur les signaux exigeant un jugement humain.

## Installation

```
/plugin marketplace add NASSWIEL/bt-ai-plugin
/plugin install bt-ai@CGI-BT-AI
```

## Pré-requis

- [`uv`](https://docs.astral.sh/uv/) **ou** [`poetry`](https://python-poetry.org/) — `proj-init` détecte la forme du projet et propose le bon défaut.
- `git`.
- [`gh`](https://cli.github.com) authentifié (`gh auth login`) — requis pour `commit-push-pr` et `preflight`.

ruff, bandit, pyright, pytest, gitlint-core sont installés par `proj-init` dans l'environnement du projet.

## Commandes au quotidien

| Commande | Quand | Ce qu'elle fait |
|---|---|---|
| `/bt-ai:proj-init` | Une fois, à la création du projet | Détecte la forme du projet, choisit le runner, installe les outils, dépose les configs et templates de docs |
| `/bt-ai:check-style` | Après modification de fichiers `.py` | Lance ruff. Affiche chaque finding avec un extrait de code (3 lignes). Halt sur Critical (`F*`, `E9*`). Pour le reste, corrige automatiquement : ruff fait les corrections mécaniques, le modèle insère les docstrings (`D1xx`) et applique les renommages (`N801`/`N802`/`N803`/`N806`) en parallèle |
| `/bt-ai:security` | Après modification de fichiers `.py` | Lance bandit. Pour chaque HIGH/HIGH, propose un fix concret et demande consentement une fois pour tout corriger. MEDIUM reste advisory |
| `/bt-ai:gen-tests` | Après ajout/modification de code applicatif | Génère des tests pytest, lance les tests, répare les échecs mécaniques (cap 3), interrompt sur échec sémantique |
| `/bt-ai:doc-sync` | Après changement d'API publique | Patch minimal pour `docs/` et docstrings ; appliqué automatiquement |
| `/bt-ai:readme-sync` | Après changement de surface utilisateur (CLI, env vars, deps) | Patch minimal pour `README.md` (français) ; appliqué automatiquement |
| `/bt-ai:commit` | Pour committer manuellement | Compose un Conventional Commit, valide via gitlint, commite. Pas de push |
| `/bt-ai:commit-push-pr` | Pour committer + pousser + ouvrir une PR | Commite (titre EN, corps FR), pousse, ouvre la PR. Refuse la branche par défaut et le force-push |
| `/bt-ai:preflight` | Avant chaque PR | Pipeline complet (voir ci-dessous). Termine par l'URL de la PR |

**Argument `all`** (optionnel sur `check-style`, `security`, `gen-tests`) : agit sur tout le repo au lieu du diff. Sans argument : fichiers modifiés uniquement.

## Pipeline preflight

`/bt-ai:preflight` est séquentiel, halt-on-failure, sans prompt. Sortie sur succès : l'URL de la PR.

| # | Étape | Halt si |
|---|---|---|
| 1 | `check-style` | Findings Critical (`F*`, `E9*`) |
| 2 | `security` | Findings HIGH/HIGH |
| 3 | `gen-tests` (diff) | Échec sémantique persistant après 3 réparations mécaniques |
| 4 | `pytest -q` (full suite) | Exit non-zero |
| 5 | `doc-sync` | Patch ne s'applique pas |
| 6 | `readme-sync` | Patch ne s'applique pas |
| 7 | Compose + valide message via gitlint | Gitlint rejette après une réécriture |
| 8 | `commit-push-pr` | `gh pr create` échoue |

**Gardes initiales** : refus si pas de repo git, aucun changement, changements unstaged uniquement, branche par défaut, ou `gh` absent / non authentifié.

**Stage handoff** : chaque sous-skill `git add` ses propres outputs ; preflight ne stage jamais les changements de l'utilisateur à sa place.

## Sous-agents

Contexte isolé, périmètre minimal, mode silent. Invoqués en parallèle par les skills parents (un agent par fichier, tous les `Task` dans le même message — fan-out).

| Agent | Modèle | Invoqué par | Rôle |
|---|---|---|---|
| `style-fixer` | Sonnet | `check-style` | Insère docstrings Google-style (`D1xx`) et renomme arguments/variables locales (`N803`/`N806`) dans UN fichier. Refuse les renommages de classes/fonctions (`N801`/`N802`) — le parent les gère via Grep + MultiEdit |
| `security-fixer` | Sonnet | `security` | Applique les fix bandit HIGH/HIGH proposés par le parent dans UN fichier (B101, B105/106/107, B201, B311, B324, B501–503, B602/605/607). Refuse les findings d'intention (B102, B301/302/306, B608) avec raison structurée |
| `test-writer` | Sonnet | `gen-tests` | Génère les tests pytest manquants pour UN fichier source (golden + erreur + boundary). Ne réécrit jamais les tests existants. Pas de `pytest.skip` |
| `test-fixer` | Haiku | `gen-tests` | Répare les échecs mécaniques pytest (imports, fixtures, args) sur UN fichier de test. One-shot, parent rappelle si nécessaire (cap 3). Lecture seule sur le code source |
| `doc-patcher` | Sonnet | `doc-sync` | Patche UN `docs/*.md` à partir des faits du code et d'un diff optionnel. Lit `index.md` + le doc cible uniquement, jamais les 6 |
| `readme-patcher` | Sonnet | `readme-sync` | Patche `README.md` quand une surface utilisateur change (CLI, env vars, deps). Ton français préservé |

## Philosophie de design

Inspirée du plugin [`commit-commands`](https://github.com/anthropics/claude-code) d'Anthropic.

- **Silence par défaut.** L'utilisateur voit le diff, le résultat final, ou la halt-line. Pas de narration intermédiaire.
- **Skills en tant que prompts**, pas state machines : prompts courts (≤ 100 lignes), contexte injecté via `!command` pré-exécuté, single-message incantation pour forcer les appels d'outils en parallèle.
- **`allowed-tools` étroits** (`Bash(git status:*)` plutôt que `Bash`) pour éviter les confirmations sur le chemin heureux.
- **`AskUserQuestion` uniquement pour l'ambiguïté réelle.** Seul `proj-init` en utilise (choix `uv`/`poetry`).
- **Refus systématiques** : pas de `--no-verify`, pas de `--force` push, pas de push sur la branche par défaut.
- **Hermétique.** Tous les helpers Python du plugin vivent sous `${CLAUDE_PLUGIN_ROOT}/tools/`. Aucun script auxiliaire n'est jamais écrit dans le repo de l'utilisateur.

## Runner dispatch

Skills et agents lisent `[tool.bt-ai].runner` dans `pyproject.toml` (défaut : `uv`) via `tools/resolve_runner.py`, puis invoquent les outils via `$R run <tool>`. Le choix est fait une fois par `proj-init` et reste cohérent ensuite.

`gitlint-core` est utilisé à la place de `gitlint` pour éviter la dépendance `sh` (qui échoue à compiler sur Windows à cause de `fcntl`).

## Ressources

- **[docs/design.md](docs/design.md)** — workflow complet, méthodologie, justifications.
- **Repository** — [github.com/NASSWIEL/bt-ai-plugin](https://github.com/NASSWIEL/bt-ai-plugin).
- **Issues** — [github.com/NASSWIEL/bt-ai-plugin/issues](https://github.com/NASSWIEL/bt-ai-plugin/issues).

## Licence

Proprietary — CGI.
