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

## Commandes

| Commande | Rôle |
|---|---|
| `/bt-ai:proj-init` | Bootstrap d'un projet Python (outils + configs + templates) |
| `/bt-ai:check-style` | Lint des fichiers modifiés (ruff) |
| `/bt-ai:security` | Analyse sécurité des fichiers modifiés (bandit) |
| `/bt-ai:gen-tests` | Génère les tests pytest manquants |
| `/bt-ai:doc-sync` | Synchronise `docs/` avec le code |
| `/bt-ai:readme-sync` | Met à jour `README.md` si surface utilisateur change |
| `/bt-ai:preflight` | Suite complète avant PR |
| `/bt-ai:commit` | Commit Conventional Commits |
| `/bt-ai:commit-push-pr` | Commit + push + ouverture PR |

## Mode silencieux

Tous les skills exécutent les outils sans narration. Pas de "je fais ceci, je fais cela". Chaque commande retourne uniquement son résultat final.

## Pré-requis

- [uv](https://docs.astral.sh/uv/) **ou** [poetry](https://python-poetry.org/) installé (`/bt-ai:proj-init` détecte la forme du projet et propose un défaut)
- `git`
- `gh` (GitHub CLI) authentifié pour `/bt-ai:commit-push-pr` et `/bt-ai:preflight`

## Cycle de travail recommandé

1. Nouveau projet : `/bt-ai:proj-init`
2. Pendant le développement : utiliser les skills à la demande
3. Avant chaque PR : `/bt-ai:preflight`

## Architecture

Voir [special-plugin-doc.md](special-plugin-doc.md) pour la documentation complète : workflow, méthodologie, cas d'usage, justifications des choix d'outils.

## Licence

Proprietary — CGI.
