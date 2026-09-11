# INIS — Spécification d'implémentation exécutable v0.2.0

> **Document de codage normatif.**
> Ce document transforme `INIS_MASTER_SPEC.md v0.1.0` en spécification directement implémentable.
> En cas de conflit avec la v0.1.0, **ce document prévaut pour la V1**.
> Les termes **DOIT**, **NE DOIT PAS**, **DEVRAIT**, **PEUT** sont à interpréter selon RFC 2119.
> Les choix marqués `[V1-FIXE]` sont figés pour la première implémentation.
> Les choix marqués `[CONFIG]` doivent être configurables et ne jamais être codés en dur.

---

## 0. Décisions fondatrices — précisions normatives

### 0.1 Mission

INIS est un agent et un service informationnel pair-à-pair. Il mobilise, vérifie, trace, structure et transporte l'information. Il ne produit pas de synthèse métier par défaut.

### 0.2 Invariants vérifiables

Tout code produit pour INIS DOIT garantir ces invariants :

**1. Aucun fait sans provenance.**
Toute `InformationUnit`, `Evidence`, `Claim`, `Dataset`, `Artifact` ou `Finding` factuel DOIT référencer au moins :
- `source_id`, ou
- `document_id`, ou
- `dataset_id`, ou
- `transformation_id`, ou
- une combinaison de ces éléments.

**2. Aucune sortie factuelle non traçable.**
Si une affirmation ne peut pas être reliée à une preuve, elle DOIT être marquée :

```json
{
  "epistemic_status": "hypothesis | assumption | intention | uncertainty"
}
```

et NE DOIT PAS être placée dans `findings` comme fait.

**3. Séparation RAW / NORMALIZED / ENRICHED / DERIVED.**
Chaque donnée DOIT avoir un `data_stage` parmi :

```text
raw | normalized | enriched | derived
```

**4. Versionnement obligatoire.**
Toute modification significative crée une nouvelle version. L'ancienne version reste récupérable.

**5. Suppression logique.**
Aucune suppression physique directe. Statuts autorisés :

```text
active | archived | deleted | superseded
```

**6. Audit obligatoire.**
Toute opération importante écrit un `audit_event`.

**7. Confiance explicable.**
Le score de confiance DOIT exposer ses dimensions et les règles de calcul.

**8. LLM non source de vérité.**
Le LLM ne peut jamais être la source unique d'un fait.

### 0.3 Identifiants `[V1-FIXE]`

Tous les identifiants métier utilisent le format suivant :

```text
REQ_{ULID}          request_id
MSG_{ULID}          message_id
CORR_{ULID}         correlation_id
INF_{ULID}          information_id
SRC_{ULID}          source_id
DOC_{ULID}          document_id
DATA_{ULID}         dataset_id
EVID_{ULID}         evidence_id
CLM_{ULID}          claim_id
CONFLICT_{ULID}     conflict_id
TRF_{ULID}          transformation_id
AUD_{ULID}          audit_event_id
ART_{YYYY}_{SEQ6}   artifact_id
```

- `ULID` : 26 caractères Crockford, triable temporellement.
- `trace_id` : 32 caractères hexadécimaux minuscules.
- `span_id` : 16 caractères hexadécimaux minuscules.
- Horodatages : ISO 8601 UTC avec `Z`, précision microseconde. En base : `timestamptz`.

---

## 1. Périmètre fonctionnel — V1 exacte

### 1.1 INIS V1 DOIT faire

- Recevoir des demandes JSON via HTTP et AMQP.
- S'enregistrer et découvrir des agents via un registre.
- Construire un plan.
- Rechercher sur le Web via au moins deux fournisseurs interchangeables.
- Lire des pages Web.
- Appeler des APIs REST.
- Interroger PostgreSQL.
- Ingérer CSV, Excel, JSON, XML.
- Ingérer PDF et documents bureautiques.
- Analyser des images simples.
- Détecter PII et sensibilité.
- Contrôler qualité, doublons, fraîcheur, cohérence.
- Détecter contradictions.
- Calculer un score de confiance explicable.
- Stocker sources, documents, datasets, informations, preuves, transformations, artefacts.
- Rechercher en vectoriel et hybride via PostgreSQL + pgvector.
- Réutiliser la mémoire si pertinente et fraîche.
- Déléguer à un autre agent si compétence absente.
- Produire des réponses JSON structurées.
- Produire des artefacts `.xlsx`, `.csv`, `.json`, `.xml`, `.pdf`.
- Journaliser et auditer.

### 1.2 INIS V1 NE DOIT PAS faire

- Inventer une valeur manquante.
- Transformer une hypothèse en fait.
- Modifier silencieusement le sens d'une source.
- Faire une analyse métier spécialisée.
- Produire une synthèse éditoriale.
- Exécuter du code arbitraire.
- Supprimer physiquement sans archivage.
- Exposer une donnée sans contrôle de politique.

### 1.3 États de sortie autorisés

```text
SUCCESS
PARTIAL_SUCCESS
INSUFFICIENT_EVIDENCE
CONFLICTING_SOURCES
SOURCE_UNAVAILABLE
SOURCE_STALE
ACCESS_DENIED
DATA_INVALID
TOOL_FAILURE
AGENT_UNAVAILABLE
TIMEOUT
BUDGET_EXCEEDED
CANCELLED
```

---

## 2. Positionnement multi-agents

### 2.1 Modèle

INIS est un pair. Il expose :
- une API HTTP ;
- des files AMQP ;
- optionnellement MQTT.

Il n'est pas un hub obligatoire. Il est un carrefour informationnel spécialisé.

```text
INIS = agent autonome + service informationnel interopérable
```

### 2.2 Flux entrant

```text
Agent demandeur
  -> message INIS
  -> authentification
  -> autorisation
  -> compréhension
  -> plan
  -> exécution
  -> vérification
  -> packaging
  -> livraison
  -> audit
```

### 2.3 Flux sortant

```text
INIS
  -> discover_agents()
  -> query_agent_capabilities()
  -> send_agent_request()
  -> receive_agent_result()
  -> vérification
  -> rattachement au contexte
  -> livraison au demandeur initial
```

---

## 3. Architecture logique — composants obligatoires

```text
inis/
├── app/
│   ├── api/                 # FastAPI, routes, dependencies
│   ├── core/                # config, logging, erreurs, modèles de base
│   ├── domain/              # entités, value objects, enums
│   ├── agents/              # runtime agent, compréhension, planification
│   ├── planning/            # plans, étapes, itérations, budgets
│   ├── tools/               # outils internes
│   ├── connectors/          # connecteurs de sources
│   ├── knowledge/           # information units, evidence, pgvector
│   ├── provenance/          # lineage, transformations, versions
│   ├── quality/             # contrôles qualité
│   ├── confidence/          # scoring, matrice
│   ├── governance/          # politiques, permissions, audit
│   ├── messaging/           # AMQP, MQTT, protocole
│   ├── registry/            # agent registry
│   ├── storage/             # PostgreSQL, S3/MinIO, Redis
│   ├── observability/       # OpenTelemetry, métriques
│   └── security/            # authn, authz, PII
├── migrations/              # Alembic
├── tests/
├── frontend/
├── docker/
├── configs/
├── scripts/
├── docs/
└── pyproject.toml
```

---

## 4. Stack technique cible — versions figées V1

### 4.1 Runtime `[V1-FIXE]`

```text
Python 3.12
FastAPI 0.115+
Pydantic 2.9+
SQLAlchemy 2.0 async
Alembic
asyncpg
pgvector-python
aio-pika
paho-mqtt ou gmqtt
Redis 7
MinIO / S3
OpenTelemetry
structlog
httpx
trafilatura
readability-lxml
pypdf
pdfplumber
python-docx
openpyxl
xlsxwriter
polars
Pillow
litellm
pytest
pytest-asyncio
testcontainers
```

### 4.2 PostgreSQL `[V1-FIXE]`

- PostgreSQL 16+
- Extension `vector`
- JSONB
- `tsvector` pour full-text
- Index GIN sur JSONB
- Index IVFFlat ou HNSW pgvector

### 4.3 Object storage

- Local : MinIO
- Cloud : S3 compatible
- PostgreSQL ne stocke jamais le binaire volumineux.
- PostgreSQL stocke `storage_ref`, `sha256`, `size_bytes`.

### 4.4 Broker de messages

- AMQP : RabbitMQ pour requêtes, résultats, tâches fiables.
- MQTT : optionnel pour événements légers, heartbeat, télémétrie.

Interface interne obligatoire :

```python
class MessageBroker(Protocol):
    async def publish(self, routing_key: str, message: Envelope) -> None: ...
    async def subscribe(self, queue: str, handler: Callable[[Envelope], Awaitable[None]]) -> None: ...
```

---

## 5. Protocoles inter-agents — schémas

### 5.1 Envelope commune

Chaque message échangé entre agents DOIT respecter la structure suivante :

```json
{
  "protocol_version": "1.0",
  "message_id": "<MSG_{ULID}>",
  "correlation_id": "<CORR_{ULID}>",
  "causation_id": "<MSG_{ULID} parent | null>",
  "timestamp": "<ISO 8601 UTC>",
  "sender": {
    "agent_id": "<identifiant de l'agent émetteur>",
    "agent_instance_id": "<ULID de l'instance | null>",
    "agent_version": "<semver>"
  },
  "recipient": {
    "agent_id": "<identifiant de l'agent destinataire>",
    "agent_instance_id": "<ULID de l'instance cible | null>"
  },
  "message_type": "<type parmi la liste V1>",
  "priority": "low | normal | high | critical",
  "reply_to": "<queue de retour | null>",
  "ttl_seconds": "<entier positif>",
  "payload": {},
  "security": {
    "auth_method": "mtls | jwt | api_key",
    "token_id": "<identifiant du token | null>",
    "scopes": ["<scope1>", "<scope2>"]
  },
  "trace": {
    "trace_id": "<32 hex>",
    "span_id": "<16 hex>",
    "correlation_id": "<CORR_{ULID}>",
    "causation_id": "<MSG_{ULID} | null>"
  }
}
```

### 5.2 Types de messages V1

```text
AGENT_REGISTER
AGENT_UPDATE
AGENT_HEARTBEAT
CAPABILITY_QUERY
INFORMATION_REQUEST
INFORMATION_RESPONSE
SOURCE_REQUEST
EVIDENCE_REQUEST
DATA_REQUEST
RESEARCH_REQUEST
RESEARCH_PROGRESS
RESEARCH_COMPLETED
AGENT_DELEGATION_REQUEST
AGENT_DELEGATION_RESPONSE
CLARIFICATION_REQUEST
CONFLICT_REPORT
LOW_CONFIDENCE_REPORT
ACCESS_DENIED
VALIDATION_ERROR
EXECUTION_ERROR
CANCEL_REQUEST
CANCELLED
AUDIT_EVENT
```

### 5.3 Idempotence

- `message_id` est unique.
- Table `agent_messages` avec contrainte unique sur `message_id`.
- Si un message déjà traité arrive, INIS renvoie la réponse précédente si disponible, sinon ignore.

---

## 6. Agent Registry — modèle

### 6.1 Table `agents`

```sql
CREATE TABLE agents (
  agent_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('available','degraded','unavailable','maintenance')),
  protocols JSONB NOT NULL DEFAULT '[]',
  message_types JSONB NOT NULL DEFAULT '[]',
  capabilities JSONB NOT NULL DEFAULT '[]',
  input_schemas JSONB NOT NULL DEFAULT '[]',
  output_schemas JSONB NOT NULL DEFAULT '[]',
  security_requirements JSONB NOT NULL DEFAULT '[]',
  health JSONB NOT NULL DEFAULT '{}',
  performance_profile JSONB NOT NULL DEFAULT '{}',
  learning_profile JSONB NOT NULL DEFAULT '{}',
  registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2 Structure de la carte d'identité d'un agent

```json
{
  "agent_id": "<identifiant unique de l'agent>",
  "name": "<nom lisible de l'agent>",
  "description": "<description fonctionnelle>",
  "version": "<semver>",
  "status": "available | degraded | unavailable | maintenance",
  "capabilities": ["<capacité_1>", "<capacité_2>"],
  "protocols": ["amqp | http | mqtt"],
  "message_types": ["<type_1>", "<type_2>"],
  "input_schemas": [],
  "output_schemas": [],
  "security_requirements": [],
  "health": {
    "last_heartbeat": "<ISO 8601 UTC>",
    "latency_ms_p95": "<entier>"
  },
  "performance_profile": {
    "success_rate": "<float 0-1>",
    "avg_latency_ms": "<entier>"
  },
  "learning_profile": {
    "observed_tasks": "<entier>",
    "avg_quality": "<float 0-1>",
    "error_rate": "<float 0-1>"
  },
  "registered_at": "<ISO 8601 UTC>",
  "last_seen_at": "<ISO 8601 UTC>"
}
```

### 6.3 Heartbeat

- Fréquence par défaut : 30 s `[CONFIG]`.
- TTL : 90 s `[CONFIG]`.
- Si `last_seen_at < now - ttl`, statut passe à `unavailable`.

---

## 7. Modèle de demande — schéma Pydantic

```python
class RequestConstraints(BaseModel):
    date_range: DateRange | None = None
    source_preferences: list[str] = []
    minimum_confidence: float = Field(0.8, ge=0.0, le=1.0)
    maximum_cost: float | None = None
    maximum_execution_time_seconds: int = 300
    maximum_iterations: int = 12
    maximum_web_depth: int = 3

class RequiredOutput(BaseModel):
    format: Literal[
        "evidence_package",
        "json",
        "csv",
        "xlsx",
        "pdf",
        "xml"
    ] = "evidence_package"
    fields: list[str] = []

class InformationRequest(BaseModel):
    request_id: str
    request_type: Literal["research", "source", "evidence", "data", "artifact"]
    objective: str
    question: str | None = None
    context: dict = {}
    required_information: list[str] = []
    constraints: RequestConstraints = RequestConstraints()
    required_output: RequiredOutput = RequiredOutput()
    requester: dict
    permissions: dict = {}
```

---

## 8. Planification autonome — algorithme et états

### 8.1 États de traitement

```text
RECEIVED
AUTHENTICATED
AUTHORIZED
UNDERSTANDING
REQUIREMENTS_EXTRACTED
MEMORY_CHECKED
PLANNED
EXECUTING
QUALITY_CONTROL
VERIFYING
PACKAGING
PERMISSION_CHECK
DELIVERING
DELIVERED
FAILED
CANCELLED
```

### 8.2 Structure d'un plan

```json
{
  "plan_id": "<PLAN_{ULID}>",
  "request_id": "<REQ_{ULID}>",
  "objective": "<objectif de la demande>",
  "steps": [
    {
      "step_id": "<STEP_{ULID}>",
      "order": "<entier, ordre d'exécution>",
      "action": "<nom de l'action>",
      "tool": "<identifiant de l'outil>",
      "inputs": {},
      "expected_output": "<type de sortie attendu>",
      "status": "pending | running | done | failed",
      "depends_on": ["<step_id>"]
    }
  ],
  "budget": {
    "max_iterations": "<entier>",
    "max_cost": "<float | null>",
    "max_execution_time_seconds": "<entier>"
  },
  "created_at": "<ISO 8601 UTC>"
}
```

### 8.3 Structure d'une itération

```json
{
  "iteration_id": "<ITER_{ULID}>",
  "request_id": "<REQ_{ULID}>",
  "iteration_number": "<entier>",
  "objective": "<objectif de cette itération>",
  "hypothesis": "<hypothèse de travail>",
  "actions": [],
  "tools_used": [],
  "inputs": [],
  "outputs": [],
  "new_evidence": [],
  "decision": "continue | stop | delegate | fail",
  "termination_reason": "<raison si arrêt | null>"
}
```

### 8.4 Algorithme de planification

```python
async def build_plan(request: InformationRequest) -> Plan:
    requirements = extract_requirements(request)
    memory_hit = await memory_check(requirements)
    if memory_hit.sufficient and memory_hit.fresh:
        return Plan.simple_memory_response(memory_hit)
    sources = await discover_sources(requirements)
    tools = select_tools(requirements, sources)
    steps = []
    for req in requirements:
        if req.type == "web":
            steps.append(web_search_step(req))
        elif req.type == "api":
            steps.append(api_step(req))
        elif req.type == "database":
            steps.append(postgres_step(req))
        elif req.type == "file":
            steps.append(file_ingest_step(req))
    steps.append(quality_step())
    steps.append(verification_step())
    steps.append(packaging_step())
    return Plan(objective=request.objective, steps=steps, budget=request.constraints)
```

### 8.5 Critères d'arrêt

L'exécution s'arrête dès qu'une des conditions suivantes est vraie :

```text
requirements_satisfied == True
confidence_score >= minimum_confidence
budget_exhausted == True
no_new_relevant_source == True
information_unavailable == True
policy_forbids_continue == True
```

---

## 9. Connecteurs de sources — interface obligatoire

```python
class SourceConnector(Protocol):
    connector_id: str
    supported_source_types: list[str]

    async def discover(self, query: Query) -> list[SourceCandidate]: ...
    async def retrieve(self, candidate: SourceCandidate) -> RawSource: ...
    async def inspect(self, raw: RawSource) -> SourceMetadata: ...
    async def health_check(self) -> HealthStatus: ...
    async def metadata(self) -> ConnectorMetadata: ...
```

### 9.1 Connecteurs V1 obligatoires

| Connecteur | Bibliothèque V1 |
|---|---|
| Web search | httpx + provider adapters |
| Pages Web | httpx + trafilatura |
| API REST | httpx |
| PostgreSQL | asyncpg + SQLAlchemy |
| CSV | polars |
| Excel | polars + openpyxl |
| JSON | orjson |
| XML | lxml |
| PDF | pypdf + pdfplumber |
| Documents bureautiques | python-docx |
| Images | Pillow |

### 9.2 Connecteurs exclus V1

OCR avancé, audio, vidéo, streaming temps réel. Ils DOIVENT être prévus comme plugins.

---

## 10. Recherche Web — abstraction et politique

### 10.1 Interface

```python
class SearchProvider(Protocol):
    provider_id: str

    async def search(self, query: str, limit: int) -> list[SearchResult]: ...
```

### 10.2 Hiérarchie des sources par fiabilité `[CONFIG]`

```text
1. sources officielles
2. institutions publiques
3. articles scientifiques
4. organismes internationaux
5. entreprises
6. médias
7. forums / réseaux sociaux
```

Chaque source reçoit un `source_reliability_score` entre 0 et 1.

### 10.3 Navigation

- Profondeur max : `constraints.maximum_web_depth`.
- INIS ne suit un lien que si le plan l'exige.
- Chaque page visitée crée un `Document` et des `InformationUnit`.

---

## 11. Information Unit — schéma complet

```python
class InformationUnit(BaseModel):
    information_id: str
    type: Literal["text", "number", "table", "record", "image_region", "document_fragment"]
    content: dict
    raw_reference: dict
    source_id: str
    document_id: str | None
    dataset_id: str | None
    location: dict
    context: dict
    language: str | None
    unit: str | None
    time: dict
    classification: dict
    quality: dict
    confidence: dict
    provenance: dict
    versions: list[str]
    created_at: datetime
    updated_at: datetime
```

### 11.1 Règle de conservation

Lors de l'extraction, conserver en priorité :

```text
original
+ contexte immédiat
+ métadonnées
+ position dans la source
+ relations avec d'autres unités
+ provenance complète
```

Toute réduction DOIT être justifiée par un `transformation_id`.

---

## 12. Cycle de vie des données : RAW → NORMALIZED → ENRICHED → DERIVED

```text
RAW -> NORMALIZED -> ENRICHED -> DERIVED
```

### 12.1 Structure d'une transformation

```json
{
  "transformation_id": "<TRF_{ULID}>",
  "input_ids": ["<information_id | dataset_id>"],
  "output_ids": ["<information_id | dataset_id>"],
  "operator": "<nom de l'opération>",
  "tool": "<module.fonction>",
  "tool_version": "<semver>",
  "parameters": {},
  "timestamp": "<ISO 8601 UTC>",
  "result": "success | failure",
  "justification": "<description de la raison de la transformation>"
}
```

---

## 13. Qualité des données — contrôles et score

### 13.1 Interface de contrôle

```python
class QualityCheck(Protocol):
    async def run(self, target: InformationUnit | Dataset | Document) -> QualityResult: ...
```

### 13.2 Contrôles V1 obligatoires

- complétude
- validité
- cohérence
- unicité
- conformité aux types
- doublons
- anomalies
- fraîcheur
- provenance
- cohérence temporelle
- cohérence inter-sources

### 13.3 Formule du score qualité

```text
quality_score = weighted_mean(
  completeness,
  validity,
  consistency,
  uniqueness,
  type_conformity,
  freshness,
  provenance_completeness
)
```

Poids par défaut `[CONFIG]` :

```json
{
  "completeness": 0.15,
  "validity": 0.15,
  "consistency": 0.15,
  "uniqueness": 0.10,
  "type_conformity": 0.10,
  "freshness": 0.15,
  "provenance_completeness": 0.20
}
```

---

## 14. Preuves et contradictions

### 14.1 Structure d'un Claim

```json
{
  "claim_id": "<CLM_{ULID}>",
  "statement": "<affirmation factuelle>",
  "information_ids": ["<INF_{ULID}>"],
  "evidence_ids": ["<EVID_{ULID}>"],
  "confidence": "<float 0-1>",
  "epistemic_status": "fact | hypothesis | assumption | uncertainty"
}
```

### 14.2 Structure d'une Evidence

```json
{
  "evidence_id": "<EVID_{ULID}>",
  "claim_id": "<CLM_{ULID}>",
  "information_id": "<INF_{ULID}>",
  "document_id": "<DOC_{ULID}>",
  "source_id": "<SRC_{ULID}>",
  "excerpt": "<extrait de la source>",
  "location": {},
  "strength": "<float 0-1>"
}
```

### 14.3 Structure d'un Conflict

```json
{
  "conflict_id": "<CONFLICT_{ULID}>",
  "information_a": "<INF_{ULID}>",
  "information_b": "<INF_{ULID}>",
  "difference_type": "value | definition | date | methodology | scope",
  "severity": "low | medium | high",
  "resolution_status": "open | investigated | unresolved | resolved",
  "resolution_evidence": []
}
```

### 14.4 Algorithme de détection de contradictions

```python
async def detect_conflicts(units: list[InformationUnit]) -> list[Conflict]:
    conflicts = []
    grouped = group_by_subject_and_predicate(units)
    for group in grouped:
        for a, b in combinations(group, 2):
            if values_differ(a, b):
                conflicts.append(Conflict(
                    information_a=a.information_id,
                    information_b=b.information_id,
                    difference_type=classify_difference(a, b),
                    severity=assess_severity(a, b),
                    resolution_status="open"
                ))
    return conflicts
```

---

## 15. Modèle de confiance

### 15.1 Dimensions

```text
source_reliability
source_freshness
extraction_confidence
data_quality
evidence_strength
cross_source_agreement
methodological_consistency
```

### 15.2 Formule `[CONFIG]`

```text
confidence_score =
    0.20 * source_reliability +
    0.10 * source_freshness +
    0.15 * extraction_confidence +
    0.15 * data_quality +
    0.15 * evidence_strength +
    0.15 * cross_source_agreement +
    0.10 * methodological_consistency
```

### 15.3 Structure de la sortie explicable

```json
{
  "confidence_score": "<float 0-1>",
  "dimensions": {
    "source_reliability": "<float 0-1>",
    "source_freshness": "<float 0-1>",
    "extraction_confidence": "<float 0-1>",
    "data_quality": "<float 0-1>",
    "evidence_strength": "<float 0-1>",
    "cross_source_agreement": "<float 0-1>",
    "methodological_consistency": "<float 0-1>"
  },
  "explanation": "<description des règles de calcul appliquées>",
  "not_a_probability": true
}
```

---

## 16. Recherche vectorielle — PostgreSQL + pgvector

### 16.1 Table `embeddings`

```sql
CREATE TABLE embeddings (
  embedding_id UUID PRIMARY KEY,
  owner_type TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  model TEXT NOT NULL,
  vector vector(1536) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX embeddings_vector_idx ON embeddings
USING hnsw (vector vector_cosine_ops);
```

### 16.2 Recherche hybride

```sql
WITH semantic AS (
  SELECT owner_id, 1 - (vector <=> :query_vector) AS score
  FROM embeddings
  WHERE owner_type = :owner_type
  ORDER BY vector <=> :query_vector
  LIMIT :limit
),
lexical AS (
  SELECT information_id AS owner_id,
         ts_rank(search_vector, plainto_tsquery(:query)) AS score
  FROM information_units
  WHERE search_vector @@ plainto_tsquery(:query)
  LIMIT :limit
)
SELECT owner_id,
       COALESCE(semantic.score, 0) * 0.6 +
       COALESCE(lexical.score, 0) * 0.4 AS final_score
FROM semantic
FULL OUTER JOIN lexical USING (owner_id)
ORDER BY final_score DESC;
```

---

## 17. Mémoire

### 17.1 Algorithme de réutilisation

```python
async def memory_lookup(question: str, requirements: Requirements) -> MemoryResult:
    candidates = await hybrid_search(question, filters=requirements.filters)
    for candidate in candidates:
        if not candidate.provenance_complete:
            continue
        if not freshness_acceptable(candidate, requirements):
            continue
        if not policy_allows_reuse(candidate):
            continue
        return MemoryResult(sufficient=True, items=[candidate])
    return MemoryResult(sufficient=False)
```

---

## 18. Gouvernance de la donnée

### 18.1 Versioning

Chaque version d'un enregistrement DOIT conserver :

```text
version_id
parent_version_id
created_at
created_by
change_reason
before_hash
after_hash
```

### 18.2 Cycle de vie (suppression logique)

```text
ACTIVE -> ARCHIVED -> DELETED
```

Aucune suppression physique. `deleted_at` DOIT être renseigné.

### 18.3 Champs de temporalité obligatoires

```text
published_at
collected_at
updated_at
valid_from
valid_until
```

---

## 19. Sécurité

### 19.1 Pipeline de traitement d'une requête

```text
Agent requester
  -> Authentication
  -> Authorization
  -> Policy evaluation
  -> Data access
  -> Redaction / delivery
```

### 19.2 Authentification `[V1-FIXE]`

- mTLS pour inter-agents.
- JWT pour API HTTP.
- API keys pour administration.

### 19.3 Autorisation

RBAC + ABAC.

Structure d'une politique d'accès :

```json
{
  "policy_id": "<POL_{ULID}>",
  "subject": {
    "agent_id": "<identifiant de l'agent>"
  },
  "resource": {
    "type": "information | source | dataset | document",
    "classification": "public | internal | confidential | restricted"
  },
  "action": "read | write | update | delete | transmit | search",
  "effect": "allow | deny",
  "conditions": {}
}
```

### 19.4 Classification PII

```json
{
  "sensitivity": "low | medium | high | critical",
  "pii": true,
  "categories": ["<catégorie_1>", "<catégorie_2>"]
}
```

---

## 20. Audit et observabilité

### 20.1 Structure d'un audit event

```json
{
  "audit_event_id": "<AUD_{ULID}>",
  "timestamp": "<ISO 8601 UTC>",
  "actor_type": "agent | user | system",
  "actor_id": "<identifiant de l'acteur>",
  "action": "read | write | update | delete | transmit | search",
  "resource_type": "information | source | dataset | document",
  "resource_id": "<identifiant de la ressource>",
  "request_id": "<REQ_{ULID}>",
  "result": "success | denied | failed",
  "reason": "<description du résultat>",
  "before_hash": "<sha256 avant modification>",
  "after_hash": "<sha256 après modification>"
}
```

### 20.2 Trace distribuée

Chaque requête DOIT porter :

```text
trace_id
span_id
correlation_id
causation_id
```

OpenTelemetry obligatoire.

---

## 21. Outils internes — signatures

```python
async def web_search(query: str, limit: int) -> list[SearchResult]: ...
async def open_url(url: str) -> Document: ...
async def follow_link(url: str) -> Document: ...
async def postgres_query(sql: str, params: dict) -> list[dict]: ...
async def read_csv(path: str) -> Dataset: ...
async def read_excel(path: str) -> Dataset: ...
async def read_json(path: str) -> Dataset: ...
async def read_xml(path: str) -> Dataset: ...
async def inspect_schema(dataset: Dataset) -> Schema: ...
async def profile_dataset(dataset: Dataset) -> Profile: ...
async def read_pdf(path: str) -> Document: ...
async def extract_document(path: str) -> Document: ...
async def extract_image_content(path: str) -> list[InformationUnit]: ...
async def locate_fragment(document_id: str, query: str) -> list[InformationUnit]: ...
async def detect_duplicates(dataset: Dataset) -> list[Duplicate]: ...
async def validate_schema(dataset: Dataset, schema: Schema) -> ValidationResult: ...
async def check_missing_values(dataset: Dataset) -> QualityResult: ...
async def check_consistency(dataset: Dataset) -> QualityResult: ...
async def check_freshness(source: Source) -> QualityResult: ...
async def compare_sources(sources: list[Source]) -> list[Conflict]: ...
async def store_source(source: Source) -> str: ...
async def store_information(unit: InformationUnit) -> str: ...
async def store_evidence(evidence: Evidence) -> str: ...
async def vector_search(query_vector: list[float], limit: int) -> list[InformationUnit]: ...
async def hybrid_search(query: str, filters: dict) -> list[InformationUnit]: ...
async def retrieve_context(ids: list[str]) -> list[InformationUnit]: ...
async def discover_agents(capability: str) -> list[AgentIdentity]: ...
async def query_agent_capabilities(agent_id: str) -> list[str]: ...
async def send_agent_request(agent_id: str, request: Envelope) -> Envelope: ...
async def receive_agent_result(correlation_id: str) -> Envelope: ...
async def check_permission(agent_id: str, resource: str, action: str) -> bool: ...
async def classify_sensitivity(data: dict) -> Classification: ...
async def create_version(resource_id: str, change: dict) -> str: ...
async def archive_record(resource_id: str) -> None: ...
async def write_audit_event(event: AuditEvent) -> None: ...
```

---

## 22. LLM et Model Router

### 22.1 Interface

```python
class ModelRouter(Protocol):
    async def complete(self, task: LLMTask, prompt: str, **kwargs) -> LLMResponse: ...
```

### 22.2 Critères de sélection du modèle

Le routeur choisit selon :

- nature de la tâche
- coût
- latence
- taille de contexte requise
- capacité de raisonnement
- multimodalité
- disponibilité

### 22.3 Règle absolue

Le LLM ne DOIT JAMAIS être la source unique d'un fait.

Le LLM sert à :

- comprendre la demande
- planifier les étapes
- choisir les outils
- interpréter les résultats
- classer les informations
- comparer des éléments
- proposer des hypothèses
- aider à détecter des contradictions
- évaluer des signaux de confiance

---

## 23. Exécution sécurisée

V1 : pas d'exécution de code arbitraire.

Si ajoutée dans une version ultérieure, les conditions obligatoires sont :

- sandbox obligatoire
- limites CPU / mémoire / temps
- réseau contrôlé
- filesystem isolé
- whitelist de bibliothèques
- journalisation complète

---

## 24. Contrat de livraison

### 24.1 Structure de la réponse standard

```json
{
  "response_id": "<RESP_{ULID}>",
  "request_id": "<REQ_{ULID}>",
  "status": "<état de sortie autorisé>",
  "summary": null,
  "findings": [],
  "information_units": [],
  "evidence": [],
  "sources": [],
  "datasets": [],
  "artifacts": [],
  "transformations": [],
  "conflicts": [],
  "confidence": {},
  "limitations": [],
  "assumptions": [],
  "missing_information": [],
  "recommended_next_actions": [],
  "provenance": {},
  "audit": {},
  "generated_by": {},
  "timestamps": {},
  "trace": {}
}
```

### 24.2 Structure d'un artefact

```json
{
  "artifact_id": "<ART_{YYYY}_{SEQ6}>",
  "artifact_type": "<dataset_export | report | document | other>",
  "file_name": "<nom_du_fichier.extension>",
  "mime_type": "<type MIME>",
  "version": "<semver>",
  "size_bytes": "<entier>",
  "sha256": "<hash du fichier>",
  "storage_ref": "<s3://bucket/chemin>",
  "purpose": "<description de l'usage attendu>",
  "source_ids": ["<SRC_{ULID}>"],
  "dataset_ids": ["<DATA_{ULID}>"],
  "transformation_ids": [],
  "quality_score": "<float 0-1>",
  "confidence_score": "<float 0-1>",
  "provenance_complete": true,
  "status": "available | archived | deleted"
}
```

### 24.3 Export Excel

INIS PEUT générer un `.xlsx` si demandé explicitement. Le classeur PEUT contenir :

- données demandées
- métadonnées
- dictionnaire de données
- sources
- provenance
- contrôles qualité
- version

INIS NE DOIT PAS inventer de valeurs.

---

## 25. Gestion de l'incertitude et des échecs

### 25.1 Stratégie d'escalade

```text
Erreur
  -> Classifier
  -> Retry si pertinent
  -> Alternative source / outil
  -> Délégation à un autre agent
  -> Résultat partiel
  -> Échec transparent avec raison explicite
```

### 25.2 Correspondance erreurs / états

| Erreur | État |
|---|---|
| Source inaccessible | SOURCE_UNAVAILABLE |
| Source trop ancienne | SOURCE_STALE |
| Permission refusée | ACCESS_DENIED |
| Donnée invalide | DATA_INVALID |
| Outil en échec | TOOL_FAILURE |
| Agent indisponible | AGENT_UNAVAILABLE |
| Timeout | TIMEOUT |
| Budget dépassé | BUDGET_EXCEEDED |
| Annulé | CANCELLED |

---

## 26. Architecture des services — détail

```text
app/api/           -> FastAPI routers
app/core/          -> config, logging, errors, constants
app/domain/        -> modèles métier, enums, value objects
app/agents/        -> runtime, compréhension, décision
app/planning/      -> plan builder, executor, iterations
app/tools/         -> implémentations outils
app/connectors/    -> web, api, postgres, csv, excel, json, xml, pdf, docx, image
app/knowledge/     -> information units, evidence, pgvector
app/provenance/    -> lineage, transformations, versions
app/quality/       -> checks, scores
app/confidence/    -> scoring, explainability
app/governance/    -> policies, permissions, audit
app/messaging/     -> amqp, mqtt, protocol
app/registry/      -> agent registry
app/storage/       -> postgres, s3, redis
app/observability/ -> otel, metrics, logs
app/security/      -> authn, authz, pii
```

---

## 27. Modèle conceptuel de données — tables obligatoires

```text
agents
agent_capabilities
agent_health
agent_learning_profiles
requests
plans
plan_steps
executions
iterations
sources
source_versions
documents
datasets
information_units
information_versions
evidence
claims
conflicts
transformations
embeddings
agent_messages
audit_events
access_policies
security_classifications
artifacts
artifact_versions
artifact_lineage
artifact_delivery_events
```

### 27.1 Relations entre entités

```text
Request
 ├── Plan
 │    └── PlanStep
 │          └── Execution
 │                 └── Iteration
 ├── Sources
 │     └── Information Units
 │            └── Evidence
 ├── Agent Messages
 └── Audit Events
```

---

## 28. Cycle complet d'une demande

```text
1.  RECEIVING
2.  AUTHENTICATION
3.  AUTHORIZATION
4.  UNDERSTANDING
5.  REQUIREMENT EXTRACTION
6.  MEMORY CHECK
7.  PLAN GENERATION
8.  TOOL / SOURCE DISCOVERY
9.  DATA ACQUISITION
10. EXTRACTION
11. NORMALIZATION
12. QUALITY CONTROL
13. SOURCE CROSS-CHECK
14. CONFIDENCE ASSESSMENT
15. CONTRADICTION HANDLING
16. OPTIONAL AGENT DELEGATION
17. TARGETED EXTRACTION / STRUCTURING
18. RESULT PACKAGING
19. PERMISSION CHECK
20. DELIVERY
21. AUDIT
22. LEARNING / TELEMETRY
```

Toutes les étapes ne sont pas obligatoires. Le plan choisit lesquelles activer.

---

## 29. Communication inter-agents — structure des messages

### 29.1 Structure d'une demande d'information

```json
{
  "protocol_version": "1.0",
  "message_id": "<MSG_{ULID}>",
  "correlation_id": "<CORR_{ULID}>",
  "causation_id": null,
  "timestamp": "<ISO 8601 UTC>",
  "sender": {
    "agent_id": "<identifiant de l'agent émetteur>",
    "agent_version": "<semver>"
  },
  "recipient": {
    "agent_id": "inis"
  },
  "message_type": "INFORMATION_REQUEST",
  "payload": {
    "objective": "<objectif de la demande>",
    "requirements": [
      "<exigence_1>",
      "<exigence_2>"
    ],
    "minimum_confidence": "<float 0-1>"
  }
}
```

### 29.2 Structure d'une réponse d'information

```json
{
  "message_type": "INFORMATION_RESPONSE",
  "payload": {
    "status": "<état de sortie autorisé>",
    "findings": [
      {
        "information_id": "<INF_{ULID}>",
        "value": "<valeur extraite>",
        "unit": "<unité de mesure>",
        "confidence": "<float 0-1>",
        "evidence_ids": ["<EVID_{ULID}>"],
        "source_ids": ["<SRC_{ULID}>"]
      }
    ],
    "sources": ["<SRC_{ULID}>"],
    "evidence": ["<EVID_{ULID}>"],
    "conflicts": [],
    "limitations": [],
    "provenance": {
      "trace_id": "<TRACE_{ULID}>"
    }
  }
}
```

---

## 30. Délégation vers un autre agent

```text
Agent demandeur
  -> INIS
  -> compétence absente détectée
  -> Agent Registry
  -> découverte de l'agent compétent
  -> envoi de la demande à l'agent cible
  -> réception du résultat avec provenance
  -> vérification et rattachement au contexte
  -> livraison au demandeur initial
```

INIS NE DOIT PAS inventer une compétence absente du registre.

---

## 31. Frontend minimal

### 31.1 Écrans obligatoires

1. Soumettre une demande.
2. Voir l'état d'une recherche.
3. Visualiser les sources.
4. Consulter la matrice de confiance.
5. Consulter les contradictions.
6. Voir les informations extraites.
7. Voir les agents sollicités.
8. Consulter la traçabilité.
9. Consulter l'historique d'une requête.

### 31.2 Écran de confiance — structure attendue

```text
┌─────────────────────────────────────┐
│ Confiance globale        [score]    │
├─────────────────────────────────────┤
│ Source reliability       [score]    │
│ Freshness                [score]    │
│ Extraction               [score]    │
│ Data quality             [score]    │
│ Evidence strength        [score]    │
│ Cross-source agreement   [score]    │
└─────────────────────────────────────┘
```

---

## 32. API interne / externe

```text
POST   /v1/requests
GET    /v1/requests/{id}
POST   /v1/requests/{id}/cancel
GET    /v1/requests/{id}/events
GET    /v1/information/{id}
GET    /v1/sources/{id}
GET    /v1/evidence/{id}
GET    /v1/conflicts/{id}
GET    /v1/agents
POST   /v1/agents/register
GET    /v1/agents/{id}
GET    /v1/health
GET    /v1/metrics
```

Les appels inter-agents passent prioritairement par AMQP/MQTT. HTTP sert à l'administration, au frontend et aux intégrations compatibles.

---

## 33. Tests obligatoires

### 33.1 Unitaires

- parsing
- validation
- provenance
- scoring
- policy
- versioning
- détection de conflit

### 33.2 Intégration

- PostgreSQL
- pgvector
- object storage
- RabbitMQ
- MQTT
- connecteurs
- agent registry

### 33.3 Agentiques

- source fiable unique
- sources contradictoires
- information obsolète
- information insuffisante
- outil indisponible
- agent externe indisponible
- permission refusée
- demande ambiguë
- réutilisation de mémoire
- données modifiées entre deux recherches

### 33.4 Non-hallucination

> Toute affirmation factuelle produite par INIS DOIT être traçable vers une information, une source ou une transformation explicite.

Une sortie non traçable DOIT être marquée comme hypothèse, intention, proposition ou incertitude.

---

## 34. Observabilité et supervision

Métriques obligatoires :

```text
request_success_rate
request_latency
source_failure_rate
tool_failure_rate
agent_success_rate
confidence_distribution
conflict_rate
stale_data_rate
cache_hit_rate
vector_search_latency
postgres_latency
broker_latency
llm_cost
llm_latency
```

---

## 35. Roadmap d'implémentation

### Phase 1 — Kernel

- domaine
- modèles Pydantic
- configuration
- logging
- PostgreSQL
- migrations
- versioning
- audit

### Phase 2 — Agent runtime

- compréhension
- planning
- tool calling
- model router
- états
- itérations
- budgets

### Phase 3 — Network

- Agent Registry
- carte d'identité
- RabbitMQ
- protocole JSON
- corrélation
- découverte
- délégation

### Phase 4 — Information acquisition

- Web
- REST API
- fichiers structurés
- PDF
- documents
- images

### Phase 5 — Knowledge layer

- information units
- evidence
- pgvector
- recherche hybride
- mémoire
- provenance

### Phase 6 — Quality & confidence

- contrôles qualité
- contradictions
- scoring
- matrice de confiance
- fraîcheur

### Phase 7 — Security

- authentification
- permissions
- classification sensible
- politiques
- audit renforcé

### Phase 8 — Frontend

- interface minimaliste

### Phase 9 — Extensions

- OCR avancé
- audio
- vidéo
- streaming
- connecteurs additionnels
- déploiement Cloud
- exécution sandboxée de code si nécessaire

---

## 36. Critères d'acceptation V1

INIS est fonctionnel lorsque :

1. un autre agent peut s'enregistrer automatiquement ;
2. un agent peut découvrir INIS et ses capacités ;
3. un agent peut envoyer une demande JSON via le protocole ;
4. INIS construit automatiquement un plan ;
5. INIS peut rechercher sur le Web ;
6. INIS peut ingérer un fichier structuré ;
7. INIS peut interroger PostgreSQL ;
8. INIS stocke les sources et leurs métadonnées ;
9. INIS conserve la provenance ;
10. INIS peut retourner une information avec son contexte ;
11. INIS peut détecter un conflit ;
12. INIS attribue un score de confiance explicable ;
13. INIS peut solliciter un autre agent ;
14. INIS journalise l'ensemble de l'exécution ;
15. INIS respecte les politiques de permission ;
16. une information modifiée peut être retrouvée dans son historique ;
17. une suppression n'efface pas silencieusement l'historique ;
18. une information insuffisamment étayée est explicitement marquée comme telle ;
19. INIS n'utilise pas le LLM comme source de vérité ;
20. une sortie factuelle peut être reliée à une preuve et une source.

---

## 37. Règle absolue de conception

> **INIS doit privilégier la fidélité, la provenance et l'utilisabilité de l'information sur la beauté de la réponse.**

Dans le doute :

```text
conserver   > couper
tracer      > résumer
signaler    > inventer
vérifier    > supposer
structurer  > reformuler
versionner  > écraser
```

---

## 38. Décisions laissées configurables

Ne jamais coder en dur :

- fournisseurs Web
- fournisseurs LLM
- seuils de confiance
- poids des sources
- budget de recherche
- profondeur de navigation
- politiques de fraîcheur
- règles de conservation
- stratégies de délégation
- utilisation AMQP / MQTT
- règles de sélection des agents
- niveaux de sensibilité

---

## 39. Principe de séparation des responsabilités

```text
INIS
├── MOBILISER l'information
├── CONTROLER la qualité
├── PROVENIR / TRACER
├── STRUCTURER
├── VERIFIER
├── TRANSPORTER
└── ORIENTER vers l'agent compétent

Autres agents
├── ANALYSE MÉTIER
├── MODELISATION SPÉCIALISÉE
├── SYNTHÈSE
├── DÉCISION
└── PRODUCTION DU LIVRABLE FINAL
```

INIS peut raisonner pour vérifier la véracité et mobiliser l'information.
Il NE DOIT PAS devenir un agent métier généraliste.

---

## 40. Conclusion architecturale

INIS est une couche intelligente de mobilisation et de gouvernance de l'information.

Sa valeur vient de :

```text
AGENT RUNTIME
+
SOURCE CONNECTORS
+
KNOWLEDGE STORE
+
PROVENANCE
+
QUALITY ENGINE
+
CONFIDENCE ENGINE
+
AGENT NETWORK
+
GOVERNANCE
+
AUDIT
```

L'implémentation DOIT rester modulaire. L'ajout de nouveaux connecteurs, modèles, agents ou fournisseurs NE DOIT PAS nécessiter de refonte du noyau.

---

---

## 41. Aspects non couverts — prévisionnels

Cette section recense les domaines absents de la spécification initiale mais nécessaires à un système de production robuste. Ils DOIVENT être pris en compte dès la conception, même si leur implémentation est reportée.

---

### 41.1 Gestion du cycle de vie des requêtes longues

La spec couvre le traitement synchrone et la file AMQP, mais ne définit pas :

**Reprise sur interruption (`resume`).**
Une requête longue interrompue (crash, timeout infrastructure) DOIT pouvoir reprendre depuis le dernier état persisté, sans recommencer depuis zéro.

```json
{
  "resumable": true,
  "last_committed_step": "<STEP_{ULID}>",
  "last_committed_at": "<ISO 8601 UTC>",
  "resume_token": "<opaque string>"
}
```

**Progression explicite.**
Le demandeur DOIT pouvoir interroger la progression sans attendre la livraison finale :

```text
GET /v1/requests/{id}/progress

{
  "steps_total": "<entier>",
  "steps_done": "<entier>",
  "current_step": "<description>",
  "estimated_completion": "<ISO 8601 UTC | null>",
  "partial_findings_available": true
}
```

**Expiration gracieuse.**
Si le TTL d'une requête expire avant livraison, INIS DOIT livrer un résultat partiel marqué `PARTIAL_SUCCESS` plutôt que de perdre silencieusement le travail accompli.

---

### 41.2 Gestion des quotas et de la facturation interne

La spec définit `maximum_cost` mais ne précise pas comment les coûts sont mesurés, alloués et reportés.

**Unités de coût à définir `[CONFIG]` :**

```text
tokens_llm_input
tokens_llm_output
web_requests
api_calls
storage_bytes_written
storage_bytes_read
compute_seconds
```

**Budget par dimension :**

```json
{
  "budget": {
    "max_llm_tokens": "<entier>",
    "max_web_requests": "<entier>",
    "max_api_calls": "<entier>",
    "max_storage_bytes": "<entier>",
    "max_compute_seconds": "<entier>",
    "max_total_cost_usd": "<float | null>"
  }
}
```

**Rapport de consommation en sortie :**
Chaque réponse DOIT inclure un `usage_report` décrivant ce qui a été consommé, pour permettre la facturation inter-agents et la détection de dérives.

---

### 41.3 Internationalisation et multilinguisme

La spec mentionne `language` sur `InformationUnit` mais ne définit pas :

- La politique de langue de travail vs langue de la source.
- La gestion des sources multilingues sur un même sujet.
- La normalisation des unités et formats selon la région (virgule décimale, formats de date, devises).
- Le comportement lorsque deux sources contradictoires sont dans des langues différentes.

**Règles à définir `[CONFIG]` :**

```text
working_language           # langue des sorties
source_languages_allowed   # liste de codes BCP-47 acceptés
translation_policy         # never | on_demand | always
normalization_locale       # pour formats numériques et dates
```

**Chaque InformationUnit DOIT porter :**

```json
{
  "source_language": "<BCP-47>",
  "normalized_language": "<BCP-47>",
  "translation_applied": true,
  "translation_model": "<identifiant du modèle>",
  "translation_transformation_id": "<TRF_{ULID}>"
}
```

---

### 41.4 Gestion des sources requérant authentification

La spec couvre les connecteurs mais pas l'authentification aux sources externes :

- APIs avec OAuth2, API keys, Basic Auth.
- Sites Web avec session / cookies.
- Bases de données avec credentials rotatifs.
- Documents en accès restreint (intranet, portails partenaires).

**Vault de credentials `[CONFIG]` :**
Les credentials ne DOIVENT JAMAIS être stockés en clair en base ni apparaître dans les logs ou les `audit_event`. Un vault externe (HashiCorp Vault, AWS Secrets Manager) DOIT être utilisé.

```json
{
  "source_id": "<SRC_{ULID}>",
  "auth_type": "oauth2 | api_key | basic | certificate | none",
  "credential_ref": "<chemin dans le vault>",
  "token_expiry": "<ISO 8601 UTC | null>",
  "auto_refresh": true
}
```

---

### 41.5 Stratégie de cache et invalidation

La spec couvre la mémoire vectorielle mais pas le cache opérationnel :

**Niveaux de cache à distinguer :**

```text
L1 — Redis     : résultats de recherche Web récents, réponses API (TTL court)
L2 — PostgreSQL: information units déjà extraites et validées (TTL configurable)
L3 — pgvector  : embeddings persistants (invalidés par nouvelle version)
```

**Politique d'invalidation `[CONFIG]` :**

```json
{
  "cache_invalidation": {
    "on_source_update": true,
    "on_conflict_detected": true,
    "on_quality_failure": true,
    "max_ttl_seconds": "<entier>",
    "freshness_threshold_hours": "<entier>"
  }
}
```

**Règle :** une entrée cache NE DOIT PAS être réutilisée si sa `source_freshness` est inférieure au seuil de fraîcheur de la requête courante.

---

### 41.6 Gestion des données structurées volumineuses

La spec couvre l'ingestion de fichiers mais pas le traitement de datasets dépassant la mémoire disponible :

**Stratégie de traitement par chunks :**

```python
class ChunkedDatasetProcessor(Protocol):
    async def stream(self, dataset_id: str, chunk_size: int) -> AsyncIterator[DataChunk]: ...
    async def process_chunk(self, chunk: DataChunk) -> ChunkResult: ...
    async def merge_results(self, results: list[ChunkResult]) -> Dataset: ...
```

**Seuils à configurer `[CONFIG]` :**

```text
max_in_memory_rows        # au-delà, passage en streaming
max_in_memory_bytes       # au-delà, passage en streaming
chunk_size_rows           # taille des chunks
parallel_chunks           # chunks traités en parallèle
```

---

### 41.7 Détection de désinformation et de manipulation de source

La spec détecte les contradictions inter-sources mais ne prévoit pas :

- La détection de sources synthétiques ou générées par IA.
- La détection de sites miroirs ou de copie de contenu.
- La détection de manipulation éditoriale (biais systématique d'une source).
- La détection de fraîcheur artificielle (contenu ancien re-daté).

**Signal de suspicion `[CONFIG]` :**

```json
{
  "source_suspicion": {
    "synthetic_content_detected": false,
    "mirror_of": "<SRC_{ULID} | null>",
    "editorial_bias_score": "<float 0-1>",
    "freshness_manipulation_suspected": false,
    "suspicion_reason": "<description | null>"
  }
}
```

Une source avec `synthetic_content_detected = true` NE DOIT PAS contribuer à un `Finding` sans avertissement explicite.

---

### 41.8 Politique de retry et circuit breaker

La spec liste les états d'erreur mais ne définit pas la politique de retry :

**Structure `[CONFIG]` :**

```json
{
  "retry_policy": {
    "max_attempts": "<entier>",
    "initial_delay_ms": "<entier>",
    "backoff_multiplier": "<float>",
    "max_delay_ms": "<entier>",
    "retryable_errors": ["SOURCE_UNAVAILABLE", "TOOL_FAILURE", "TIMEOUT"]
  },
  "circuit_breaker": {
    "failure_threshold": "<entier>",
    "recovery_timeout_seconds": "<entier>",
    "half_open_max_calls": "<entier>"
  }
}
```

Le circuit breaker s'applique par connecteur, par fournisseur Web et par agent externe. L'état `open | closed | half_open` DOIT être exposé dans `/v1/health`.

---

### 41.9 Gestion du consentement et des droits sur les données

La spec couvre PII et politiques d'accès, mais pas :

- Le droit à l'oubli (RGPD Article 17) : comment propager une suppression logique dans toute la chaîne de provenance.
- Le droit de rectification : comment corriger une information erronée sans casser la traçabilité.
- La durée de rétention légale par type de données `[CONFIG]`.
- La portabilité : export de toutes les données liées à un agent demandeur.

**Durée de rétention `[CONFIG]` :**

```json
{
  "retention_policies": {
    "audit_events": "<durée en jours>",
    "information_units": "<durée en jours>",
    "pii_data": "<durée en jours>",
    "embeddings": "<durée en jours>",
    "artifacts": "<durée en jours>"
  }
}
```

**Droit à l'oubli :**
Une demande de suppression d'un `actor_id` DOIT déclencher la pseudonymisation de tous les `audit_event` et `information_unit` liés, sans supprimer la structure de provenance.

---

### 41.10 Gestion des dépendances entre agents (topologie)

La spec couvre la découverte et la délégation, mais pas :

**Détection de cycles de délégation.**
Si INIS délègue à l'Agent A, qui délègue à l'Agent B, qui redélègue à INIS, le système DOIT détecter et rompre le cycle.

```python
class DelegationGraph:
    def detect_cycle(self, path: list[str]) -> bool: ...
    def max_depth_reached(self, path: list[str], max_depth: int) -> bool: ...
```

**Topologie connue `[CONFIG]` :**
INIS DEVRAIT maintenir une carte des relations de confiance entre agents (qui peut déléguer à qui, avec quel niveau de confiance).

```json
{
  "agent_trust_graph": {
    "<agent_id>": {
      "trusted_agents": ["<agent_id>"],
      "trust_level": "full | partial | minimal",
      "max_delegation_depth": "<entier>"
    }
  }
}
```

---

### 41.11 Migration et compatibilité ascendante du protocole

La spec définit `protocol_version: "1.0"` mais ne prévoit pas l'évolution :

- Comment INIS gère-t-il un message en version `1.1` qu'il ne connaît pas encore ?
- Comment déprécier un type de message sans casser les agents existants ?
- Comment négocier la version lors de l'enregistrement d'un agent ?

**Règles obligatoires :**

```text
- Champs inconnus : ignorer silencieusement (tolérance forward)
- Champs manquants : utiliser les valeurs par défaut (tolérance backward)
- Version majeure incompatible : rejeter avec VALIDATION_ERROR + version_supported
- Négociation lors du AGENT_REGISTER : l'agent déclare ses versions supportées
```

```json
{
  "protocol_compatibility": {
    "supported_versions": ["1.0", "1.1"],
    "preferred_version": "1.0",
    "min_version": "1.0"
  }
}
```

---

### 41.12 Observabilité des décisions du LLM

La spec audit les opérations mais pas les décisions de raisonnement du LLM, ce qui rend le système difficile à déboguer et à auditer en production.

**Trace de décision LLM :**
Chaque appel LLM significatif (compréhension, planification, classification) DOIT produire un `llm_decision_trace` :

```json
{
  "llm_decision_id": "<ULID>",
  "request_id": "<REQ_{ULID}>",
  "step_id": "<STEP_{ULID}>",
  "task_type": "understanding | planning | classification | conflict_detection | confidence_signal",
  "model_used": "<identifiant du modèle>",
  "prompt_hash": "<sha256 du prompt>",
  "input_token_count": "<entier>",
  "output_token_count": "<entier>",
  "latency_ms": "<entier>",
  "decision_summary": "<description courte de la décision prise>",
  "alternatives_considered": [],
  "confidence_in_decision": "<float 0-1>",
  "timestamp": "<ISO 8601 UTC>"
}
```

Le `prompt_hash` permet de retrouver le prompt exact sans le stocker en clair (coût de stockage et confidentialité).

---

### 41.13 Tests de charge et limites de dimensionnement

La spec liste les tests fonctionnels mais pas les tests de performance :

**Benchmarks à définir avant mise en production :**

```text
throughput_requests_per_second    # requêtes concurrentes acceptées
max_information_units_per_request # au-delà, chunking obligatoire
vector_search_latency_p99_ms      # seuil d'alerte
postgres_query_latency_p99_ms     # seuil d'alerte
amqp_message_latency_p99_ms       # seuil d'alerte
llm_call_latency_p99_ms           # seuil d'alerte
max_plan_steps                    # au-delà, plan jugé trop complexe
max_parallel_tool_calls           # limite de concurrence
```

Ces seuils DOIVENT être documentés, mesurés en environnement de staging et exposés dans `/v1/metrics`.

---

### 41.14 Stratégie de déploiement et de migration de schéma

La spec mentionne Alembic mais ne définit pas :

**Règles de migration sans interruption de service :**

```text
- Toute migration DOIT être backward-compatible pendant au minimum une version.
- Aucun `DROP COLUMN` ou `ALTER TYPE` direct : passer par des étapes intermédiaires.
- Les colonnes supprimées restent présentes une version avant d'être retirées.
- Les nouvelles colonnes NE DOIVENT PAS avoir de contrainte NOT NULL sans DEFAULT.
- Toute migration DOIT avoir un script de rollback validé.
```

**Blue/Green et canary :**
INIS DEVRAIT supporter le déploiement canary en exposant sa version dans `/v1/health` et dans chaque `Envelope` (`agent_version`), permettant au routeur d'infrastructure de distribuer le trafic progressivement.

---

### 41.15 Documentation automatique et contrat d'interface

La spec est un document normatif, mais le système ne prévoit pas de générer automatiquement sa propre documentation à partir du code :

- L'API HTTP DOIT exposer un `OpenAPI 3.1` généré automatiquement via FastAPI, accessible à `/v1/docs` et `/v1/openapi.json`.
- Les schémas Pydantic DOIVENT être la source de vérité pour l'OpenAPI.
- Le registre d'agents DOIT exposer les `input_schemas` et `output_schemas` de chaque agent en JSON Schema valide, consultables via `GET /v1/agents/{id}/schema`.
- Un changelog machine-readable DOIT être maintenu à `GET /v1/changelog`.

---

**Fin de la spécification d'implémentation exécutable v0.2.0 — section 41 ajoutée.**
