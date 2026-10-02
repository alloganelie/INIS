"""§16.1/§22/§41.12 — embed the §11 units of a colis, or state why not.

The ``embeddings`` table (migration ``0003``) has existed since V1 with its HNSW
index, ``app/tools/knowledge/vector_searcher.py`` reads it — and **nothing ever
wrote a row** (C13): the §16.2 semantic half of the search was dead code, and a
delivery could claim a `vector_search` tool that returned nothing for ever.

This module produces those rows, and it owns four rules:

* **the text embedded is the text stored**: it is the same
  :func:`app.knowledge.enrichment.unit_text` the enricher reads, so a vector is
  never the embedding of something the colis does not contain;
* **the model is traced**: the call goes through the §22 Model Router and writes
  one ``llm_decision_trace`` per batch (§41.12), and ``embeddings.model`` names
  the model that really answered — a vector whose model is unknown is
  unusable the day the model changes;
* **the width is the column's**: :data:`EMBEDDING_DIMENSION` is the width of
  ``embeddings.vector`` (``0003``); a provider answering another one is refused
  rather than truncated (a truncated vector is not the embedding of anything);
* **no silent zero vector**: without a provider the outcome carries **no**
  record and one limitation naming the missing variable. A null vector would be
  indistinguishable from a real one once stored (§0.2).

No database is required to *produce* the vectors: :func:`generate_embeddings` is
pure apart from the model call, and :func:`persist_embeddings` is the only
function that writes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import InfrastructureError
from app.core.hashing import sha256_hex
from app.core.logging import get_logger
from app.knowledge.enrichment import unit_text
from app.llm.router.model_router import (
    EMBEDDING_DIMENSION,
    EmbeddingResponse,
    ModelRouter,
)

#: Delivery logger — a metric or a trace that could not be written is stated.
logger = get_logger(__name__)

__all__ = [
    "EMBEDDING_DIMENSION",
    "EMBEDDING_OWNER_TYPE",
    "EmbeddingOutcome",
    "EmbeddingRecord",
    "default_embedding_cache",
    "embedding_cache_key",
    "embedding_row_id",
    "generate_embeddings",
    "persist_embeddings",
]

#: §16.1 — ``embeddings.owner_type`` of an ``InformationUnit``. Kept in step with
#: ``app.tools.knowledge.vector_searcher.OWNER_TYPE`` by
#: ``tests/unit/knowledge/test_embeddings_generator.py``: a row the searcher
#: cannot see would be dead weight.
EMBEDDING_OWNER_TYPE = "information_unit"


def embedding_cache_key(
    unit_id: str, text_hash: str, model: str, dimension: int, version: str | None
) -> tuple[str, ...]:
    """Return the L3 cache parts of one unit's embedding (§41.5).

    Tout ce qui décide de l'identité du vecteur entre dans la clé : le texte
    (par son empreinte), le modèle, la largeur, **et** la version courante de
    l'unité. Une nouvelle version de l'unité change donc la clé, ce qui est
    exactement l'invalidation « par nouvelle version » du §41.5 — sans quoi un
    vecteur calculé avant la révision serait servi pour le texte révisé.
    """
    return (
        EMBEDDING_OWNER_TYPE,
        str(unit_id),
        str(text_hash),
        str(model),
        str(dimension),
        str(version or ""),
    )


def default_embedding_cache() -> Any | None:
    """Return a cache with the L3 (pgvector) level, or ``None`` without a database.

    Sans base configurée il n'y a pas de L3 : rendre ``None`` vaut mieux qu'un
    cache qui prétendrait retenir quelque chose. L'import est paresseux, comme
    celui de ``ModelRouter``, pour que ``app.knowledge`` ne dépende pas de
    ``app.storage`` au chargement.
    """
    try:
        from app.storage.cache.cache_store import CacheStore
        from app.storage.cache.vector_backend import PgVectorCacheBackend
    except Exception:  # noqa: BLE001 - no storage layer, no L3
        return None
    backend = PgVectorCacheBackend()
    if not backend.available:
        return None
    return CacheStore(l3_async_backend=backend)


def vector_literal(vector: Sequence[float]) -> str:
    """Return the pgvector text literal ``[a,b,c]`` of *vector*.

    Args:
        vector: Embedding values.

    Returns:
        A literal accepted by ``CAST(:vector AS vector)``.
    """
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


@dataclass(frozen=True)
class EmbeddingRecord:
    """One vector ready to be stored in ``embeddings`` (§16.1).

    ``embedding_id`` is a **UUID** because that is the column's type (migration
    ``0003``), not a ``ULID``: an identifier the table cannot hold is not an
    identifier.
    """

    owner_id: str
    vector: tuple[float, ...]
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)
    owner_type: str = EMBEDDING_OWNER_TYPE
    embedding_id: str = ""

    def __post_init__(self) -> None:
        """Mint the identifier when the caller did not supply one."""
        if not self.embedding_id:
            object.__setattr__(self, "embedding_id", str(uuid.uuid4()))

    def to_row(self) -> dict[str, Any]:
        """Return the row as the parameters of the ``embeddings`` INSERT."""
        return {
            "embedding_id": self.embedding_id,
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "model": self.model,
            "vector": vector_literal(self.vector),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EmbeddingOutcome:
    """What the §16.1 step produced for a colis."""

    records: tuple[EmbeddingRecord, ...] = ()
    model: str | None = None
    dimension: int = EMBEDDING_DIMENSION
    skipped: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()
    input_tokens: int = 0
    #: §41.5 L3 — how many of ``records`` were served by the pgvector cache
    #: instead of being computed and paid for again.
    reused: int = 0

    @property
    def owner_ids(self) -> list[str]:
        """Return the ``owner_id`` of every record produced."""
        return [record.owner_id for record in self.records]

    @property
    def vector_count(self) -> int:
        """Return how many vectors were produced."""
        return len(self.records)

    def lineage(self) -> dict[str, Any] | None:
        """Return the parameters of the step (§12.1), or ``None`` when empty.

        ``None`` means no vector was produced: the step must then stay absent
        from the lineage rather than be recorded as if it had run (§0.2).
        """
        if not self.records:
            return None
        return {
            "unit_ids": self.owner_ids,
            "model": self.model,
            "dimension": self.dimension,
            "vectors": self.vector_count,
            # §41.5 L3 — combien de vecteurs viennent du cache : le gain de
            # l'appel évité est lisible, et il l'est sans le confondre avec les
            # vecteurs réellement calculés.
            "reused": self.reused,
            "computed": self.vector_count - self.reused,
            "skipped": len(self.skipped),
            "tokens": self.input_tokens,
        }


def _candidates(
    units: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Return the embeddable ``(unit_id, text)`` pairs and why others were skipped."""
    candidates: list[tuple[str, str]] = []
    skipped: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, Mapping):
            continue
        unit_id = str(unit.get("information_id") or "")
        if not unit_id:
            skipped.append({"information_id": "", "reason": "no_identifier"})
            continue
        text = unit_text(unit)
        if not text.strip():
            skipped.append({"information_id": unit_id, "reason": "no_text"})
            continue
        candidates.append((unit_id, text))
    return candidates, skipped


def _expected_model(router: Any, override: str | None) -> str:
    """Return the model the router will probably answer with, or ``""``.

    Un modèle vide signifie « inconnu » : la réutilisation L3 est alors
    **désactivée** pour ce lot, parce qu'un identifiant calculé sur un modèle
    inconnu ne peut pas être comparé sans risque.
    """
    if override:
        return str(override)
    getter = getattr(router, "embeddings_model", None)
    if callable(getter):
        try:
            return str(getter() or "")
        except Exception:  # noqa: BLE001 - an unreadable model is an unknown model
            return ""
    return ""


def _version_head(unit: Mapping[str, Any]) -> str | None:
    """Return the current version of one unit (§18.1), or ``None``.

    La version courante de l'unité entre dans la clé L3 : un texte révisé produit
    donc une autre entrée, ce qui est l'invalidation « par nouvelle version » du
    §41.5 — l'ancienne ligne reste l'historique, elle n'est jamais servie pour le
    texte révisé.
    """
    versions = unit.get("versions")
    if isinstance(versions, Sequence) and not isinstance(versions, (str, bytes)):
        return str(versions[-1]) if versions else None
    return str(versions) if versions else None


def embedding_row_id(owner_id: str, text_hash: str, model: str, dimension: int) -> str:
    """Return the deterministic ``embeddings.embedding_id`` of one vector.

    L'identifiant est un UUID parce que c'est le type de la colonne (``0003``),
    et il est **déterministe** parce que c'est la réutilisation qui l'exige : le
    même propriétaire, le même texte, le même modèle et la même largeur
    retombent sur la même ligne, ce qui rend l'insertion idempotente sans clé
    secondaire. Le propriétaire en fait partie : deux unités qui portent le même
    texte restent deux lignes (la recherche §16.2 joint sur ``owner_id``).
    """
    from app.storage.cache.vector_backend import PgVectorCacheBackend

    return PgVectorCacheBackend.embedding_key(owner_id, text_hash, model, dimension)


def _metadata(unit: Mapping[str, Any], text: str, request_id: str | None) -> dict[str, Any]:
    """Return the §16.1 metadata block of one vector.

    It carries what a reader needs to understand the row later — the digest of
    the embedded text (so drift is detectable), its length, the §12 stage it was
    read at, and where it came from — never the text itself: the colis already
    holds it, and duplicating it would double the storage for nothing.
    """
    return {
        "text_hash": sha256_hex(text),
        "chars": len(text),
        "data_stage": unit.get("data_stage"),
        "source_id": unit.get("source_id"),
        "document_id": unit.get("document_id"),
        "request_id": request_id,
    }


def _observe_embedding_latency(latency_ms: int) -> None:
    """Feed the §34 ``llm_latency`` histogram with the model call of this step.

    §34 has no embedding-specific metric: the call *is* an LLM-provider call, so
    it lands in ``llm_latency`` rather than in an invented metric name.
    """
    try:
        from app.observability.metrics import observe_value

        observe_value("llm_latency", float(latency_ms))
    except Exception as exc:  # noqa: BLE001 - observability never breaks a generation
        logger.warning("embedding latency not observed", error=str(exc))


def _trace_embedding(
    trace_writer: Any | None,
    texts: Sequence[str],
    response: EmbeddingResponse,
    *,
    step_id: str,
    request_id: str | None,
) -> list[str]:
    """Write the §41.12 trace of an embeddings step, never raising.

    One trace per generation step: the §22 router may split the batch into
    several HTTP calls, but the step the operator asks about is « embed this
    colis ». The prompt is hashed by the writer, never stored.

    Returns:
        The limitations describing a trace that could not be written — a model
        call with no trace is a lineage gap, and a gap is stated (§0.2).
    """
    if trace_writer is None:
        return []
    try:
        trace = trace_writer.build_trace(
            request_id or "REQ_EMBEDDINGS",
            step_id,
            "embedding",
            response.model,
            "\n".join(texts),
            input_tokens=response.input_tokens,
            latency_ms=response.latency_ms,
            decision_summary=f"{len(response.vectors)} vecteur(s) par {response.model}",
        )
        trace_writer.write(trace)
    except Exception as exc:  # noqa: BLE001 - §41.12: a trace gap is stated
        return [
            (
                "Trace LLM §41.12 de l'étape « embedding » non écrite "
                f"({type(exc).__name__}: {exc})."
            )
        ]
    return []


async def generate_embeddings(
    units: Sequence[Mapping[str, Any]],
    *,
    router: ModelRouter | None = None,
    model: str | None = None,
    dimension: int = EMBEDDING_DIMENSION,
    batch_size: int | None = None,
    trace_writer: Any | None = None,
    request_id: str | None = None,
    step_id: str = "embedding",
    cache: Any | None = None,
    use_cache: bool = True,
) -> EmbeddingOutcome:
    """Embed the §11 units of a colis, or state why no vector was produced.

    Args:
        units: The §11 units of a run (or of a document), as mappings.
        router: §22 Model Router to call; a default one when omitted.
        model: Embeddings model override; the router decides otherwise.
        dimension: Expected vector width, ``EMBEDDING_DIMENSION`` by default.
        batch_size: Texts per model call; the router decides when omitted.
        trace_writer: §41.12 writer receiving one ``embedding`` trace per call.
        request_id: Request the vectors belong to (kept in the trace/metadata).
        step_id: Step the trace is attached to.
        cache: §41.5 cache holding the L3 (pgvector) level. When omitted, one is
            built from ``INIS_DATABASE_URL``; without a database there is no L3.
        use_cache: Set ``False`` to compute everything (measurement, tests).

    Returns:
        An :class:`EmbeddingOutcome`: one :class:`EmbeddingRecord` per unit that
        could be embedded (with its model and metadata), the units left out and
        why, and the limitations that state anything that could not be done.

    A unit without identifier or without any analysable text is **skipped** and
    named: it is never embedded as an empty string, which would put a vector of
    nothing in the index. Without a configured provider the outcome carries no
    record at all and one limitation naming the cause — never a zero vector.
    """
    candidates, skipped = _candidates(units)
    if not candidates:
        limitations: list[str] = []
        if units:
            limitations.append(
                f"Aucun vecteur §16.1 produit : les {len(units)} unité(s) du colis "
                "n'ont ni texte analysable ni identifiant (§0.2)."
            )
        return EmbeddingOutcome(skipped=tuple(skipped), limitations=tuple(limitations))

    active_router = router or ModelRouter()
    active_cache = cache
    if active_cache is None and use_cache:
        active_cache = default_embedding_cache()

    by_id = {
        str(unit.get("information_id") or ""): unit
        for unit in units
        if isinstance(unit, Mapping)
    }
    text_hashes = {unit_id: sha256_hex(text) for unit_id, text in candidates}
    # Le modèle qui va répondre est celui que le routeur annonce ; s'il en annonce
    # un autre, la clé L3 ne vaut plus et la lecture est abandonnée (plus bas),
    # plutôt que de risquer un hit du mauvais modèle.
    expected_model = _expected_model(active_router, model)

    reused: dict[str, list[float]] = {}
    reused_metadata: dict[str, dict[str, Any]] = {}
    if active_cache is not None and expected_model:
        for unit_id, _text in candidates:
            unit = by_id.get(unit_id, {})
            found = await active_cache.aget_l3(
                "embedding",
                embedding_cache_key(
                    unit_id, text_hashes[unit_id], expected_model, dimension, _version_head(unit)
                ),
                owner_id=unit_id,
                text_hash=text_hashes[unit_id],
                model=expected_model,
                dimension=dimension,
            )
            if found:
                reused[unit_id] = [float(item) for item in found]
                reused_metadata[unit_id] = {
                    "cache": {
                        "hit": True,
                        "level": "L3",
                        "text_hash": text_hashes[unit_id],
                        "model": expected_model,
                        "dimension": dimension,
                    }
                }

    to_compute = [(unit_id, text) for unit_id, text in candidates if unit_id not in reused]
    limitations_list: list[str] = []
    response: EmbeddingResponse | None = None
    if to_compute:
        try:
            response = await active_router.embed(
                [text for _, text in to_compute],
                model=model,
                dimension=dimension,
                batch_size=batch_size,
            )
        except InfrastructureError as exc:
            if not reused:
                return EmbeddingOutcome(
                    skipped=tuple(skipped),
                    limitations=(
                        (
                            f"Aucun vecteur §16.1 produit ({exc}) : le volet sémantique de "
                            "§16.2 reste indisponible pour ce colis, et aucun vecteur nul "
                            "n'est inventé (§0.2)."
                        ),
                    ),
                )
            # Le cache a déjà couvert une partie du colis : la panne est dite, et
            # les vecteurs réutilisés restent livrés tels quels — jamais complétés
            # par des valeurs inventées.
            limitations_list.append(
                "Vecteurs §16.1 partiellement réutilisés (cache L3) ; le calcul des "
                f"{len(to_compute)} restant(s) a échoué ({exc})."
            )

    if response is not None and expected_model and response.model != expected_model:
        # Le provider a répondu avec un autre modèle : les identifiants calculés
        # avec le modèle annoncé ne décrivent plus ces vecteurs. On les recalcule
        # avec le modèle réel, et la réutilisation est abandonnée pour ce lot.
        limitations_list.append(
            "Le fournisseur d'embeddings a répondu avec un autre modèle que celui "
            f"configuré ({expected_model} → {response.model}) : la réutilisation L3 est "
            "abandonnée pour ce lot (§41.5)."
        )
        reused = {}
        reused_metadata = {}
        to_compute = list(candidates)

    _observe_embedding_latency(response.latency_ms if response is not None else 0)
    computed = (
        {
            unit_id: tuple(vector)
            for (unit_id, _text), vector in zip(to_compute, response.vectors, strict=True)
        }
        if response is not None
        else {}
    )
    active_model = response.model if response is not None else expected_model
    records_list: list[EmbeddingRecord] = []
    for unit_id, text in candidates:
        unit = by_id.get(unit_id, {})
        if unit_id in reused:
            vector = tuple(reused[unit_id])
            metadata = {**_metadata(unit, text, request_id), **reused_metadata[unit_id]}
        elif unit_id in computed:
            vector = computed[unit_id]
            metadata = {
                **_metadata(unit, text, request_id),
                "cache": {
                    "hit": False,
                    "level": "L3",
                    "text_hash": text_hashes[unit_id],
                },
            }
        else:
            continue
        records_list.append(
            EmbeddingRecord(
                owner_id=unit_id,
                vector=vector,
                model=str(active_model or ""),
                metadata=metadata,
                embedding_id=embedding_row_id(
                    unit_id, text_hashes[unit_id], str(active_model or ""), len(vector)
                ),
            )
        )

    if response is not None:
        limitations_list.extend(
            _trace_embedding(
                trace_writer,
                [text for _, text in to_compute],
                response,
                step_id=step_id,
                request_id=request_id,
            )
        )
    return EmbeddingOutcome(
        records=tuple(records_list),
        model=active_model,
        dimension=dimension,
        skipped=tuple(skipped),
        limitations=tuple(limitations_list),
        input_tokens=response.input_tokens if response is not None else 0,
        reused=len(reused),
    )


async def persist_embeddings(
    records: Sequence[EmbeddingRecord],
    *,
    engine: Any | None = None,
    connection_string: str | None = None,
) -> tuple[int, list[str]]:
    """Store *records* in the ``embeddings`` table, idempotently (§16.1).

    Args:
        records: The vectors produced by :func:`generate_embeddings`.
        engine: Async engine; the default one (``INIS_DATABASE_URL``) when omitted.
        connection_string: PostgreSQL URL used when *engine* is omitted.

    Returns:
        ``(written, limitations)``: how many rows were really inserted, and what
        could not be done. A failed write never raises — a vector accelerates the
        search, and losing a colis because its index could not be updated would be
        worse than a stated gap (§25.2).

    Inserting the same identifier twice is a no-op (``ON CONFLICT DO NOTHING``),
    so a run and ``scripts/backfill_embeddings.py`` can both execute without ever
    duplicating a vector.
    """
    if not records:
        return 0, []
    from app.storage.database.engine import create_engine_or_none, get_default_engine
    from app.storage.repositories.embedding_repository import EmbeddingRepository

    active = engine
    owned = False
    if active is None and connection_string:
        active = create_engine_or_none(connection_string)
        owned = active is not None
    if active is None:
        active = get_default_engine()
    if active is None:
        return 0, [
            (
                "Embeddings §16.1 non persistés (INIS_DATABASE_URL non configuré) : les "
                "vecteurs restent hors base et le volet sémantique de §16.2 ne les verra pas."
            )
        ]
    try:
        written = await EmbeddingRepository.insert_many(
            active, [record.to_row() for record in records]
        )
    except Exception as exc:  # noqa: BLE001 - §25.2: the gap is named, not hidden
        return 0, [
            (
                f"Embeddings §16.1 non persistés ({type(exc).__name__}: {exc}) : les "
                "vecteurs ne sont pas indexés et §16.2 ne les retrouvera pas."
            )
        ]
    finally:
        if owned:
            await active.dispose()
    return written, []
