"""In-memory lineage graph for INIS transformations."""


class LineageTracker:
    """Record resource transformations and retrieve transitive lineage."""

    def __init__(self) -> None:
        self._transformations: dict[str, dict[str, tuple[str, ...]]] = {}
        self._parents: dict[str, set[str]] = {}
        self._children: dict[str, set[str]] = {}

    def record(
        self,
        transformation_id: str,
        input_ids: list[str],
        output_ids: list[str],
    ) -> None:
        """Record links from each input resource to each output resource."""
        self._transformations[transformation_id] = {
            "input_ids": tuple(input_ids),
            "output_ids": tuple(output_ids),
        }
        for input_id in input_ids:
            self._children.setdefault(input_id, set()).update(output_ids)
        for output_id in output_ids:
            self._parents.setdefault(output_id, set()).update(input_ids)

    def get_lineage(self, resource_id: str) -> dict[str, list[str]]:
        """Return all upstream ancestry and downstream descendants of a resource."""
        return {
            "ancestry": sorted(self._reachable(resource_id, self._parents)),
            "descendants": sorted(self._reachable(resource_id, self._children)),
        }

    @staticmethod
    def _reachable(resource_id: str, links: dict[str, set[str]]) -> set[str]:
        """Traverse graph links without looping when transformations form a cycle."""
        discovered: set[str] = set()
        pending = list(links.get(resource_id, set()))
        while pending:
            candidate = pending.pop()
            if candidate in discovered or candidate == resource_id:
                continue
            discovered.add(candidate)
            pending.extend(links.get(candidate, set()))
        return discovered
