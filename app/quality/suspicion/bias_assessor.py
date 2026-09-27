"""Editorial bias assessment (§41.7).

``editorial_bias_score`` is a float in ``[0, 1]`` combining:

* the **contradiction rate** — the share of this source's claims that other,
  independent sources contradict (systematic one-sidedness), and
* the **lexical one-sidedness** — absolutist wording versus hedging wording.

Pure functions over injected counts, so thresholds are unit-testable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

#: Score at or above which a source is considered systematically biased.
BIAS_THRESHOLD = 0.5

#: Unqualified, absolute claims typical of one-sided editorializing.
_ABSOLUTIST: frozenset[str] = frozenset(
    {
        "always",
        "never",
        "every",
        "nobody",
        "nothing",
        "totally",
        "completely",
        "entirely",
        "certainly",
        "definitely",
        "obviously",
        "toujours",
        "jamais",
        "tous",
        "toutes",
        "aucun",
        "aucune",
        "totalement",
        "complètement",
        "certainement",
        "évidemment",
        "sans aucun doute",
    }
)

#: Hedged, qualified wording typical of balanced reporting.
_HEDGED: frozenset[str] = frozenset(
    {
        "may",
        "might",
        "perhaps",
        "sometimes",
        "reportedly",
        "according",
        "could",
        "likely",
        "peut",
        "parfois",
        "selon",
        "probablement",
        "semble",
        "apparemment",
        "possible",
        "possiblement",
    }
)

_WORD = re.compile(r"\w+", re.UNICODE)


def _count_hits(text: str, lexicon: frozenset[str]) -> int:
    words = _WORD.findall(text.casefold())
    return sum(1 for word in words if word in lexicon)


def lexical_one_sidedness(texts: Sequence[str]) -> float:
    """Return absolutist-word share of all stance markers in ``[0, 1]``.

    Returns ``0.0`` when no stance marker of either kind appears.
    """
    absolutist = sum(_count_hits(t, _ABSOLUTIST) for t in texts)
    hedged = sum(_count_hits(t, _HEDGED) for t in texts)
    total = absolutist + hedged
    if total == 0:
        return 0.0
    return absolutist / total


def assess_editorial_bias(
    texts: Sequence[str],
    *,
    contradicted_claims: int = 0,
    total_claims: int | None = None,
) -> float:
    """Return the §41.7 ``editorial_bias_score`` in ``[0, 1]``.

    Args:
        texts: the source's recent contents (its editorial voice).
        contradicted_claims: how many of its claims other sources contradict.
        total_claims: denominator for the contradiction rate; defaults to
            ``max(len(texts), contradicted_claims)``.
    """
    if contradicted_claims < 0:
        raise ValueError("contradicted_claims must be >= 0")
    denominator = total_claims if total_claims is not None else max(len(texts), contradicted_claims, 1)
    if denominator < 1:
        raise ValueError("total_claims must be >= 1")
    if contradicted_claims > denominator:
        raise ValueError("contradicted_claims cannot exceed total_claims")

    contradiction_rate = contradicted_claims / denominator
    one_sidedness = lexical_one_sidedness(texts)
    score = 0.5 * contradiction_rate + 0.5 * one_sidedness
    return max(0.0, min(1.0, score))
