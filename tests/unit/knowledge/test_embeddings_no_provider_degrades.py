"""§16.1/§0.2 — sans fournisseur : aucun vecteur, et la cause est nommée.

Un vecteur nul, ou un vecteur de remplacement, serait **indiscernable** d'un vrai
une fois stocké : la recherche §16.2 renverrait alors des résultats aléatoires
comme si c'étaient des similarités mesurées. C'est exactement l'invention que
§0.2 interdit.

Ce fichier verrouille donc :

* ``ModelRouter.embed`` **n'a pas de stub** — contrairement à ``complete``, dont
  le comportement hors ligne reste inchangé (les deux sont vérifiés ici) ;
* le générateur renvoie alors **zéro** record, une limitation qui nomme la
  variable manquante, et **pas de lignage** ;
* la persistance sans base est un constat, pas une exception : ``(0, limitation)`` ;
* une réponse malformée ou d'une autre largeur est **refusée**, jamais tronquée.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import InfrastructureError
from app.knowledge.embedding import generate_embeddings, persist_embeddings
from app.llm.router.model_router import (
    EMBEDDING_DIMENSION,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_EMBEDDING_MODEL,
    ModelRouter,
)

UNIT = {
    "information_id": "INF_01M3Q0000000000000000000BB",
    "content": {"text": "Le fournisseur a livré 12 kilos de café"},
    "data_stage": "enriched",
}


def _router() -> ModelRouter:
    """Return a router with no environment read at import time."""
    return ModelRouter(retry_attempts=1, retry_backoff_seconds=0)


def _client(handler: object) -> httpx.AsyncClient:
    """Return a client whose transport answers *handler* (no real network)."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _payload(count: int, dimension: int) -> dict[str, object]:
    """Return an OpenAI-compatible embeddings payload."""
    return {
        "data": [
            {"index": index, "embedding": [0.5] * dimension} for index in range(count)
        ],
        "usage": {"prompt_tokens": 3 * count},
    }


@pytest.fixture(autouse=True)
def _no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any ambient provider configuration, like a fresh offline install."""
    for name in (ENV_API_KEY, ENV_BASE_URL, ENV_EMBEDDING_MODEL):
        monkeypatch.delenv(name, raising=False)


class TestNoProviderMeansNoVector:
    """Le contraste entre ``complete`` (stub assumé) et ``embed`` (refus explicite)."""

    async def test_the_chat_completion_still_stubs_offline(self) -> None:
        from app.llm.router.model_router import LLMTask

        response = await _router().complete(LLMTask(task_type="classification"), "prompt")

        assert response.stub is True

    async def test_embeddings_refuse_instead_of_stubbing(self) -> None:
        with pytest.raises(InfrastructureError) as excinfo:
            await _router().embed(["petit texte"])

        assert ENV_API_KEY in str(excinfo.value)

    async def test_the_generator_produces_no_record_and_states_it(self) -> None:
        outcome = await generate_embeddings([UNIT], router=_router())

        assert outcome.records == ()
        assert outcome.vector_count == 0
        assert outcome.lineage() is None
        assert any(ENV_API_KEY in line for line in outcome.limitations)
        assert any("aucun vecteur nul" in line for line in outcome.limitations)

    async def test_the_persistence_without_a_database_is_a_stated_constat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
        from app.storage.database.engine import set_default_engine

        set_default_engine(None)
        from app.knowledge.embedding import EmbeddingRecord

        written, limitations = await persist_embeddings(
            [EmbeddingRecord(owner_id="INF_1", vector=(0.1, 0.2), model="m")]
        )

        assert written == 0
        assert any("INIS_DATABASE_URL" in line for line in limitations)


class TestAProviderThatAnswersBadlyIsRefused:
    """§0.2 — une réponse douteuse n'est jamais rangée « au cas où »."""

    async def test_a_missing_vector_count_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_API_KEY, "test-key")
        payload = {"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {}}

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        async with _client(handler) as client:
            with pytest.raises(InfrastructureError):
                await _router().embed(["un", "deux"], dimension=2, client=client)

    async def test_a_wrong_width_is_refused_not_truncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_API_KEY, "test-key")

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload(1, dimension=8))

        async with _client(handler) as client:
            with pytest.raises(InfrastructureError) as excinfo:
                await _router().embed(["texte"], dimension=EMBEDDING_DIMENSION, client=client)

        assert "1536" in str(excinfo.value)

    async def test_an_upstream_error_envelope_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_API_KEY, "test-key")

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"code": 503, "message": "overloaded"}})

        async with _client(handler) as client:
            with pytest.raises(InfrastructureError) as excinfo:
                await _router().embed(["texte"], dimension=2, client=client)

        assert "overloaded" in str(excinfo.value)

    async def test_a_valid_answer_is_parsed_in_input_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_API_KEY, "test-key")
        monkeypatch.setenv(ENV_EMBEDDING_MODEL, "text-embedding-3-large")
        sent: list[dict[str, object]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            import json

            body = json.loads(request.content.decode("utf-8"))
            sent.append(body)
            # The provider answers in reverse order on purpose.
            count = len(body["input"])
            data = [
                {"index": index, "embedding": [float(index)] * 3}
                for index in reversed(range(count))
            ]
            return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 5}})

        async with _client(handler) as client:
            response = await _router().embed(
                ["un", "deux"], dimension=3, client=client, base_url="https://example.test/v1"
            )

        assert response.model == "text-embedding-3-large"
        assert response.vectors == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]
        assert response.input_tokens == 5
        assert sent[0]["model"] == "text-embedding-3-large"

    async def test_the_batch_is_split_into_several_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_API_KEY, "test-key")
        calls: list[int] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            import json

            body = json.loads(request.content.decode("utf-8"))
            calls.append(len(body["input"]))
            return httpx.Response(200, json=_payload(len(body["input"]), 2))

        async with _client(handler) as client:
            response = await _router().embed(
                ["a", "b", "c"], dimension=2, batch_size=2, client=client
            )

        assert calls == [2, 1]
        assert len(response.vectors) == 3

    @pytest.mark.parametrize("texts", [[], [""], ["   "]])
    async def test_unusable_input_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, texts: list[str]
    ) -> None:
        monkeypatch.setenv(ENV_API_KEY, "test-key")

        with pytest.raises(ValueError):
            await _router().embed(texts)

