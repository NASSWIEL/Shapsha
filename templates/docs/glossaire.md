<!--
TEMPLATE — Glossaire et conventions
====================================
Public cible : (1) une IA qui doit nommer correctement un nouveau type / une nouvelle
table / une nouvelle classe sans réinventer une convention, (2) un humain qui croise
un acronyme et veut savoir ce qu'il signifie.

C'est la SOURCE DE VÉRITÉ du vocabulaire. Toute convention de nommage, tout terme métier,
tout acronyme spécifique au projet doit s'y rattacher. Si un terme manque ici, c'est qu'il
ne devrait pas exister dans le code.

Garde-fous :
- Distinguer "validé" / "(à confirmer)" / "(legacy — à éviter)".
- Tout terme cite au moins un endroit où il apparaît dans le code, la base, ou la doc
  fonctionnelle. Sinon, c'est un terme qui n'a pas sa place ici.
- Le glossaire référence ; il ne RE-DÉFINIT PAS les concepts qui sont décrits ailleurs.

Bloc « Mode d'emploi » en fin de fichier.
-->

# Glossaire et conventions de nommage — {{NOM_PROJET}}

| Champ | Valeur |
|---|---|
| **Dernière mise à jour** | {{AAAA-MM-JJ}} |
| **Mise à jour par** | {{Auteur PR / agent IA}} |
| **PR de référence** | {{#PR}} |
| **Périmètre** | {{Modules / domaines couverts}} |

> Source de vérité du vocabulaire projet. Termes marqués **(à confirmer)** = déductions à valider. Marqués **(legacy)** = conservés pour compatibilité, à ne pas reproduire.

---

## 1. Vocabulaire métier

### 1.1 Concepts centraux

| Terme | Définition | Représentation code | Apparaît dans |
|---|---|---|---|
| **{{Concept A}}** | {{1-2 lignes — définition métier, pas technique}} | {{Classe / table / champ}} | {{Modules / docs}} |
| **{{Concept B}}** | {{}} | {{}} | {{}} |

### 1.2 Règles de gestion (noms courts)

> Liste des règles métier nommées qui apparaissent dans le code, les commits, les tickets. Le détail vit dans [fonctionnel.md](fonctionnel.md).

| Nom court | Sens | Détail dans |
|---|---|---|
| **Règle X** | {{1 ligne}} | [fonctionnel.md#{{ancre}}](fonctionnel.md) |

### 1.3 États et transitions nommés

> Si le métier a des états explicites (statuts d'une commande, phases d'un workflow), les nommer ici.

| État | Sens | Transitions sortantes |
|---|---|---|
| `{{ETAT_A}}` | {{}} | → `{{ETAT_B}}`, `{{ETAT_C}}` |

---

## 2. Acronymes et abréviations

### 2.1 Acronymes métier

| Acronyme | Signification | Confiance | Origine |
|---|---|---|---|
| **{{ACR}}** | {{}} | ✓ / (à confirmer) | {{Doc projet / déduction}} |

### 2.2 Acronymes techniques

| Acronyme | Signification | Domaine |
|---|---|---|
| {{}} | {{}} | {{Stack / lib / pattern}} |

---

## 3. Conventions de nommage — Code

### 3.1 Packages / modules

```
{{Pattern racine — ex. com.entreprise.projet.<domaine>.<couche>}}
```

| Segment | Valeurs autorisées | Exemple |
|---|---|---|
| `<domaine>` | {{Liste}} | {{}} |
| `<couche>` | `api`, `domain`, `application`, `infrastructure` | {{}} |

### 3.2 Classes

- **Casse** : {{PascalCase / snake_case selon langage}}
- **Suffixes par rôle** :

| Rôle | Suffixe | Exemple |
|---|---|---|
| Entité persistée | `Entity` ou aucun | {{`OrderEntity` / `Order`}} |
| Repository | `Repository` | {{`OrderRepository`}} |
| Service applicatif | `Service` | {{`OrderService`}} |
| Cas d'usage | `UseCase` ou `Handler` | {{}} |
| Contrôleur HTTP | `Controller` ou `Handler` | {{}} |
| DTO entrée | `Request` ou `Command` | {{}} |
| DTO sortie | `Response` ou `View` | {{}} |
| Exception | `Exception` ou `Error` | {{}} |

### 3.3 Méthodes et fonctions

- **Casse** : {{camelCase / snake_case}}
- **Verbes d'action** : `find*`, `create*`, `update*`, `delete*`, `is*`, `has*`, `can*`, `should*`
- **Booléens** : préfixe `is_` / `has_` / `can_` ; jamais de double négation
- **Async** : suffixe `*Async` (TypeScript) ou retourne `Mono<>` / `Future<>` (typage suffit)

### 3.4 Variables et constantes

- **Variables locales** : {{camelCase / snake_case}} — courtes mais explicites, pas d'abréviations cryptiques
- **Constantes** : {{UPPER_SNAKE_CASE}}
- **Énumérations** : `enum {{NomEnum}} { VALEUR_A, VALEUR_B }`
- **Identifiants** : conserver le terme métier (ex. `idEnvelope` plutôt que `envId` si « envelope » est le terme officiel)

### 3.5 Tests

| Type | Pattern de classe | Pattern de méthode |
|---|---|---|
| Unitaire | `<ClasseTestée>Test` | `should<Comportement>When<Condition>` |
| Intégration | `<ClasseTestée>IT` ou `*IntegrationTest` | idem |
| Contract | `<Interface>ContractTest` | idem |
| End-to-end | `<Parcours>E2ETest` | `<scénario fonctionnel>` |

### 3.6 Fichiers, branches, commits

- **Fichiers** : {{kebab-case.md / snake_case.py / PascalCase.java}}
- **Branches** : {{`feat/...`, `fix/...`, `chore/...`}}
- **Commits** : {{Conventional Commits — `feat(scope): description`}}

---

## 4. Conventions de nommage — Données

> Sync avec [data-model.md §9.1](data-model.md). Lister ici uniquement les conventions DE NOMMAGE ; les détails de typage vivent côté data-model.

### 4.1 Préfixes de colonnes / champs

| Préfixe | Sémantique | Exemple |
|---|---|---|
| `id_` | Identifiant technique | `id_order` |
| `ref_` | Référence métier alphanum | `ref_customer` |
| `cd_` | Code discret | `cd_status` |
| `dt_` | Date | `dt_created` |
| `is_` / `has_` | Booléen | `is_active` |
| `nb_` / `qty_` | Quantité | `nb_items` |
| `lib_` / `label_` | Libellé | `label_status` |

### 4.2 Suffixes temporels

| Suffixe | Sens | Exemple |
|---|---|---|
| `*_at` | Instant ponctuel (timestamp) | `created_at` |
| `*_on` | Date sans heure | `effective_on` |
| `*_deb` / `*_fin` | Bornes de période | `dt_deb_validite` |

### 4.3 Tables / collections

- **Casse** : {{snake_case / PascalCase}}
- **Singulier ou pluriel** : {{Choisir UN — ex. `user` ou `users`, conserver partout}}
- **Tables de liaison N:N** : {{`<a>_<b>` ordonnés alphabétiquement}}
- **Tables d'audit** : {{Suffixe `_audit` / `_history` / dans schéma `audit`}}

---

## 5. Conventions de nommage — Interfaces

### 5.1 Endpoints HTTP

- **Casse** : `kebab-case` dans les paths
- **Pluriel pour les collections** : `/orders`, `/orders/{id}`
- **Verbes** : à éviter dans les paths sauf actions hors CRUD (`/orders/{id}:cancel`)
- **Versioning** : {{`/v1/...`}}

### 5.2 Topics / queues

```
{{Pattern — ex. <env>.<domaine>.<entité>.<événement>}}
```

| Segment | Valeurs |
|---|---|
| `<env>` | `dev`, `stg`, `prod` |
| `<domaine>` | {{Liste}} |
| `<entité>` | {{Singulier}} |
| `<événement>` | `created`, `updated`, `deleted`, métier (`shipped`, `cancelled`) |

### 5.3 Schémas d'événements

- **Champs systématiques** : `id`, `event_type`, `schema_version`, `occurred_at`, `producer`
- **Casse champs** : {{snake_case / camelCase — choisir UN}}
- **Versioning** : champ `schema_version` (entier monotone)

---

## 6. Vocabulaire technique

### 6.1 Stack

| Terme | Définition | Lien |
|---|---|---|
| **{{Framework / lib }}** | {{1 ligne — rôle dans le projet}} | [{{}}]({{}}) |

### 6.2 Patterns

| Pattern | Sens dans ce projet | Où il est appliqué |
|---|---|---|
| **{{Hexagonal / Strangler / Saga / Outbox / CQRS}}** | {{1 ligne}} | {{Modules}} |

### 6.3 Démarche / process

| Terme | Définition |
|---|---|
| **{{Trunk-based / GitFlow / Shape-Up}}** | {{}} |
| **{{Code review}}** | {{Règles internes}} |
| **{{ADR}}** | Architecture Decision Record — décisions traçables, voir {{lien dossier ADR}} |

---

## 7. Termes à éviter / pièges de vocabulaire

> Termes ambigus, faux amis, ou collisions avec des termes techniques. Cette section évite les confusions répétitives.

| Terme | Pourquoi l'éviter | Préférer |
|---|---|---|
| {{}} | {{Ambiguïté entre A et B / collision avec un terme technique standard}} | {{Terme désambiguïsé}} |
| `xxx` (legacy) | {{Conservé pour compat ; ne pas reproduire}} | {{Nouveau terme officiel}} |

---

## 8. Correspondance / mapping

> À utiliser si le projet a deux vocabulaires en parallèle (ex. ancien système → nouveau, métier → technique, API publique → modèle interne). Sinon, supprimer la section.

| {{Vocabulaire A}} | {{Vocabulaire B}} | Note |
|---|---|---|
| {{}} | {{}} | {{}} |

---

## 9. Questions ouvertes

> Ambiguïtés à lever avec les experts. Une question marquée non résolue depuis longtemps est un signal — voir [index.md §5](index.md#5-signaux-de-dérive-à-surveiller).

| # | Question | Impact | Owner | Ouverte depuis |
|---|---|---|---|---|
| Q1 | {{}} | {{Bloquant / cosmétique}} | {{}} | {{AAAA-MM-JJ}} |

---

## Références

- Architecture (où ces termes sont utilisés en pratique) : [architecture.md](architecture.md)
- Modèle de données (conventions colonnes détaillées) : [data-model.md](data-model.md)
- Contrats (conventions interfaces détaillées) : [contracts.md](contracts.md)
- Fonctionnel (règles métier nommées) : [fonctionnel.md](fonctionnel.md)
- ADR : [{{dossier ADR}}]({{dossier ADR}})

---

<!--
MODE D'EMPLOI DU TEMPLATE
=========================

POUR L'IA QUI MET À JOUR CE FICHIER

Déclencheurs :

| Modification dans la PR | Sections à toucher |
|---|---|
| Nouveau concept métier introduit dans le code | §1.1 |
| Nouvelle règle de gestion nommée | §1.2 (avec lien vers fonctionnel.md) |
| Nouvel état dans une machine à états | §1.3 |
| Nouvel acronyme dans des noms de classe / table / variable | §2 |
| Nouvelle convention de package / classe / méthode | §3 |
| Nouvelle convention de table / colonne | §4 (et data-model.md §9) |
| Nouvelle convention d'endpoint / topic | §5 |
| Nouveau pattern adopté | §6.2 |
| Renommage / dépréciation d'un terme | §7 (« legacy ») |

Règles spéciales :
- Quand on RENOMME un terme, ne pas supprimer l'ancien : le déplacer en §7 « legacy »
  avec le pointeur vers le nouveau, pendant au moins 1 cycle de release.
- Une convention ne s'AJOUTE qu'avec un exemple vivant dans le code (lien direct).
- Les questions ouvertes §9 vieillissent — celles sans MAJ depuis 90 jours doivent être
  signalées dans la PR.

Auto-checks :
- [ ] Chaque concept §1.1 cite au moins une représentation code réelle.
- [ ] Aucun acronyme §2 marqué ✓ ne reste sans occurrence dans le code.
- [ ] Les liens §Références sont valides.
- [ ] Section §7 ne déprécie aucun terme encore activement utilisé.

POUR LE RELECTEUR HUMAIN

- Le glossaire vieillit mal si on n'élague pas : terme inutilisé → le retirer (ou le passer
  en legacy si renommé).
- Les § « (à confirmer) » doivent être levés ou explicitement assumés.
- Vérifier la cohérence avec data-model §9 et contracts §1 — pas de doublon, pas d'écart.

POUR ADAPTER À UN AUTRE PROJET

1. Le glossaire est le document le plus DÉPENDANT du domaine — repartir de zéro pour §1.
2. §3 et §4 sont les plus stables — les conventions Java / SQL standard se répliquent.
3. Si le projet a un seul domaine simple, fusionner §1.1 et §1.2.
4. Pour un projet multi-langage, dédoubler §3 par langage (§3.A Java, §3.B Python, etc.).
-->
