# bt-ai — plugin Claude Code

Standardise les pratiques Python d'équipe : style, sécurité, tests, documentation, pré-commit, initialisation projet.

## Installation

```bash
git clone https://github.com/NASSWIEL/bt-ai-plugin.git
```

Dans Claude Code :

```
/plugin marketplace add /chemin/vers/bt-ai-plugin
/plugin install bt-ai
```

## Pré-requis

- [uv](https://docs.astral.sh/uv/) **ou** [poetry](https://python-poetry.org/) installé (`/bt-ai:proj-init` détecte la forme du projet et propose un défaut)
- `git`
- `gh` (GitHub CLI) authentifié pour `/bt-ai:commit-push-pr` et `/bt-ai:preflight`

## Commandes

| Commande | Rôle |
|---|---|
| `/bt-ai:proj-init` | Bootstrap d'un projet Python (outils + configs + templates) |
| `/bt-ai:check-style` | Lint des fichiers modifiés (ruff) |
| `/bt-ai:security` | Analyse sécurité des fichiers modifiés (bandit) |
| `/bt-ai:gen-tests` | Génère les tests pytest manquants |
| `/bt-ai:doc-sync` | Synchronise `docs/` avec le code |
| `/bt-ai:readme-sync` | Met à jour `README.md` si la surface utilisateur change |
| `/bt-ai:preflight` | Suite complète avant PR |
| `/bt-ai:commit` | Commit Conventional Commits |
| `/bt-ai:commit-push-pr` | Commit + push + ouverture PR |

## Détail des skills

### `/bt-ai:proj-init`
Bootstrap d'un projet Python conforme aux standards bt-ai.
- Détecte la forme du projet (`uv` / `poetry` / `mixed` / `bare`) à partir de `pyproject.toml` et des lockfiles présents.
- Propose un runner par défaut, écrit `[tool.bt-ai].runner = "uv"` ou `"poetry"` (utilisé par tous les autres skills).
- Installe les outils manquants (ruff, bandit, pytest, pyright, gitlint, pre-commit) dans la bonne section selon le runner choisi (uv → `[dependency-groups]`, poetry → `[tool.poetry.group.*.dependencies]`) — pas de double déclaration.
- Fusionne les fragments TOML (`templates/pyproject/*.toml.fragment`) dans `pyproject.toml` via un merge intelligent par clé : union de tokens pour les chaînes de flags, union pour les listes, conservation du scalaire cible en cas de conflit.
- Copie les templates `docs/`, `README.md`, `.gitignore`, templates GitHub (PR + Issue) et `.gitlint`.

### `/bt-ai:check-style`
Lint des fichiers Python modifiés (staged, unstaged, untracked) via ruff.
- Classification : Critical (`F*`, `E9*`) / High (`B*`, `S*`) / Low (autres).
- Auto-fix silencieux des Low (`E`, `W`, `D`, `I`, `UP`).
- Demande confirmation avant d'appliquer les fix unsafe sur High (sous-ensemble whitelisté : `B007`, `B009`, `B010`, `B011`, `S101` dans `tests/`).
- Refuse les renames (`N*`) et les Critical : exit non-zero, l'humain tranche.
- Délègue les corrections à l'agent `style-fixer`.

### `/bt-ai:security`
Analyse bandit des fichiers Python modifiés.
- Filtre : sévérité ≥ MEDIUM **et** confiance ≥ MEDIUM (signal/bruit).
- Classifie FIXABLE vs BLOCKED. BLOCKED couvre les catégories à risque (`B102` exec, `B301` pickle, `B602` shell=True, etc.) que l'agent ne touche jamais.
- Délègue les fix à l'agent `security-fixer` qui n'agit que sur la whitelist FIXABLE.

### `/bt-ai:gen-tests`
Génère les tests pytest manquants. Deux modes :
- **Diff mode** (sans argument) : scanne les `*.py` modifiés en excluant `tests/**`.
- **Targeted mode** (chemins en argument) : génère pour ces fichiers uniquement.

Pour chaque symbole public sans test (function/method/AsyncFunction via AST), l'agent `test-writer` produit golden path + un cas d'erreur + une valeur limite, en miroir de l'arborescence source sous `tests/`. Ne réécrit jamais un test existant.

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

5 sous-agents Sonnet, contexte isolé, périmètre minimal :

| Agent | Tools | Rôle |
|---|---|---|
| `style-fixer` | Read, Edit, Bash | Applique les auto-fix ruff (safe + whitelist unsafe). Refuse renames, Critical, manuel. |
| `security-fixer` | Read, Edit | Applique les fix bandit hors blacklist. Par défaut "report-only" — la majorité reste manuelle. |
| `test-writer` | Read, Write, Edit, Glob, Bash | Génère les tests pytest manquants (golden + erreur + boundary). N'écrase jamais un test existant. |
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
3. **gen-tests (diff mode)** — halt si génération ou collection pytest échoue ; "tous déjà testés" est un pass.
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

## Runner dispatch

Tous les skills/agents lisent `[tool.bt-ai].runner` dans `pyproject.toml` (défaut : `uv`) et invoquent les outils via `$R run <tool>` où `$R` vaut `uv` ou `poetry`. Configuré par `/bt-ai:proj-init` ; reste cohérent ensuite.

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
│   └── test-writer.md
├── commands/
│   ├── commit.md
│   └── commit-push-pr.md
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
├── .gitignore
├── LICENSE
├── README.md
└── special-plugin-doc.md
```

## Architecture

Voir [special-plugin-doc.md](special-plugin-doc.md) pour la documentation complète : workflow, méthodologie, cas d'usage, justifications des choix d'outils.

## Licence

Proprietary — CGI.
