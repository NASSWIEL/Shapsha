<!--
TEMPLATE — Modèle de données
============================
Public cible : (1) une IA qui écrit du code touchant à la persistance et doit raisonner
sur le schéma sans relire le SQL/ORM, (2) un humain qui prend le projet.

Doit permettre de RAISONNER sur les données sans ouvrir une seule migration. Catalogue
exhaustif, ordonné par importance fonctionnelle (pivot d'abord), pas par ordre alphabétique.

Garde-fous d'écriture :
- Tout type, contrainte, index = vérifiable depuis le DDL versionné OU le code (annotations
  ORM, schéma de validation). Si ni l'un ni l'autre, marquer "(à confirmer)".
- Les volumétries citées sont datées et tracent leur source (dashboard, requête, anonymisée
  depuis prod, etc.).
- Une cellule "non utilisé / aucun accès" est UNE INFORMATION — ne pas la supprimer.

Bloc « Mode d'emploi » en fin de fichier.
-->

# Modèle de données — {{NOM_PROJET}}

| Champ | Valeur |
|---|---|
| **Dernière mise à jour** | {{AAAA-MM-JJ}} |
| **Mise à jour par** | {{Auteur PR / agent IA}} |
| **PR de référence** | {{#PR}} |
| **SGBD / Stockage** | {{PostgreSQL 15 / Oracle 19c / DynamoDB / MongoDB / mixte}} |
| **État du DDL** | {{Versionné dans `db/migrations/` / Reconstitué depuis le code / Géré par ORM (Liquibase, Flyway, Alembic, Prisma…)}} |
| **Source d'extraction** | {{Chemins parcourus pour produire ce document}} |

> **Résumé en 1 phrase** : {{À quoi sert cette base — quels concepts métier elle persiste.}}

---

## 1. Vue d'ensemble

| Indicateur | Valeur | Source |
|---|---|---|
| **Nombre de tables / collections** | {{N}} | {{}} |
| **Nombre de domaines fonctionnels** | {{M}} | {{}} |
| **Relations** | {{K}} (dont {{K1}} FK déclarées, {{K2}} implicites) | {{}} |
| **Objets non-table** | {{V}} (vues, séquences, triggers, fonctions) | {{}} |
| **Volume total approximatif** | {{Lignes / GB / docs}} | {{Dashboard ou requête datée}} |
| **Croissance** | {{Linéaire / append-only / plateau}} | {{}} |

> _Résumé en 3 lignes : à quoi sert cette base ? Quels sont les concepts pivots ?_
>
> {{Texte court — ne pas dépasser 5 lignes. Identifier le ou les pivots, le pattern temporel global, et le mode dominant (lecture / écriture / mixte).}}

---

## 2. Vue d'ensemble par domaine

> Les tables sont regroupées par **rôle fonctionnel**, pas par ordre alphabétique. Une cellule vide dans la matrice d'accès §7 est une information en soi : elle signifie « aucun accès ».

```
{{Schéma ASCII des domaines — encadrés par domaine, flèches pour les liens entre domaines.
Lister pour chaque table : nom, PK, colonnes-clés, FK sortantes.

Exemple de format :
┌─── Catalogue ──────────────────────┐   ┌─── Transactions ─────────────────┐
│   USER (PK: id)                    │   │   ORDER (PK: id)                  │
│   PRODUCT (PK: id)                 │──▶│   ├─ user_id (FK USER)            │
│                                    │   │   └─ created_at                   │
└────────────────────────────────────┘   └───────────────────────────────────┘
}}
```

---

## 3. Diagramme entité-relation

```mermaid
erDiagram
    {{ENTITE_A}} ||--o{ {{LIEN_AB}} : "rel sémantique"
    {{ENTITE_B}} ||--o{ {{LIEN_AB}} : "rel sémantique"
    {{ENTITE_A}} ||--|| {{ENTITE_C}} : "1:1"
    {{ENTITE_D}} }o--o{ {{ENTITE_E}} : "N:N (via table de liaison)"
```

> Cardinalités Mermaid : `||--o{` = 1:N · `||--||` = 1:1 · `}o--o{` = N:N · `||--o|` = 1:0..1.
> Si une relation est **observée** mais non déclarée en base, l'indiquer dans la table §4.

---

## 4. Relations

> Une ligne par arête. Ordonner par centralité : pivot d'abord, feuilles après.

| Source | Cible | Cardinalité | Clé(s) | Déclarée ? | Sémantique |
|---|---|---|---|---|---|
| `{{TABLE_A}}` | `{{TABLE_B}}` | N:1 | `{{col}}` | {{FK / Index unique / Implicite (code) / Snapshot}} | {{1 ligne}} |

> ⚠️ Lister explicitement les FK **manquantes** (intégrité tenue par le code) — ce sont les zones de risque pour toute migration ou refactor.

---

## 5. Catalogue des tables

> Un bloc complet par table **pivot** ou **fréquemment écrite**. Un bloc abrégé pour les référentiels stables. Ordre : pivot → catalogue → liens → audit.

### 5.1 `{{TABLE_PIVOT}}` — {{rôle métier en 1 phrase}}

| Méta | Valeur |
|---|---|
| **Domaine** | {{}} |
| **Accédée par** | {{Liste de composants/services}} |
| **Volumétrie** | {{Ordre de grandeur — daté}} |
| **Mode dominant** | {{Lecture / écriture / mixte}} |
| **PK** | {{Composite ou simple}} |
| **FK sortantes** | {{Liste — déclarées ou implicites}} |
| **Index** | {{PK + secondaires nommés}} |
| **Pattern temporel** | {{Aucun / SCD2 / append-only / soft-delete}} |

**Colonnes**

| Colonne | Type | Null | Description | Flags |
|---|---|---|---|---|
| `{{col_1}}` | {{Type natif}} | {{N/Y}} | {{1 ligne}} | {{PK / FK / IDX / UNIQUE}} |
| `{{col_2}}` | {{}} | {{}} | {{}} | {{}} |

**Requêtes typiques**

```sql
-- Lecture principale
SELECT ... FROM {{TABLE_PIVOT}} WHERE ...;

-- Écriture
INSERT INTO {{TABLE_PIVOT}} (...) VALUES (...);
```

**Pièges connus**

- ⚠️ {{Comportement contre-intuitif — ex. soft-delete déguisé, padding, encodage}}
- ⚠️ {{Conversion implicite, NULL sémantique, valeur par défaut surprenante}}

**Évolutions notables**

| Date | PR | Changement |
|---|---|---|
| {{AAAA-MM-JJ}} | {{#PR}} | {{Ajout colonne / index / contrainte}} |

---

### 5.2 `{{TABLE_AUDIT_OU_HISTO}}` — {{rôle}}

> Bloc identique au précédent. À dupliquer pour chaque table importante.

---

### 5.3 `{{TABLE_REFERENTIEL}}` — {{rôle}} _(forme abrégée)_

- **Domaine :** {{}} · **Accédée par :** {{}} · **PK :** `{{col}}`
- **Colonnes :** `{{col_1}}` ({{type}}), `{{col_2}}` ({{type}}), …
- **Pattern :** {{Quasi-stable / lecture seule au runtime / chargée au boot}}

---

## 6. Synthèse catalogue

| Domaine | Table | Volume | PK | Évolutivité |
|---|---|---|---|---|
| {{Pivot}} | `{{}}` | {{}} | {{}} | {{Écriture fréquente}} |
| {{Catalogue}} | `{{}}` | {{}} | {{}} | {{Quasi-stable}} |
| {{Lien}} | `{{}}` | {{}} | {{}} | {{Historisé}} |
| {{Audit}} | `{{}}` | {{Append-only, illimité}} | {{}} | {{Write-only}} |

---

## 7. Matrice d'accès composant × table

> Lignes = composants/services. Colonnes = tables. Cellule vide = aucun accès = information utile.
> Légende : 👁 SELECT · 🔄 SELECT curseur / paginé · ✍ INSERT · ✏ UPDATE · 🗑 DELETE · 🔀 UPSERT.

| Composant | `{{T1}}` | `{{T2}}` | `{{T3}}` | `{{T4}}` |
|---|---|---|---|---|
| `{{COMPOSANT_A}}` | 👁 | — | ✍ | — |
| `{{COMPOSANT_B}}` | — | 👁 🔄 | — | — |
| `{{COMPOSANT_C}}` | ✏ | — | — | ✍ |

---

## 8. Objets non-table

| Type | Nom | Rôle | Localisation source |
|---|---|---|---|
| Vue | `{{nom}}` | {{}} | {{`db/views/...`}} |
| Séquence | `{{nom}}` | {{}} | {{}} |
| Trigger | `{{nom}}` | ⚠️ Logique cachée — décrire | {{}} |
| Fonction / Procédure | `{{nom}}` | {{}} | {{}} |
| Index spécial (partiel, GIN, expression) | `{{nom}}` | {{}} | {{}} |

> ⚠️ Les triggers et procédures stockées sont des **zones à risque** : la logique métier qu'ils portent doit aussi être documentée dans [fonctionnel.md](fonctionnel.md) ou [contracts.md](contracts.md).

---

## 9. Conventions transverses

### 9.1 Nommage

| Préfixe / suffixe | Sémantique | Exemple | Type canonique |
|---|---|---|---|
| `id_` | Identifiant technique | `id_user` | {{UUID / BIGINT / RAW}} |
| `ref_` | Référence métier alphanum | `ref_order` | {{VARCHAR}} |
| `cd_` | Code discret | `cd_status` | {{CHAR(n)}} |
| `dt_` | Date applicative | `dt_created` | {{TIMESTAMP / DATE}} |
| `is_` / `has_` | Booléen | `is_active` | {{BOOLEAN / CHAR(1)}} |
| `lib_` / `label_` | Libellé | `label_status` | {{VARCHAR}} |

### 9.2 Types et conversions critiques

> Documenter ICI tout type qui pose problème aux frontières (sérialisation, comparaison, hashing).

- **{{Type X}}** : {{Comportement à connaître — ex. Oracle CHAR padde avec espaces, PostgreSQL TIMESTAMP WITHOUT TIME ZONE pose problème pour les fuseaux, BLOB nécessite des conversions hex…}}

### 9.3 Dates et périodes de validité

- **Format applicatif** : {{ISO-8601 / Unix epoch / format propriétaire}}
- **Fuseau** : {{UTC / Europe/Paris / heure serveur}}
- **Convention de validité** : {{`dt_fin IS NULL` = infini / sentinelle date / colonne explicite}}
- **Filtre temporel canonique** :
  ```sql
  WHERE dt_deb <= :as_of
    AND (dt_fin IS NULL OR dt_fin >= :as_of)
  ```

### 9.4 NULL sémantique

| Colonne | NULL signifie | Impact |
|---|---|---|
| `{{col}}` | {{Inconnu / Pas applicable / Infini / Pas encore fixé}} | {{}} |

### 9.5 Capture d'erreur SQL / DB

- **Mécanisme** : {{Exception ORM / try-catch / handler global}}
- **Logs** : {{Format, niveau, anonymisation des paramètres}}
- **Localisation** : {{Couche DAO, intercepteur, middleware}}

---

## 10. Contraintes implicites

> Règles d'intégrité **non déclarées en base** mais **tenues par le code**. Toute évolution doit les préserver — voir [contracts.md](contracts.md) pour les composants qui les portent.

| # | Règle | Tenue par | Sanction si violée |
|---|---|---|---|
| IMP-01 | {{Ex. : `order.user_id` doit exister dans `user.id`}} | {{Validation service `OrderService.create`}} | {{Rejet en amont / corruption silencieuse}} |
| IMP-02 | {{}} | {{}} | {{}} |

---

## 11. Politique de rétention et purge

| Table | Rétention | Mécanisme | RGPD / sensible |
|---|---|---|---|
| `{{table}}` | {{Durée}} | {{Job, partition rolling, soft-delete}} | {{Données personnelles ?}} |

---

## 12. Migrations / évolutions

> Les migrations détaillées vivent dans `{{db/migrations/}}`. Cette section donne le cadre.

- **Outil** : {{Liquibase / Flyway / Alembic / Prisma / TypeORM…}}
- **Convention de nommage des fichiers** : {{`NNN_description.sql` / horodatage}}
- **Réversibilité** : {{Toutes les migrations sont reversibles / down-migration optionnelle}}
- **Stratégie pour les changements bloquants** : {{Expand-contract, double-write, fenêtre de maintenance}}

---

## 13. Recommandations actives

> Recommandations **non encore appliquées** — actions concrètes, pas des vœux pieux. Une fois traitées, les retirer (les conserver dans la PR qui les implémente).

1. **{{Action}}** — {{Justification, lien vers ticket}}
2. **{{Action}}** — {{}}

---

## Références

- Architecture : [architecture.md](architecture.md)
- Contrats des composants accédant aux données : [contracts.md](contracts.md)
- Glossaire : [glossaire.md](glossaire.md)
- Migrations versionnées : [{{db/migrations/}}]({{db/migrations/}})

---

<!--
MODE D'EMPLOI DU TEMPLATE
=========================

POUR L'IA QUI MET À JOUR CE FICHIER

Déclencheurs (mettre à jour les sections concernées si la PR touche…) :

| Modification dans la PR | Sections à relire |
|---|---|
| Nouvelle migration / DDL change | §1, §3, §4, §5 (table concernée), §6 |
| Ajout / suppression de table | §1, §2, §3, §4, §5, §6, §7 |
| Nouvelle FK ou index | §4, §5 (table concernée), §10 si elle remplace une contrainte implicite |
| Nouveau composant accédant à la base | §7 (matrice) |
| Nouveau trigger / procédure / vue | §8 |
| Changement de convention de nommage | §9.1 |
| Changement de mécanisme de date / fuseau | §9.3 |
| Politique de rétention modifiée | §11 |
| Outil de migration changé | §12 |

Pour chaque table modifiée, MAJ obligatoire :
- Le bloc colonnes (§5.x).
- La ligne dans §6 si la volumétrie change d'ordre de grandeur.
- La ligne dans la matrice §7 si l'accès change.
- Ajouter une ligne « Évolutions notables » dans le bloc table avec date + PR.

Auto-checks :
- [ ] Toutes les tables citées en §5 existent dans le DDL / l'ORM.
- [ ] Toutes les FK §4 marquées « déclarée » correspondent à une vraie FK SQL.
- [ ] Le diagramme §3 reflète les relations §4.
- [ ] La matrice §7 ne mentionne pas de composant supprimé.
- [ ] Aucune `(à confirmer)` ancienne de plus de 60 jours sans ticket associé.

POUR LE RELECTEUR HUMAIN

- Vérifier que les volumétries ont une source datée (sinon : « ordre approximatif »).
- Les pièges §5.x doivent être réalistes — pas de sur-anticipation.
- Si l'IA invente un IMP-XX, vérifier que c'est bien tenu par le code et pas une
  hypothèse de relecture.

POUR ADAPTER À UN AUTRE PROJET

1. Remplacer placeholders.
2. Si stockage non relationnel (DynamoDB, MongoDB, Cassandra) :
   - §3 (ER) → schéma de documents / partitions clés.
   - §4 (relations) → références dénormalisées + GSI / SI.
   - §5 → catalogue de collections / item types ; les « colonnes » deviennent attributs.
3. Si plusieurs bases : dupliquer §5 par base, garder une vue d'ensemble §1 unique.
4. Garder les sections vides plutôt que les supprimer — l'absence est une information
   (« pas de trigger », « pas de pattern temporel »).
-->
