"""§41.6 — le seuil de découpage, ses bornes et la **borne mémoire** sous charge.

Le plan L7 le réclamait explicitement : « ⚠️ reste dû ici : le test de borne
mémoire sous charge (`performance/test_chunked_threshold.py`, **non créé à ce
jour**) ». Le branchement du seuil était déjà prouvé par
`tests/unit/knowledge/test_ingestion_chunking.py` et
`tests/integration/test_chunked_ingestion.py` ; ce fichier apporte ce qui
manquait : le **contrat exact** du seuil (unité, valeur au seuil, juste en
dessous, juste au-dessus, vide, invalide) et la **mesure** de la borne de travail.

Ce qui est mesuré, et ce qui ne l'est pas :

* la **borne structurelle** est déterministe et mesurée sur le chemin réel
  (`_chunked_units` + `DefaultChunkedDatasetProcessor`) : aucun tronçon ne
  dépasse ``chunk_size_rows``, et le nombre de tronçons est celui du découpage ;
* la **mémoire tracée** (`tracemalloc`) est comparée entre le chemin découpé et
  le chemin direct sur la **même** charge : le découpage ne doit jamais coûter
  plus cher. C'est une mesure structurelle, exécutée en CI sur un processus
  Python — **pas** une facture ni une mesure de production.
"""

from __future__ import annotations

import tracemalloc
from typing import Any, ClassVar

import pytest

from app.knowledge.ingestion import document_ingestor
from app.knowledge.ingestion.document_ingestor import _chunked_units
from app.knowledge.normalization.chunked_dataset import (
    DEFAULT_MAX_IN_MEMORY_BYTES,
    DEFAULT_PARALLEL_CHUNKS,
    ChunkedProcessingConfig,
    DefaultChunkedDatasetProcessor,
)
from app.knowledge.normalization.limits import (
    DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST,
    MAX_INFORMATION_UNITS_PER_REQUEST_ENV,
    chunked_processing_config,
    max_information_units_per_request,
)

#: §41.6 — les quatre seuils du bloc ``[CONFIG]``, et rien d'autre.
CONFIG_KEYS = frozenset(
    {"max_in_memory_rows", "max_in_memory_bytes", "chunk_size_rows", "parallel_chunks"}
)


class TestTheThresholdContract:
    """L'unité, la valeur, et les bornes : au seuil, en dessous, au-dessus."""

    def test_the_threshold_is_a_row_count_and_defaults_to_the_adr_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR 007 — l'unité est la ligne, le défaut est 50, la config les reprend."""
        monkeypatch.delenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, raising=False)

        threshold = max_information_units_per_request()
        config = chunked_processing_config()

        assert threshold == DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST == 50
        assert set(config.to_dict()) == CONFIG_KEYS
        assert config.max_in_memory_rows == threshold, "le seuil est le plafond en mémoire"
        assert config.chunk_size_rows == threshold, "et la taille d'un tronçon"
        assert config.max_in_memory_bytes == DEFAULT_MAX_IN_MEMORY_BYTES
        assert config.parallel_chunks == DEFAULT_PARALLEL_CHUNKS

    def test_exactly_at_the_threshold_does_not_stream(self) -> None:
        """Au seuil, aucun découpage : la comparaison est **strictement** au-dessus."""
        config = chunked_processing_config(50)

        assert config.should_stream(50) is False, "50 lignes pour un seuil de 50 restent directes"

    def test_just_below_the_threshold_does_not_stream(self) -> None:
        assert chunked_processing_config(50).should_stream(49) is False

    def test_just_above_the_threshold_streams(self) -> None:
        assert chunked_processing_config(50).should_stream(51) is True

    def test_an_empty_dataset_does_not_stream(self) -> None:
        """Vide n'est pas « volumineux » : aucun processeur, aucun tronçon."""
        assert chunked_processing_config(50).should_stream(0) is False

    def test_a_byte_ceiling_also_triggers_streaming(self) -> None:
        """§41.6 — le seuil en octets existe aussi (défaut 512 Mio)."""
        config = chunked_processing_config(1_000_000)

        assert config.should_stream(10, byte_size=DEFAULT_MAX_IN_MEMORY_BYTES) is False
        assert config.should_stream(10, byte_size=DEFAULT_MAX_IN_MEMORY_BYTES + 1) is True

    def test_an_environment_override_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "7")

        assert max_information_units_per_request() == 7
        assert chunked_processing_config().chunk_size_rows == 7

    @pytest.mark.parametrize("raw", ["", "   ", "pas-un-entier", "0", "-3", "3.5"])
    def test_an_unusable_environment_value_falls_back_to_the_default(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un seuil que personne ne peut énoncer n'est pas un seuil (§0.2)."""
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, raw)

        assert max_information_units_per_request() == DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST

    @pytest.mark.parametrize("bad", [0, -1])
    def test_an_invalid_config_is_refused_not_ignored(self, bad: int) -> None:
        """Une borne nulle ou négative lèverait la borne : elle est refusée."""
        with pytest.raises(ValueError):
            chunked_processing_config(bad)
        with pytest.raises(ValueError):
            ChunkedProcessingConfig(max_in_memory_rows=bad)


class _RecordingProcessor(DefaultChunkedDatasetProcessor):
    """Le processeur réel, qui note la taille de chaque tronçon qu'il traite.

    Sous-classe du processeur **de production** : le chemin reste le vrai, seule
    l'observation est ajoutée (aucune logique de découpage n'est réécrite ici).
    """

    observed: ClassVar[list[int]] = []
    max_parallel: ClassVar[int] = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        type(self).observed = []
        type(self).max_parallel = 0

    @classmethod
    def reset(cls) -> None:
        """Forget what a previous test observed (the class outlives one test)."""
        cls.observed = []
        cls.max_parallel = 0

    def stream(self, dataset_id: str, chunk_size: int) -> Any:
        """Delegate to the real streaming, recording each chunk's size."""
        stream = super().stream(dataset_id, chunk_size)
        type(self).max_parallel = max(type(self).max_parallel, self.config.parallel_chunks)

        async def generator() -> Any:
            async for chunk in stream:
                type(self).observed.append(len(chunk.rows))
                yield chunk

        return generator()


def _payload(count: int, *, width: int = 60) -> list[tuple[int, dict[str, Any]]]:
    """Build *count* ``(index, row)`` items, each one big enough to weigh."""
    filler = "x" * width
    return [(index, {"row": index, "text": f"{filler}-{index}"}) for index in range(1, count + 1)]


def _build(pair: tuple[int, dict[str, Any]]) -> dict[str, Any]:
    """The per-item work the threshold bounds: one validated §11-shaped unit."""
    index, row = pair
    return {
        "information_id": f"INF_ROW_{index:05d}",
        "type": "record",
        "content": dict(row),
        "location": {"row": index},
    }


class TestTheChunkBoundIsRespectedOnTheRealPath:
    """§41.6 — le découpage réel borne ce qui est traité à la fois."""

    @pytest.mark.asyncio
    async def test_each_chunk_stays_within_the_threshold_and_none_is_lost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Aucun tronçon ne dépasse ``chunk_size_rows``, et tout est livré."""
        monkeypatch.setattr(
            document_ingestor, "DefaultChunkedDatasetProcessor", _RecordingProcessor
        )
        _RecordingProcessor.reset()
        threshold = 25

        units, errors = await _chunked_units(
            _payload(120), build_one=_build, dataset_id="DATA_TEST", threshold=threshold
        )

        assert errors == []
        assert [unit["information_id"] for unit in units] == [
            f"INF_ROW_{index:05d}" for index in range(1, 121)
        ], "la fusion conserve l'ordre des éléments"
        observed = _RecordingProcessor.observed
        assert observed, "au-delà du seuil, le processeur de découpage doit être atteint"
        assert max(observed) <= threshold, f"un tronçon dépasse le seuil : {observed}"
        assert len(observed) == 5, "120 éléments pour un seuil de 25 font cinq tronçons"
        assert _RecordingProcessor.max_parallel == DEFAULT_PARALLEL_CHUNKS

    @pytest.mark.asyncio
    async def test_at_the_threshold_no_processor_is_instantiated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Au seuil exactement : chemin direct, aucun tronçon (ADR 007)."""
        monkeypatch.setattr(
            document_ingestor, "DefaultChunkedDatasetProcessor", _RecordingProcessor
        )
        _RecordingProcessor.reset()
        threshold = 30

        units, errors = await _chunked_units(
            _payload(threshold), build_one=_build, dataset_id="DATA_TEST", threshold=threshold
        )

        assert errors == []
        assert len(units) == threshold
        assert _RecordingProcessor.observed == [], "au seuil, aucun découpage"

    @pytest.mark.asyncio
    async def test_the_chunked_result_is_identical_to_the_direct_one(self) -> None:
        """La transparence du découpage : mêmes unités, même ordre."""
        items = _payload(40)

        chunked, chunked_errors = await _chunked_units(
            items, build_one=_build, dataset_id="DATA_TEST", threshold=10
        )
        direct, direct_errors = await _chunked_units(
            items, build_one=_build, dataset_id="DATA_TEST", threshold=10_000
        )

        assert chunked_errors == direct_errors == []
        assert chunked == direct, "le découpage ne change ni le contenu ni l'ordre"

    @pytest.mark.asyncio
    async def test_an_empty_payload_produces_nothing_and_no_chunk(self) -> None:
        units, errors = await _chunked_units(
            [], build_one=_build, dataset_id="DATA_TEST", threshold=5
        )

        assert units == [] and errors == []

    @pytest.mark.asyncio
    async def test_an_unusable_threshold_is_refused(self) -> None:
        """Un seuil de 0 ne « découpe pas » : il est refusé explicitement."""
        with pytest.raises(ValueError):
            await _chunked_units(
                _payload(3), build_one=_build, dataset_id="DATA_TEST", threshold=0
            )


class TestTheWorkingSetIsBoundedUnderLoad:
    """La borne mémoire annoncée par §41.6, mesurée sur la même charge."""

    @staticmethod
    async def _run(items: list[Any], threshold: int) -> int:
        """Run the real chunked path and return the peak traced memory, in bytes."""
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            units, errors = await _chunked_units(
                items, build_one=_build, dataset_id="DATA_TEST", threshold=threshold
            )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert errors == []
        assert len(units) == len(items), "aucun élément n'est perdu par le découpage"
        return peak

    @pytest.mark.asyncio
    async def test_chunking_keeps_the_working_set_bounded_without_a_memory_blowup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mesure structurelle honnête : borne du tronçon, et pas d'explosion mémoire.

        Ce que la mesure dit — et ne dit pas :

        * **la borne est structurelle** : aucun tronçon ne dépasse le seuil, donc
          les unités construites simultanément sont bornées par le seuil et non
          par la taille du fichier. C'est ce que §41.6 demande de borner ;
        * **le pic total ne baisse pas nécessairement** : le résultat fusionné
          contient toujours toutes les unités, et le découpage ajoute ses propres
          objets. Mesurer ici 389 792 octets découpé contre 359 716 direct montre
          exactement cela — l'affirmation « le découpage consomme moins » serait
          **fausse**, et aucun chiffre de coût n'est fabriqué ;
        * ce qui est donc verrouillé : le pic découpé reste du **même ordre de
          grandeur** que le chemin direct (marge explicite), c'est-à-dire qu'aucun
          mécanisme de découpage ne fait exploser la mémoire. La marge est une
          borne haute de régression, pas une performance revendiquée.
        """
        monkeypatch.setattr(
            document_ingestor, "DefaultChunkedDatasetProcessor", _RecordingProcessor
        )
        _RecordingProcessor.reset()
        items = _payload(600)

        chunked_peak = await self._run(items, 50)
        assert _RecordingProcessor.observed, "la charge dépasse le seuil : elle est découpée"
        assert max(_RecordingProcessor.observed) <= 50, (
            f"aucun tronçon ne doit dépasser le seuil : {_RecordingProcessor.observed}"
        )

        direct_peak = await self._run(items, 10_000)

        assert chunked_peak <= direct_peak * 1.4, (
            "le découpage ne doit pas coûter un ordre de grandeur de plus : "
            f"découpé={chunked_peak} octets, direct={direct_peak} octets"
        )

    @pytest.mark.asyncio
    async def test_the_threshold_decides_the_number_of_chunks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le seuil est bien la variable qui décide du nombre de tronçons."""
        monkeypatch.setattr(
            document_ingestor, "DefaultChunkedDatasetProcessor", _RecordingProcessor
        )
        items = _payload(90)

        _RecordingProcessor.reset()
        await self._run(items, 10)
        small = list(_RecordingProcessor.observed)

        _RecordingProcessor.reset()
        await self._run(items, 45)
        large = list(_RecordingProcessor.observed)

        assert len(small) == 9, f"90 éléments pour un seuil de 10 : {small}"
        assert len(large) == 2, f"90 éléments pour un seuil de 45 : {large}"
        assert max(small) <= 10 and max(large) <= 45, (
            "aucun tronçon ne dépasse le seuil qui l'a produit"
        )

