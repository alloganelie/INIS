"""Resolution of step dependencies with topological sorting and cycle detection."""

from collections import defaultdict, deque
from typing import Any


class DependencyResolver:
    """Resolve execution order based on step dependencies (§8.2)."""

    def resolve(self, steps: list[dict[str, Any]]) -> list[str]:
        """Return topologically sorted step IDs respecting depends_on constraints.

        Args:
            steps: List of step dictionaries with step_id and depends_on fields.

        Returns:
            List of step IDs in execution order.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        # Build dependency graph
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        step_ids = {step["step_id"] for step in steps}

        for step in steps:
            step_id = step["step_id"]
            dependencies = step.get("depends_on", [])
            
            # Initialize in-degree for all steps
            if step_id not in in_degree:
                in_degree[step_id] = 0
            
            for dep_id in dependencies:
                if dep_id not in step_ids:
                    continue  # Skip dependencies that don't exist in current steps
                graph[dep_id].append(step_id)
                in_degree[step_id] += 1

        # Kahn's algorithm for topological sort
        queue = deque([step_id for step_id in step_ids if in_degree[step_id] == 0])
        execution_order = []

        while queue:
            step_id = queue.popleft()
            execution_order.append(step_id)

            for dependent in graph[step_id]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Check for cycles
        if len(execution_order) != len(step_ids):
            cycle = self._detect_cycle(steps)
            raise ValueError(f"Circular dependency detected: {cycle}")

        return execution_order

    def _detect_cycle(self, steps: list[dict[str, Any]]) -> list[str]:
        """Detect and return a cycle in the dependency graph for error reporting."""
        step_map = {step["step_id"]: step for step in steps}
        visited = set()
        rec_stack = set()
        cycle_path = []

        def dfs(step_id: str, path: list[str]) -> bool:
            if step_id in rec_stack:
                cycle_path.extend(path + [step_id])
                return True
            if step_id in visited:
                return False

            visited.add(step_id)
            rec_stack.add(step_id)
            path.append(step_id)

            step = step_map.get(step_id, {})
            for dep_id in step.get("depends_on", []):
                if dfs(dep_id, path):
                    return True

            rec_stack.remove(step_id)
            path.pop()
            return False

        for step in steps:
            if dfs(step["step_id"], []):
                break

        return cycle_path

    def get_executable_steps(
        self, steps: list[dict[str, Any]], completed_step_ids: set[str]
    ) -> list[str]:
        """Return step IDs whose dependencies are all completed.

        Args:
            steps: All steps in the plan.
            completed_step_ids: Set of step IDs that have completed successfully.

        Returns:
            List of step IDs ready for execution.
        """
        executable = []
        for step in steps:
            step_id = step["step_id"]
            if step_id in completed_step_ids:
                continue
            
            dependencies = step.get("depends_on", [])
            if all(dep_id in completed_step_ids for dep_id in dependencies):
                executable.append(step_id)

        return executable
