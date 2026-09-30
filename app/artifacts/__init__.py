"""§24 delivery artifacts — turning a delivery into files a client can download.

The package has three responsibilities, one per sub-package:

* :mod:`app.artifacts.generators` turns a delivery payload into the *bytes* of a
  file (CSV, JSON, XML, XLSX) and refuses, explicitly, a format the V1 stack
  cannot produce honestly (PDF, §4.1/§37);
* :mod:`app.artifacts.packager` allocates the §24.2 ``ART_{YYYY}_{SEQ6}``
  identifier — which is *not* a ULID — and builds the
  :class:`~app.domain.entities.artifact.Artifact` record of one delivered file;
* :mod:`app.artifacts.delivery` is the pipeline-facing entry point: given a
  request's ``required_output`` and the material a run produced, it returns the
  §24.2 records to publish in the §24.1 ``artifacts`` field.

Nothing here owns domain rules (they live in :mod:`app.domain`) nor SQL (it
lives in :mod:`app.storage`, CODING_RULES §2).
"""

from __future__ import annotations
