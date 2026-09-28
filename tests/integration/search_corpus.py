"""Seed helpers for the §16 search integration tests.

The §16 tests need rows in ``sources``, ``information_units`` (with a
``search_vector``) and ``embeddings``. The corpus is inserted with
``ON CONFLICT DO NOTHING`` and deterministic identifiers, so every test module
can seed independently without disturbing the others.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app.storage.database.engine import create_engine

#: Stable identifiers of the seeded corpus (ULID-shaped, deterministic).
SOURCE_ID = "SRC_01HZZZZZZZZZZZZZZZZZZZZZZZ"
UNIT_SEMANTIC = "INF_01HZZZZZZZZZZZZZZZZZZZZZZA"
UNIT_LEXICAL = "INF_01HZZZZZZZZZZZZZZZZZZZZZZB"
UNIT_ISOLATED = "INF_01HZZZZZZZZZZZZZZZZZZZZZZC"

#: Dimension of the §16.1 embeddings (the migrated column is ``vector(1536)``).
DIMENSION = 1536


def _vector(hot_index: int) -> str:
    """Return a unit vector with a single non-zero component."""
    values = [0.0] * DIMENSION
    values[hot_index] = 1.0
    return "[" + ",".join(map(str, values)) + "]"


SEMANTIC_VECTOR = _vector(0)
ORTHOGONAL_VECTOR = _vector(1)

#: Text of each unit, chosen so exactly one matches the lexical query.
SEMANTIC_TEXT = "unrelated wording about astronomy and telescopes"
LEXICAL_TEXT = "Paris is the capital of France and its largest city"
ISOLATED_TEXT = "cooking recipes with seasonal vegetables"


def as_float_list(vector_literal: str) -> list[float]:
    """Convert a ``[a,b,c]`` literal back into a list of floats."""
    return [float(part) for part in vector_literal.strip("[]").split(",")]


async def seed_corpus(db_url: str) -> dict[str, str]:
    """Seed the search corpus and return the identifiers used by the tests."""
    engine = create_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO sources (id, url, source_type, data_stage)
                    VALUES (:id, :url, 'web', 'raw')
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": SOURCE_ID, "url": "https://example.com/corpus"},
            )
            for unit_id, text_value in (
                (UNIT_SEMANTIC, SEMANTIC_TEXT),
                (UNIT_LEXICAL, LEXICAL_TEXT),
                (UNIT_ISOLATED, ISOLATED_TEXT),
            ):
                await conn.execute(
                    text(
                        """
                        INSERT INTO information_units
                            (id, type, content, source_id, data_stage, search_vector)
                        VALUES (
                            :id, 'text', CAST(:content AS JSONB), :source_id, 'derived',
                            to_tsvector('english', :text)
                        )
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {
                        "id": unit_id,
                        "content": json.dumps({"text": text_value}),
                        "source_id": SOURCE_ID,
                        "text": text_value,
                    },
                )
            # ``embeddings.embedding_id`` is a UUID, so the deterministic value is
            # derived from the owner id: re-seeding replaces instead of duplicating.
            await conn.execute(
                text(
                    """
                    DELETE FROM embeddings
                    WHERE owner_type = 'information_unit' AND owner_id = ANY(:owner_ids)
                    """
                ),
                {"owner_ids": [UNIT_SEMANTIC, UNIT_LEXICAL]},
            )
            for unit_id, vector in (
                (UNIT_SEMANTIC, SEMANTIC_VECTOR),
                (UNIT_LEXICAL, ORTHOGONAL_VECTOR),
            ):
                await conn.execute(
                    text(
                        """
                        INSERT INTO embeddings
                            (embedding_id, owner_type, owner_id, model, vector)
                        VALUES (
                            CAST(md5(:owner_id) AS uuid), 'information_unit', :owner_id,
                            'test-model', CAST(:vector AS vector)
                        )
                        ON CONFLICT (embedding_id) DO NOTHING
                        """
                    ),
                    {"owner_id": unit_id, "vector": vector},
                )
    finally:
        await engine.dispose()
    return {
        "source_id": SOURCE_ID,
        "semantic_unit": UNIT_SEMANTIC,
        "lexical_unit": UNIT_LEXICAL,
        "isolated_unit": UNIT_ISOLATED,
        "semantic_vector": SEMANTIC_VECTOR,
        "orthogonal_vector": ORTHOGONAL_VECTOR,
    }
