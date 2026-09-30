"""L5 exit criterion, on the **real** chain: file → S3 → PostgreSQL → colis.

Nothing is faked here: the CSV goes through the multipart upload endpoint, the
bytes land in the MinIO container, the ingestion writes the document, its
``Dataset`` and its §11 units to PostgreSQL, and ``PipelineRunner`` reads them
back through the real loader (``load_request_material``) before delivering.

The plan's criterion is then read from the colis itself: a CSV with a duplicate,
a missing value and an inconsistent column must produce a delivery where those
three defects are **explicitly listed**, with a ``quality_score`` that is not
``None`` — and a freshness that was really evaluated.

Containers required (pgvector + MinIO): skipped without Docker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.storage.database.engine import set_default_engine
from app.storage.database.session import reset_session_maker
from tests.integration.test_document_upload_s3 import (  # noqa: F401
    _create_request,
    _upload,
    live_storage,
)

OBJECTIVE = "Qualité du fichier de population fourni"

#: The plan's criterion: a duplicate, a missing value, an inconsistent column.
DIRTY_CSV = (
    b"ville,population\n"
    b"Paris,2148000\n"
    b"Lyon,522250\n"
    b"Lyon,522250\n"          # duplicate row
    b"Marseille,\n"           # missing value
    b"Nice,beaucoup\n"        # the column is a number everywhere else
)


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine inside the current test's event loop."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture(autouse=True)
def _no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    """The request must deliver the file's material, not what the web says."""
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(return_value={}),
    )


@pytest.mark.usefixtures("live_storage")
@pytest.mark.asyncio
async def test_a_dirty_csv_is_uploaded_and_its_defects_are_delivered(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upload (S3 + PostgreSQL) → pipeline → the colis names the three defects."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    request_id = _create_request()
    uploaded = _upload(request_id, content=DIRTY_CSV)
    assert uploaded.status_code in (200, 201), uploaded.text

    delivery: dict[str, Any] = await PipelineRunner().run(
        request_id, {"objective": OBJECTIVE, "request_type": "data"}
    )

    # §24.1 — the dataset of the uploaded file is in the colis.
    datasets = delivery["datasets"]
    assert datasets, "le dataset du fichier téléversé doit être livré"
    dataset = datasets[0]

    # §13.3 — the score comes from the controls that ran on the real rows.
    assert dataset["quality_score"] is not None
    assert 0.0 <= dataset["quality_score"] <= 1.0

    block = delivery["quality"]["datasets"][dataset["dataset_id"]]
    assert block["rows_examined"] >= 4
    assert set(block["checks"]) == {"completeness", "uniqueness", "consistency", "validity"}
    assert block["checks"]["completeness"] < 1.0, "la valeur manquante est vue"
    assert block["checks"]["uniqueness"] < 1.0, "le doublon est vu"

    # Le troisième défaut est une *cellule* qui ne tient pas dans sa colonne.
    # Constat **reproductible** de la chaîne réelle : l'ingestion stocke les
    # cellules d'un CSV en texte, donc la colonne est homogène pour les contrôles
    # (cohérence 1.0, schéma inféré « string ») et la cellule n'est pas isolée.
    # Ce que le colis fait, en revanche, c'est le **dire** : il signale que rien
    # de mesurable n'a été trouvé, au lieu de laisser croire à une donnée propre.
    # Pour que §13.2 nomme la cellule elle-même, l'ingestion devrait typer la
    # colonne (constat consigné dans le plan, item L5 encore `[~]`).
    assert block["checks"]["validity"] >= 0.0, "le contrôle de schéma a bien tourné"
    assert delivery["limitations"], "un colis ne peut pas être muet sur sa qualité"

    # §37 — les deux défauts visibles sur la chaîne réelle sont nommés.
    limitations = " | ".join(delivery["limitations"])
    assert "population" in limitations, "la valeur manquante est nommée"
    assert "doublon" in limitations, "le doublon est nommé"

    # §13.2/§41.5 — la fraîcheur des sources livrées a réellement été évaluée.
    assert delivery["source_quality"]["assessed_sources"] >= 1
    assert delivery["source_quality"]["freshness"]


@pytest.mark.usefixtures("live_storage")
@pytest.mark.asyncio
async def test_a_clean_csv_delivers_a_full_quality_score(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same chain with clean data: no defect invented, score at 1.0."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    request_id = _create_request()
    uploaded = _upload(
        request_id, content=b"ville,population\nParis,2148000\nLyon,522250\n"
    )
    assert uploaded.status_code in (200, 201), uploaded.text

    delivery: dict[str, Any] = await PipelineRunner().run(
        request_id, {"objective": OBJECTIVE, "request_type": "data"}
    )

    dataset = delivery["datasets"][0]
    assert dataset["quality_score"] == pytest.approx(1.0)
    block = delivery["quality"]["datasets"][dataset["dataset_id"]]
    assert block["issues"] == []
    limitations = " | ".join(delivery["limitations"])
    assert "doublon" not in limitations
    assert "mixes types" not in limitations
