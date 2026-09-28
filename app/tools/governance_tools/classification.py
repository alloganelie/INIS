"""``classify_sensitivity`` internal tool per §21 (§19.4 classification).

The classification itself is delegated to the §19.4
:class:`~app.security.pii.classifier.SensitivityClassifier`; the tool only
flattens the payload to text and re-validates the result against the domain
:class:`~app.domain.entities.security_classification.SecurityClassification`,
so an out-of-scale label can never leave the tool (§0.2).
"""

from __future__ import annotations

from typing import Any, Mapping

from app.core.errors import ValidationError
from app.core.hashing import canonical_json
from app.domain.entities.security_classification import SecurityClassification
from app.security.pii import SensitivityClassifier

__all__ = ["classify_sensitivity"]


def _flatten_text(value: Any, sink: list[str]) -> None:
    """Collect every string leaf of *value* into *sink*."""
    if isinstance(value, str):
        sink.append(value)
    elif isinstance(value, Mapping):
        for child in value.values():
            _flatten_text(child, sink)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            _flatten_text(child, sink)


async def classify_sensitivity(
    data: Mapping[str, Any],
    *,
    classifier: SensitivityClassifier | None = None,
) -> SecurityClassification:
    """Classify *data* sensitivity per §19.4 (§21 signature).

    Args:
        data: Payload to classify; its string leaves are concatenated as
            classification text.
        classifier: Injected classifier; defaults to a fresh
            :class:`SensitivityClassifier`.

    Returns:
        The validated :class:`SecurityClassification` (``sensitivity`` in
        ``low | medium | high | critical``, PII flag and categories).

    Raises:
        ValidationError: If *data* is not a non-empty mapping.
    """
    if not isinstance(data, Mapping) or not data:
        raise ValidationError("data must be a non-empty mapping to classify (§19.4)")

    leaves: list[str] = []
    _flatten_text(data, leaves)
    text = " ".join(leaves).strip() or canonical_json(data)

    active = classifier if classifier is not None else SensitivityClassifier()
    result = active.classify(text)
    return SecurityClassification(
        sensitivity=result["sensitivity"],
        pii=bool(result.get("pii", False)),
        categories=list(result.get("categories", [])),
    )
