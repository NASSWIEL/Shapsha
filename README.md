# bt-ai — plugin Claude Code

> Standardise les pratiques Python d'équipe : style, sécurité, tests, documentation, pré-commit.

Plugin [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) qui regroupe sous des slash-commands (`/bt-ai:*`) un ensemble de skills silencieux, hermétiques et idempotents. Chaque skill agit sur le diff par défaut, applique les corrections sûres automatiquement, et n'interrompt que sur les signaux exigeant un jugement humain.

## Installation

```
/plugin marketplace add NASSWIEL/bt-ai-plugin
/plugin install bt-ai@CGI-BT-AI
```

## Pré-requis

- [`uv`](https://docs.astral.sh/uv/) **ou** [`poetry`](https://python-poetry.org/) — `proj-init` demande toujours le choix (`venv` ou `poetry`). `venv` utilise `uv` sous le capot.
- `git`.
- [`gh`](https://cli.github.com) authentifié (`gh auth login`) — requis pour `commit-push-pr` et `preflight`.

ruff, bandit, pyright, pytest, gitlint-core sont installés par `proj-init` dans l'environnement du projet.

## Commandes au quotidien

| Commande | Quand | Ce qu'elle fait |
|---|---|---|
| `/bt-ai:proj-init` | Une fois, à la création du projet | Demande le choix venv/poetry, installe les outils, dépose les configs et templates de docs |
| `/bt-ai:check-style` | Après modification de fichiers `.py` | Deux passes : ruff corrige tout ce qu'il peut (`--fix --unsafe-fixes`), puis le modèle corrige le reste (docstrings `D1xx`, renommages `N8xx`, imports manquants `F821`, erreurs de syntaxe `E999`, codes sécurité `S*`) en fan-out parallèle. Ne s'arrête jamais — tout est corrigé ou signalé |
| `/bt-ai:security` | Après modification de fichiers `.py` | Lance bandit sur tous les niveaux de sévérité. Propose un fix concret pour chaque finding, demande consentement une fois, puis corrige tout via fan-out parallèle. L'agent tente de tout corriger — ne refuse que quand le contexte est réellement ambigu |
| `/bt-ai:gen-tests` | Après ajout/modification de code applicatif | Génère des tests pytest en fan-out parallèle. Si les tests échouent, propose des améliorations du code source (pas des tests), demande consentement, applique (cap 2 itérations) |
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
| 1 | `check-style` | Jamais (tout est corrigé ou advisory) |
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
| `style-fixer` | Sonnet | `check-style` | Insère docstrings Google-style (`D1xx`), renomme arguments/variables locales (`N803`/`N806`), ajoute les imports manquants (`F821`), corrige les erreurs de syntaxe (`E999`), corrige les codes sécurité (`S113`, `S301`, `S311`, `S324`, `S501`–`S503`, `S506`, `S602`/`S605`/`S607`, `S608`) dans UN fichier. Refuse les renommages de classes/fonctions (`N801`/`N802`) — le parent les gère via Grep + MultiEdit |
| `security-fixer` | Sonnet | `security` | Applique les fix bandit proposés par le parent dans UN fichier, tous niveaux de sévérité (~30 codes couverts). Tente de tout corriger — ne refuse que quand le contexte est réellement ambigu (exec dynamique, pickle objets complexes, SQL driver inconnu) |
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

Skills et agents lisent `[tool.bt-ai].runner` dans `pyproject.toml` (`venv` ou `poetry`) via `tools/resolve_runner.py`, puis invoquent les outils via `<runner> run <tool>`. `venv` utilise `uv` sous le capot. Le choix est fait une fois par `proj-init` (qui demande toujours) et reste cohérent ensuite.

`gitlint-core` est utilisé à la place de `gitlint` pour éviter la dépendance `sh` (qui échoue à compiler sur Windows à cause de `fcntl`).

## Ressources

- **[docs/design.md](docs/design.md)** — workflow complet, méthodologie, justifications.
- **Repository** — [github.com/NASSWIEL/bt-ai-plugin](https://github.com/NASSWIEL/bt-ai-plugin).
- **Issues** — [github.com/NASSWIEL/bt-ai-plugin/issues](https://github.com/NASSWIEL/bt-ai-plugin/issues).

## Licence

Proprietary — CGI.
