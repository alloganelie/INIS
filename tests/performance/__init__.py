"""Load and sizing tests per §41.13.

The benchmarks here answer the §41.13 questions — throughput, concurrency and
search latency — under a *mock* LLM and mock web providers, so they measure the
orchestration INIS owns rather than a third-party API's variance. Thresholds are
deliberately loose: they are regression guards (a change that serialises the
pipeline, leaks state between concurrent runs, or turns a search into a
full-table scan will break them), not performance targets.
"""

