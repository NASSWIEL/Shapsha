# bt-ai — plugin Claude Code

> Standardise les pratiques Python d'équipe : style, sécurité, tests, documentation, pré-commit.

Plugin [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) qui regroupe sous des slash-commands (`/starter:*`) un ensemble de skills silencieux, hermétiques et idempotents. Chaque skill agit sur le diff par défaut, applique les corrections sûres automatiquement, et n'interrompt que sur les signaux exigeant un jugement humain.

## Installation

```
/plugin marketplace add NASSWIEL/bt-ai-plugin
/plugin install bt-ai@Shapsha
```

## Pré-requis

- [`uv`](https://docs.astral.sh/uv/) **ou** [`poetry`](https://python-poetry.org/) — `proj-init` demande toujours le choix (`venv` ou `poetry`). `venv` utilise `uv` sous le capot.
- `git`.
- [`gh`](https://cli.github.com) authentifié (`gh auth login`) — requis pour `commit-push-pr` et `preflight`.

ruff, bandit, pyright, pytest, gitlint-core sont installés par `proj-init` dans l'environnement du projet.

## Commandes au quotidien

| Commande | Quand | Ce qu'elle fait |
|---|---|---|
| `/starter:proj-init` | Une fois, à la création du projet | Demande le choix venv/poetry, installe les outils, dépose les configs et templates de docs |
| `/starter:check-style` | Après modification de fichiers `.py` | Deux passes : ruff corrige tout ce qu'il peut (`--fix --unsafe-fixes`), puis le modèle corrige **tout** le reste (docstrings, renommages, imports, syntaxe, sécurité, complexité, refactoring) en fan-out parallèle. Pas de bucket « advisory » — tout est corrigé ou refusé avec raison |
| `/starter:security` | Après modification de fichiers `.py` | Deux passes : bandit (tous niveaux de sévérité) puis analyse LLM-native (auth, injection, logique métier, secrets, crypto, effets de second ordre — confidence HIGH uniquement). Findings fusionnés, consentement unique, fan-out parallèle. L'agent tente de tout corriger — ne refuse que quand le contexte est réellement ambigu |
| `/starter:gen-tests` | Après ajout/modification de code applicatif | Génère des tests pytest en fan-out parallèle. Si les tests échouent, propose des améliorations du code source (pas des tests), demande consentement, applique (cap 2 itérations) |
| `/starter:doc-sync` | Après changement d'API publique | Patch minimal pour `docs/` et docstrings ; appliqué automatiquement |
| `/starter:readme-sync` | Après changement de surface utilisateur (CLI, env vars, deps) | Patch minimal pour `README.md` (français) ; appliqué automatiquement |
| `/starter:commit` | Pour committer manuellement | Compose un Conventional Commit, valide via gitlint, commite. Pas de push |
| `/starter:commit-push-pr` | Pour committer + pousser + ouvrir une PR | Commite (titre EN, corps FR), pousse, ouvre la PR. Refuse la branche par défaut et le force-push |
| `/starter:preflight` | Avant chaque PR | Pipeline complet (voir ci-dessous). Termine par l'URL de la PR |

**Argument `all`** (optionnel sur `check-style`, `security`, `gen-tests`) : agit sur tout le repo au lieu du diff. Sans argument : fichiers modifiés uniquement.

## Pipeline preflight

`/starter:preflight` est séquentiel, halt-on-failure, sans prompt. Sortie sur succès : l'URL de la PR.

| # | Étape | Halt si |
|---|---|---|
| 1 | `check-style` | Jamais (tout est corrigé ou refusé avec raison) |
| 2 | `security` | Utilisateur refuse le consentement ou findings restent après fix |
| 3 | `gen-tests` (diff) | Tests échouent après 2 itérations d'amélioration du code source, ou utilisateur refuse les améliorations |
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
| `style-fixer` | Sonnet | `check-style` | Corrige **tous** les codes ruff restants dans UN fichier : docstrings (`D1xx`), renommages (`N8xx`), imports (`F821`), syntaxe (`E999`), sécurité (`S*`), complexité (`C901`, `PLR*`), et tout autre code. Refuse uniquement les renommages cross-fichier (`N801`/`N802`) et les fixes réellement ambigus |
| `security-fixer` | Sonnet | `security` | Applique les fix de sécurité dans UN fichier — findings bandit (B-codes, ~30 couverts) et findings LLM (`LLM-AUTH`, `LLM-INJECTION`, etc.). Chaque finding arrive avec son fix proposé ; l'agent l'ancre dans le vrai code et l'applique. Tente de tout corriger — ne refuse que quand le contexte est réellement ambigu |
| `test-writer` | Sonnet | `gen-tests` | Génère les tests pytest manquants pour UN fichier source (golden + erreur + boundary). Ne réécrit jamais les tests existants. Pas de `pytest.skip` |
| `test-fixer` | Haiku | *(inutilisé)* | Répare les échecs mécaniques pytest (imports, fixtures, args) sur UN fichier de test. Conservé mais plus invoqué par `gen-tests` — le parent propose désormais des améliorations du code source quand les tests échouent |
| `doc-patcher` | Sonnet | `doc-sync` | Patche UN `docs/*.md` à partir des faits du code et d'un diff optionnel. Lit `index.md` + le doc cible uniquement, jamais les 6 |
| `readme-patcher` | Sonnet | `readme-sync` | Patche `README.md` quand une surface utilisateur change (CLI, env vars, deps). Ton français préservé |

## Philosophie de design

Inspirée du plugin [`commit-commands`](https://github.com/anthropics/claude-code) d'Anthropic.

- **Silence par défaut.** L'utilisateur voit le diff, le résultat final, ou la halt-line. Pas de narration intermédiaire.
- **Skills en tant que prompts**, pas state machines : prompts courts (≤ 100 lignes), contexte injecté via `!command` pré-exécuté, single-message incantation pour forcer les appels d'outils en parallèle.
- **`allowed-tools` étroits** (`Bash(git status:*)` plutôt que `Bash`) pour éviter les confirmations sur le chemin heureux.
- **`AskUserQuestion` uniquement pour l'ambiguïté réelle.** Seul `proj-init` (choix `venv`/`poetry`), `security` (consentement avant correction) et `gen-tests` (consentement avant modification du code source) en utilisent.
- **Refus systématiques** : pas de `--no-verify`, pas de `--force` push, pas de push sur la branche par défaut.
- **Hermétique.** Tous les helpers Python du plugin vivent sous `${CLAUDE_PLUGIN_ROOT}/tools/`. Aucun script auxiliaire n'est jamais écrit dans le repo de l'utilisateur.

## Runner dispatch

Skills et agents lisent `[tool.starter].runner` dans `pyproject.toml` (`venv` ou `poetry`) via `tools/resolve_runner.py`, puis invoquent les outils via `<runner> run <tool>`. `venv` utilise `uv` sous le capot. Le choix est fait une fois par `proj-init` (qui demande toujours) et reste cohérent ensuite.

`gitlint-core` est utilisé à la place de `gitlint` pour éviter la dépendance `sh` (qui échoue à compiler sur Windows à cause de `fcntl`).

## Ressources

- **[docs/design.md](docs/design.md)** — workflow complet, méthodologie, justifications.
- **Repository** — [github.com/NASSWIEL/bt-ai-plugin](https://github.com/NASSWIEL/bt-ai-plugin).
- **Issues** — [github.com/NASSWIEL/bt-ai-plugin/issues](https://github.com/NASSWIEL/bt-ai-plugin/issues).

## Licence

Proprietary — CGI.
