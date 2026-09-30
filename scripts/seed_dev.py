"""Peuple la base de données avec un jeu de données de développement (§27, §36).

Usage :
    python scripts/seed_dev.py [database_url]
    # Si database_url n'est pas fourni, lit INIS_DATABASE_URL ou DATABASE_URL.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.value_objects.ulid import ULID  # noqa: E402
from app.storage.database.engine import create_engine  # noqa: E402


async def seed(database_url: str) -> None:
    print(f"Connexion à {database_url}...")
    engine = create_engine(database_url)
    now = datetime.now(timezone.utc)

    async with engine.begin() as conn:
        # 1. Agents (§6)
        print("  - Enregistrement des agents par défaut...")
        await conn.execute(
            text(
                """
                INSERT INTO agents (agent_id, name, description, version, status, protocols, capabilities, health, registered_at, last_seen_at)
                VALUES
                    ('AGT_01H00000000000000000000001', 'INIS Core Orchestrator', 'Primary intelligence pipeline runner', '2.0.0', 'active', CAST(:protocols AS JSONB), CAST(:caps AS JSONB), CAST(:health AS JSONB), :now, :now),
                    ('AGT_01H00000000000000000000002', 'Web Harvester Agent', 'Specialized web search and extraction agent', '1.0.0', 'active', CAST(:protocols AS JSONB), CAST(:caps AS JSONB), CAST(:health AS JSONB), :now, :now)
                ON CONFLICT (agent_id) DO NOTHING
                """
            ),
            {
                "protocols": json.dumps(["v1.0"]),
                "caps": json.dumps(["web_search", "synthesis"]),
                "health": json.dumps({"status": "healthy"}),
                "now": now,
            },
        )

        # 2. Sources (§9)
        print("  - Ajout des sources de test...")
        source_id_1 = "SRC_01H00000000000000000000001"
        source_id_2 = "SRC_01H00000000000000000000002"
        await conn.execute(
            text(
                """
                INSERT INTO sources (id, url, source_type, reliability_score, freshness, data_stage, name, description, trust_level, status, created_at, updated_at)
                VALUES
                    (:src1, 'https://fr.wikipedia.org/wiki/Porto-Novo', 'web', 0.95, CAST(:fresh AS JSONB), 'raw', 'Wikipedia - Porto-Novo', 'Article encyclopédique sur la capitale du Bénin', 0.95, 'active', :now, :now),
                    (:src2, 'https://gouv.bj', 'web', 0.98, CAST(:fresh AS JSONB), 'raw', 'Gouvernement du Bénin', 'Portail officiel du gouvernement béninois', 0.98, 'active', :now, :now)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "src1": source_id_1,
                "src2": source_id_2,
                "fresh": json.dumps({"retrieved_at": now.isoformat()}),
                "now": now,
            },
        )

        # 3. Information Units (§11)
        print("  - Ajout des unités d'information vérifiées...")
        unit_id = "INF_01H00000000000000000000001"
        await conn.execute(
            text(
                """
                INSERT INTO information_units (
                    id, type, content, source_id, document_id, data_stage,
                    raw_reference, context, language, epistemic_status, provenance,
                    created_at, updated_at
                )
                VALUES (
                    :id, 'text', CAST(:content AS JSONB), :src, NULL, 'derived',
                    CAST(:raw_ref AS JSONB), CAST(:ctx AS JSONB), 'fr', 'factual', CAST(:prov AS JSONB),
                    :now, :now
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": unit_id,
                "content": json.dumps({"text": "Porto-Novo est la capitale officielle de la République du Bénin."}),
                "src": source_id_1,
                "raw_ref": json.dumps({"url": "https://fr.wikipedia.org/wiki/Porto-Novo"}),
                "ctx": json.dumps({"topic": "geography"}),
                "prov": json.dumps({"extractor": "FactExtractor"}),
                "now": now,
            },
        )

        # 4. Evidence (§14.2)
        print("  - Ajout des preuves associées...")
        evid_id = "EVID_01H00000000000000000000001"
        await conn.execute(
            text(
                """
                INSERT INTO evidence (
                    evidence_id, information_id, source_id, document_id, quote,
                    confidence, strength, epistemic_status, provenance, created_at
                )
                VALUES (
                    :id, :inf_id, :src, NULL, 'Porto-Novo est la capitale officielle du Bénin',
                    0.95, 0.95, 'fact', CAST(:prov AS JSONB), :now
                )
                ON CONFLICT (evidence_id) DO NOTHING
                """
            ),
            {
                "id": evid_id,
                "inf_id": unit_id,
                "src": source_id_1,
                "prov": json.dumps({"source": "wikipedia"}),
                "now": now,
            },
        )

    await engine.dispose()
    print("Seed terminé avec succès.")


def main() -> int:
    db_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("INIS_DATABASE_URL") or os.getenv("DATABASE_URL")
    )
    if not db_url:
        print("Erreur: Aucune URL de base fournie (INIS_DATABASE_URL non défini).", file=sys.stderr)
        return 1
    # Forcer asyncpg si format standard
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    asyncio.run(seed(db_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())

