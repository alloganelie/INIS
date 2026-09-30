"""PDF export of a §24 delivery — explicitly unavailable in the V1 stack.

§4.1 fixes the V1 dependency set, and it contains no PDF *writer*: ``pypdf`` and
``pdfplumber`` read PDFs, they do not compose them. §37 forbids inventing a
capability, so this module *refuses* to produce a ``.pdf`` and states why,
instead of emitting an empty or malformed file that would look like a delivery.

Decision recorded for the plan: option B (ADR + a new dependency) is the only
way to lift this refusal; until that ADR exists, ``pdf`` stays an explicitly
unsupported ``OutputFormat`` value, and the delivery names the closest format it
did produce (§25.2 transparent failure).
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ValidationError

__all__ = ["PDF_AVAILABLE", "PDF_UNAVAILABLE_REASON", "generate_pdf", "pdf_supported"]

#: ``False`` until an ADR adds a PDF writer to §4.1 — see module docstring.
PDF_AVAILABLE = False

#: Why a ``.pdf`` cannot be delivered today (surfaced in ``limitations``).
PDF_UNAVAILABLE_REASON = (
    "Format PDF non supporté par la stack V1 (§4.1 : aucune bibliothèque "
    "d'écriture PDF) — aucun fichier PDF n'est généré, la livraison reste "
    "disponible en CSV, JSON, XML ou XLSX."
)


def pdf_supported() -> bool:
    """Return whether this stack can produce a PDF (always ``False`` in V1)."""
    return PDF_AVAILABLE


def generate_pdf(payload: Any) -> bytes:
    """Refuse to produce a PDF (§4.1, §37).

    Args:
        payload: Unused; accepted so the generator registry has one signature.

    Returns:
        Nothing — the call always raises.

    Raises:
        ValidationError: Always, carrying :data:`PDF_UNAVAILABLE_REASON`.
    """
    raise ValidationError(PDF_UNAVAILABLE_REASON)
