"""Le seul point de lecture de l'horloge UTC de la plateforme (§27, §0.2).

Avant ce module, chaque zone lisait l'horloge pour son compte
(``utc_now()``, ``utc_now()``, et cinq petits helpers
``_utc_now`` locaux) : les instants persistés, les TTL, les entrées d'audit et
les marques de provenance étaient corrects, mais la règle n'était écrite nulle
part — une zone pouvait introduire un timestamp **naïf** sans que rien ne le
signale.

``utc_now()`` est désormais ce point unique. Le contrat est minimal et explicite :

* l'instant renvoyé est **timezone-aware** (``tzinfo`` vaut UTC), jamais naïf ;
* c'est le même instant que ``utc_now()``, à la même précision
  (microseconde) : la migration ne change **aucun** comportement temporel.

Ce module ne porte volontairement ni classe, ni configuration, ni format :
centraliser l'horloge ne doit pas devenir une abstraction de plus. Le test
``tests/unit/core/test_time.py`` interdit d'ailleurs la réapparition d'une
lecture directe de l'horloge dans ``app/``.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> datetime:
    """Return the current instant as a timezone-aware UTC ``datetime``.

    Returns:
        ``datetime.now(UTC)`` : la même valeur, la même précision (microseconde),
        le même ``tzinfo``. Jamais naïf.
    """
    return datetime.now(UTC)
