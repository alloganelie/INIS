"""ABAC engine per INIS §19.3."""

from typing import Any, Callable, Dict


class ABACEngine:
    """Attribute-Based Access Control engine."""

    def __init__(self):
        """Initialize ABAC engine."""
        self.condition_evaluators: Dict[str, Callable[[Dict[str, Any]], bool]] = {
            "equals": self._evaluate_equals,
            "not_equals": self._evaluate_not_equals,
            "in": self._evaluate_in,
            "not_in": self._evaluate_not_in,
            "greater_than": self._evaluate_greater_than,
            "less_than": self._evaluate_less_than,
        }

    def evaluate(self, subject: Dict[str, Any], resource: Dict[str, Any],
                 action: str, conditions: Dict[str, Any]) -> bool:
        """Evaluate ABAC conditions for access decision.

        Args:
            subject: Subject attributes (agent_id, roles, etc.)
            resource: Resource attributes (type, classification, owner, etc.)
            action: Action being performed
            conditions: Conditions to evaluate

        Returns:
            True if all conditions are satisfied, False otherwise
        """
        if not conditions:
            return True

        for field, condition in conditions.items():
            if not self._evaluate_condition(subject, resource, field, condition):
                return False

        return True

    def _evaluate_condition(self, subject: Dict[str, Any], resource: Dict[str, Any],
                           field: str, condition: Dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        operator = condition.get("operator", "equals")
        value = condition.get("value")

        context = {**subject, **resource}
        actual_value = self._get_nested_value(context, field)

        if actual_value is None:
            return False

        evaluator = self.condition_evaluators.get(operator)
        if not evaluator:
            return False

        return evaluator(actual_value, value)

    def _get_nested_value(self, data: Dict[str, Any], field: str) -> Any:
        """Get nested value from dictionary using dot notation."""
        keys = field.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None

        return value

    def _evaluate_equals(self, actual: Any, expected: Any) -> bool:
        """Evaluate equals condition."""
        return actual == expected

    def _evaluate_not_equals(self, actual: Any, expected: Any) -> bool:
        """Evaluate not equals condition."""
        return actual != expected

    def _evaluate_in(self, actual: Any, expected: list) -> bool:
        """Evaluate in condition."""
        return actual in expected

    def _evaluate_not_in(self, actual: Any, expected: list) -> bool:
        """Evaluate not in condition."""
        return actual not in expected

    def _evaluate_greater_than(self, actual: Any, expected: Any) -> bool:
        """Evaluate greater than condition."""
        try:
            return actual > expected
        except TypeError:
            return False

    def _evaluate_less_than(self, actual: Any, expected: Any) -> bool:
        """Evaluate less than condition."""
        try:
            return actual < expected
        except TypeError:
            return False
