"""Constants shared by INIS domain foundations."""

from typing import Final


ULID_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "REQ_",
        "MSG_",
        "CORR_",
        "INF_",
        "SRC_",
        "DOC_",
        "DATA_",
        "EVID_",
        "CLM_",
        "CONFLICT_",
        "TRF_",
        "AUD_",
    }
)

DATA_STAGES: Final[tuple[str, ...]] = ("raw", "normalized", "enriched", "derived")
