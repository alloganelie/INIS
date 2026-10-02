"""§41.5 L3 — le niveau pgvector : réutiliser un embedding déjà calculé.

La spec distingue trois niveaux et donne à L3 une nature propre : « L3 — pgvector :
embeddings persistants (invalidés par nouvelle version) ». Ce n'est donc pas un
troisième exemplaire de L1/L2 (une paire clé/valeur à TTL) : c'est la table
``embeddings`` (§16.1), déjà écrite par :func:`app.knowledge.embedding.embeddings_generator.generate_embeddings`
et déjà lue par la recherche §16.2. Ce backend **ne crée aucune table** et
**n'introduit aucun second mécanisme** : il branche la lecture existante sur le
``CacheStore`` pour éviter un appel au fournisseur.

Une entrée L3 est identifiée par la **clé déterministe** que le générateur sait
reconstruire (namespace + modèle + dimensions + empreinte du texte), et sa
``metadata`` porte ce qui explique un hit : l'empreinte du texte, le modèle et la
largeur. C'est ce qui rend un faux hit impossible : le même identifiant ne peut
être produit que par le même texte, le même modèle et la même dimension.

Le vecteur rendu est une liste de flottants ; l'accesseur ``aget`` est la seule
lecture, et il ne rend rien d'autre que ce que la base contient (jamais un
vecteur nul fabriqué).
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.storage.cache.cache_store import L3, CacheEntry
from app.storage.database.engine import get_default_engine
from app.storage.repositories.embedding_repository import EmbeddingRepository

__all__ = ["PgVectorCacheBackend"]


class PgVectorCacheBackend:
    """Le niveau L3 du §41.5, lu et écrit dans la table ``embeddings``."""

    #: Namespace des clés L3 : il isole les embeddings des autres niveaux, et
    #: apparaît dans l'identifiant, donc dans la clé relue ici.
    NAMESPACE = "embedding"

    def __init__(self, engine: Any | None = None) -> None:
        """Bind the backend to *engine*, or to ``INIS_DATABASE_URL`` lazily."""
        self._engine = engine

    def _resolve(self) -> Any | None:
        """Return the engine to use, or ``None`` when no database is configured."""
        return self._engine if self._engine is not None else get_default_engine()

    @property
    def available(self) -> bool:
        """Return whether PostgreSQL (and therefore pgvector) is reachable."""
        return self._resolve() is not None

    @staticmethod
    def embedding_key(owner_id: str, text_hash: str, model: str, dimension: int) -> str:
        """Return the identifier that ties a row to its ``(owner, text, model, width)``.

        Déterministe **et** vérifiable : le propriétaire, l'empreinte du texte, le
        modèle et la dimension entrent dans l'identifiant, donc un autre texte, un
        autre modèle ou une autre largeur ne peuvent pas retomber sur la même
        ligne. Le propriétaire compte : deux unités qui portent le même texte sont
        **deux** entrées (la recherche §16.2 joint sur ``owner_id`` — les faire
        partager une ligne priverait l'une d'elles de son vecteur).
        """
        digest = hashlib.sha256(
            f"{owner_id}|{text_hash}|{model}|{dimension}".encode()
        ).hexdigest()
        return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"

    async def aget(
        self,
        cache_key: str,
        *,
        owner_id: str,
        text_hash: str,
        model: str,
        dimension: int,
    ) -> CacheEntry | None:
        """Return the stored embedding, or ``None`` when nothing matches.

        Les critères sont **vérifiés sur la ligne relue**, pas seulement supposés :
        une ligne dont le propriétaire, l'empreinte, le modèle ou la largeur
        diffère est refusée (jamais convertie en hit). La clé du ``CacheStore``
        n'est utile qu'au diagnostic : c'est l'identifiant déterministe qui fait
        la lecture.
        """
        engine = self._resolve()
        if engine is None:
            return None
        row = await EmbeddingRepository.get(
            engine, self.embedding_key(owner_id, text_hash, model, dimension)
        )
        if row is None:
            return None
        metadata = dict(row.get("metadata") or {})
        vector = [float(item) for item in (row.get("vector") or [])]
        if not vector:
            # Une ligne sans vecteur lisible n'est pas un embedding : la refuser
            # vaut mieux que rendre une liste vide qu'un appelant prendrait pour
            # un résultat.
            return None
        if str(row.get("owner_id") or "") != owner_id:
            return None
        if metadata.get("text_hash") != text_hash:
            return None
        if str(row.get("model") or "") != model:
            return None
        if len(vector) != dimension:
            return None
        return CacheEntry(
            key=cache_key,
            value=vector,
            level=L3,
            source_id=metadata.get("source_id"),
            source_freshness=row.get("created_at"),
            metadata={
                "text_hash": metadata.get("text_hash"),
                "model": row.get("model"),
                "dimension": len(vector),
                "owner_id": row.get("owner_id"),
                "data_stage": metadata.get("data_stage"),
                "document_id": metadata.get("document_id"),
                "request_id": metadata.get("request_id"),
            },
        )

    async def aset(
        self, entry: CacheEntry, *metadata: Any, **kwargs: Any
    ) -> bool:
        """Return whether the entry can be written by this backend.

        Une entrée L3 **est** une ligne ``embeddings`` : le générateur la persiste
        par ``persist_embeddings`` (§16.1), qui gère l'idempotence. Ce backend ne
        réécrit donc rien — il l'indique, et le générateur écrit. Cela évite deux
        chemins d'écriture concurrents vers la même table, ce qui est exactement
        la « seconde architecture » à ne pas créer.
        """
        return False