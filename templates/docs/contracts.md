<!--
TEMPLATE — Contrats d'interface
================================
Public cible : (1) une IA qui doit appeler / modifier une interface sans relire toutes les
définitions OpenAPI / proto / handler, (2) un humain qui prend le projet.

Ce document décrit TOUS les points d'interaction du système : APIs exposées, APIs consommées,
événements (in / out), commandes CLI, jobs batch, fichiers d'entrée/sortie. C'est le « plan
de vol » des entrées/sorties — toute requête qui entre, toute donnée qui sort, doit y figurer.

Garde-fous :
- Toute signature listée doit pointer vers le code authoritatif (handler, contrôleur,
  schéma OpenAPI, fichier proto). Si pas de pointeur précis, marquer "(à confirmer)".
- Codes d'erreur listés DOIVENT être couverts par au moins un test ; sinon le signaler.
- Le format des payloads est résumé ici, le détail vit dans les schémas (lien §0).

Bloc « Mode d'emploi » en fin de fichier.
-->

# Contrats d'interface — {{NOM_PROJET}}

| Champ | Valeur |
|---|---|
| **Dernière mise à jour** | {{AAAA-MM-JJ}} |
| **Mise à jour par** | {{Auteur PR / agent IA}} |
| **PR de référence** | {{#PR}} |
| **Type d'interfaces** | {{REST / gRPC / GraphQL / Event-driven / CLI / Batch / appels natifs / mixte}} |
| **Schémas authoritatifs** | {{Liens — OpenAPI, .proto, AsyncAPI, JSON Schema}} |

> **Résumé en 1 phrase** : {{Le système expose X vers Y, consomme Z, et persiste via …}}

---

## 0. Inventaire global

| Type d'interface | Nombre | Schéma authoritatif |
|---|---|---|
| **Endpoints HTTP exposés** | {{N}} | [{{openapi.yaml}}]({{lien}}) |
| **Endpoints HTTP consommés** | {{N}} | {{Catalog interne / docs partenaire}} |
| **Topics / queues produits** | {{N}} | [{{asyncapi.yaml}}]({{lien}}) |
| **Topics / queues consommés** | {{N}} | {{}} |
| **Commandes CLI** | {{N}} | [{{cli/README}}]({{lien}}) |
| **Jobs / batchs** | {{N}} | [{{}}]({{lien}}) |
| **Fichiers E/S (formats fixes)** | {{N}} | [§9](#9-formats-des-es-physiques) |

---

## 1. Conventions transverses des interfaces

### 1.1 Authentification et autorisation

| Type d'interface | Mécanisme | Token / claims | Refresh / rotation |
|---|---|---|---|
| **API publique** | {{OIDC bearer / mTLS / API key}} | {{Liste claims requis}} | {{}} |
| **API interne** | {{Service mesh / mTLS / JWT interne}} | {{}} | {{}} |
| **Événements** | {{Signed envelope / partition ACL}} | {{}} | {{}} |
| **CLI / Batch** | {{Compte service / kubeconfig / clé SSH}} | {{}} | {{}} |

### 1.2 En-têtes / métadonnées standards

| En-tête / champ | Rôle | Direction | Obligatoire ? |
|---|---|---|---|
| `X-Request-Id` | Corrélation | I/O | Oui (généré si absent) |
| `traceparent` | Tracing W3C | I/O | Propagé |
| `Idempotency-Key` | Idempotence | I (mutations) | {{Oui pour POST mutateurs}} |
| `Accept-Language` | i18n | I | Optionnel |
| {{Custom}} | {{}} | {{}} | {{}} |

### 1.3 Codes d'erreur normalisés

> Catégoriser. Tout endpoint doit s'aligner sur ce barème — les déviations sont listées dans le bloc de l'endpoint et tracées comme dette.

| Catégorie | HTTP | Code applicatif | Sens | Idempotent ? |
|---|---|---|---|---|
| Succès | 200 / 201 / 204 | `OK` | — | — |
| Validation | 400 | `INVALID_INPUT` | Schéma / contrainte côté client | Oui |
| Auth manquante | 401 | `UNAUTHENTICATED` | Pas de credential | Oui |
| Auth refusée | 403 | `FORBIDDEN` | Credential OK mais droit absent | Oui |
| Ressource absente | 404 | `NOT_FOUND` | — | Oui |
| Conflit | 409 | `CONFLICT` | État incompatible | — |
| Trop de requêtes | 429 | `RATE_LIMITED` | Avec `Retry-After` | Oui |
| Erreur serveur | 500 | `INTERNAL_ERROR` | Bug ou état incohérent | — |
| Service tiers KO | 502 / 503 / 504 | `UPSTREAM_*` | Avec corrélation | — |

### 1.4 Format de réponse d'erreur

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "human-readable",
    "details": [
      { "field": "email", "rule": "format" }
    ],
    "trace_id": "..."
  }
}
```

> Aligné sur {{RFC 7807 Problem Details / format maison / autre}}.

### 1.5 Versioning

- **API HTTP** : {{`/v1/...` dans le path / header `Accept: application/vnd.x.v2+json` / autre}}
- **Événements** : {{Champ `schema_version` dans l'enveloppe / topic suffixé}}
- **Politique de breaking change** : {{Annonce N mois avant, support N versions, deprecation header}}

---

## 2. APIs exposées (HTTP / gRPC / GraphQL)

> Une sous-section par groupe fonctionnel ou ressource. Bloc identique pour chaque endpoint à dupliquer.

### 2.1 `{{GROUPE / RESSOURCE}}`

#### `{{VERBE}} {{path}}` — {{1 ligne de description}}

| Méta | Valeur |
|---|---|
| **Code source** | [{{chemin/handler.ext}}]({{chemin/handler.ext}}) |
| **Schéma** | [{{lien openapi.yaml#operation}}]({{lien}}) |
| **Auth requise** | {{Scope / rôle}} |
| **Idempotent** | {{Oui / Non}} |
| **Rate-limited** | {{N req/min}} |
| **SLO p95** | {{}} ms |

**Requête**

| Paramètre | Localisation | Type | Obligatoire | Description |
|---|---|---|---|---|
| `{{param}}` | {{path / query / header / body}} | {{string / int / object}} | {{Y/N}} | {{1 ligne}} |

**Body** (si applicable)

```json
{ "{{champ}}": "{{type}}" }
```

**Réponses**

| Code | Sens | Body |
|---|---|---|
| 200 | OK | `{{ResourceDto}}` |
| 400 | `INVALID_INPUT` | Erreur standard |
| 404 | `NOT_FOUND` | Erreur standard |
| {{N}} | {{Cas spécifique}} | {{}} |

**Effets de bord**

- {{Tables modifiées, événements émis, services aval appelés}}

**Pièges / particularités**

- ⚠️ {{Comportement non évident — ex. ordre de validation, header obligatoire en pratique mais pas en schéma}}

---

## 3. APIs consommées

> Une ligne par dépendance. Le détail des contrats vit chez le fournisseur — ici on note ce dont on dépend et comment on s'en protège.

| Service | Endpoint | Type | Criticité | Timeout | Retry | Circuit breaker |
|---|---|---|---|---|---|---|
| {{Nom}} | {{`POST /...`}} | {{Sync}} | {{Bloquante / dégradable}} | {{ms}} | {{Politique}} | {{Seuils}} |

**Modes dégradés** : {{Quoi faire si chaque service tiers est KO — fallback, cache, rejet propre.}}

---

## 4. Événements / messages

### 4.1 Topics produits

> Une section par topic. Schémas dans {{registry / repo / asyncapi.yaml}}.

#### `{{nom-du-topic}}` — {{rôle métier}}

| Méta | Valeur |
|---|---|
| **Broker** | {{Kafka / RabbitMQ / SQS / EventBridge}} |
| **Cluster / namespace** | {{}} |
| **Schéma** | [{{lien}}]({{lien}}) |
| **Format** | {{Avro / JSON / Protobuf}} |
| **Partition key** | {{Champ}} |
| **Versioning** | {{Champ `schema_version`}} |
| **Producteur(s)** | {{Composants émetteurs}} |
| **Consommateurs connus** | {{Liste}} |
| **Garanties** | {{At-least-once / exactly-once / at-most-once}} |
| **Ordre** | {{Garanti par partition / global / non}} |
| **Rétention** | {{Durée}} |

**Payload**

```json
{
  "schema_version": 1,
  "{{champ}}": "{{type}}"
}
```

**Émission**

| Quand | Composant | Trigger |
|---|---|---|
| {{Création d'un X}} | {{`OrderService`}} | {{Après commit DB}} |

**Pièges**

- ⚠️ {{Ordre vs partition, dédup, gestion des doublons côté consommateur}}

### 4.2 Topics consommés

> Bloc identique mais focalisé sur la **consommation**. Si on consomme un topic produit ailleurs (autre équipe / autre service), la liste des champs UTILISÉS est plus importante que le schéma complet.

#### `{{nom-du-topic}}`

- **Producteur** : {{Service / équipe}}
- **Schéma** : [{{lien}}]({{lien}})
- **Champs utilisés par nous** : {{Liste précise}}
- **Champs ignorés** : {{Liste — important pour anticiper les futurs ajouts}}
- **Idempotence côté consommateur** : {{Comment on dédupe — clé idempotence, table de dédup, design idempotent}}
- **Stratégie en cas de message non-parsable** : {{DLQ / log + skip / arrêt du consommateur}}

---

## 5. Commandes CLI

| Commande | Rôle | Code source | Authentif | Effets de bord |
|---|---|---|---|---|
| `{{cmd args}}` | {{1 ligne}} | [{{chemin}}]({{chemin}}) | {{}} | {{Lecture / écriture / réseau}} |

---

## 6. Jobs / batchs

### 6.1 `{{NOM_JOB}}` — {{rôle}}

| Méta | Valeur |
|---|---|
| **Type** | {{Cron / déclenché / streaming}} |
| **Périodicité** | {{`0 2 * * *`}} |
| **Code source** | [{{chemin}}]({{chemin}}) |
| **Entrées** | {{Fichiers / topics / tables}} |
| **Sorties** | {{Fichiers / topics / tables}} |
| **Durée typique** | {{Min / max / p95}} |
| **Scope transactionnel** | {{Commit par chunk de N / global / aucun}} |
| **Rejouable** | {{Idempotent / nécessite cleanup}} |
| **Comportement en erreur** | {{Fail-fast / continue-on-error / DLQ}} |

**Compteurs émis** : {{Lus / traités / créés / modifiés / rejetés — pour les dashboards}}

---

## 7. Mode d'appel inter-composants (interne)

> Si le système expose des appels internes (services qui se parlent dans le même processus, ou via un bus interne), documenter ici le pattern. Sinon, supprimer.

```{{langage}}
{{Pseudo-code de l'appel canonique avec instrumentation, propagation de contexte, gestion d'erreur}}
```

**Points-clés** :

- {{Propagation de contexte — corrélation ID, user ID, tenant}}
- {{Instrumentation systématique — métrique, span}}
- {{Gestion des erreurs — exception typée, code retour, abort}}

---

## 8. Matrice d'appels

> Lignes = appelants. Colonnes = appelés. Cellule = mode d'appel. Vide = aucun appel.
> Légende : ✓ = inconditionnel · (c) = conditionnel (préciser dans le bloc concerné).

| Appelant ↓ / Appelé → | `{{S1}}` | `{{S2}}` | `{{S3}}` | `{{S4}}` |
|---|---|---|---|---|
| **`{{ORCH}}`** | ✓ | ✓ | (c) | ✓ |
| **`{{S1}}`** | — | — | — | — |
| **`{{S2}}`** | — | — | — | ✓ |

> Une ligne / colonne vide = composant terminal ou racine. C'est une information.

---

## 9. Formats des E/S physiques

> Pour tout fichier ou flux à structure fixe lu/écrit par le système.

### 9.1 `{{NOM_FICHIER}}` — {{rôle (entrée / sortie / archive)}}

- **Type** : {{Séquentiel longueur fixe / CSV / JSON Lines / Parquet / XML}}
- **Encodage** : {{UTF-8 / latin-1 / EBCDIC}}
- **Délimiteur** : {{si CSV}}
- **Taille typique** : {{N lignes / X MB}}

| Offset / champ | Longueur / type | Description |
|---|---|---|
| {{}} | {{}} | {{}} |

---

## 10. Transactions, commits, rollback

| Composant | Scope transactionnel | Commit | Rollback |
|---|---|---|---|
| {{Service X}} | {{Par requête / par job / aucun}} | {{Auto / explicite / par chunk}} | {{Sur exception typée / aucun}} |

> Cas critiques où l'atomicité matters : {{lister explicitement les transactions multi-tables et les sagas}}.

---

## 11. Contraintes non-fonctionnelles par interface

| Interface | Latence p95 cible | Disponibilité | Idempotence | Re-entrance |
|---|---|---|---|---|
| {{Endpoint / topic}} | {{}} | {{}} | {{Oui / Non — par quel mécanisme}} | {{}} |

---

## 12. Tests de contrat

| Interface | Outil | Localisation | Côté |
|---|---|---|---|
| {{Endpoint X}} | {{Pact / Spring Cloud Contract / dredd}} | [{{chemin}}]({{chemin}}) | {{Provider / Consumer / les deux}} |

---

## 13. Recommandations actives

1. **{{Action}}** — {{Justification, ticket}}

---

## Références

- Architecture : [architecture.md](architecture.md)
- Modèle de données (effets de bord en base) : [data-model.md](data-model.md)
- Glossaire : [glossaire.md](glossaire.md)
- Règles fonctionnelles applicables aux endpoints : [fonctionnel.md](fonctionnel.md)

---

<!--
MODE D'EMPLOI DU TEMPLATE
=========================

POUR L'IA QUI MET À JOUR CE FICHIER

Déclencheurs (mettre à jour les sections concernées si la PR touche…) :

| Modification dans la PR | Sections à relire |
|---|---|
| Nouvel endpoint HTTP / gRPC / GraphQL | §0, §2 (nouveau bloc) |
| Modification de signature endpoint | §2 (bloc concerné), §1.3 si nouveau code d'erreur |
| Nouvel appel à un service externe | §0, §3 |
| Nouveau topic / event produit | §0, §4.1 |
| Nouveau topic / event consommé | §0, §4.2 |
| Nouvelle commande CLI | §0, §5 |
| Nouveau job batch | §0, §6 |
| Nouveau format de fichier E/S | §0, §9 |
| Changement de mécanisme d'auth | §1.1 |
| Nouvel en-tête transverse | §1.2 |
| Nouveau code d'erreur normalisé | §1.3, §1.4 si format évolue |
| Nouvel appel inter-composants interne | §7, §8 (matrice) |
| SLO / timeout / retry modifié | §3 (si externe), §11 (si exposé) |
| Nouveau test de contrat | §12 |

Auto-checks :
- [ ] Chaque endpoint §2 pointe vers un fichier source réel.
- [ ] Les codes de §1.3 sont effectivement émis quelque part dans le code.
- [ ] La matrice §8 ne mentionne aucun composant supprimé.
- [ ] Tout topic §4 a un schéma référencé.
- [ ] Aucune (à confirmer) > 60 jours sans ticket.

POUR LE RELECTEUR HUMAIN

- Vérifier la cohérence avec OpenAPI / proto : si écart, signaler dans la PR.
- Les SLO §11 doivent provenir d'un dashboard ou d'un ADR, pas être inventés.
- Si la matrice §8 devient illisible (trop de colonnes), envisager un découpage par domaine.

POUR ADAPTER À UN AUTRE PROJET

1. Si le système n'expose RIEN au monde extérieur (lib pure) : §1, §2, §3 deviennent
   minces ; §7 (appels internes) devient le cœur du document.
2. Si le système est PUREMENT batch : déplacer §6 en début de document, §2 et §3 disparaissent.
3. Si le système est event-only : §4 devient le cœur, structurer par flux.
4. Garder le pattern « inventaire global §0 + détails ensuite » même si certaines catégories
   sont vides : « 0 endpoints exposés » est une information utile.
5. Pour les systèmes critiques en sécurité, dédoubler §2 par niveau de criticité (publique
   non authentifiée / authentifiée / interne / admin).
-->
