"""Policy loader per INIS §19.3."""

import json
from typing import Any, Dict

from app.core.errors import ValidationError


class PolicyLoader:
    """Load access policies from dict or JSON."""

    def load_from_dict(self, policy_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Load policy from dictionary.

        Args:
            policy_dict: Dictionary containing policy definition

        Returns:
            Validated policy dictionary

        Raises:
            ValidationError: If policy is invalid
        """
        self._validate_policy(policy_dict)
        return policy_dict

    def load_from_json(self, json_str: str) -> Dict[str, Any]:
        """Load policy from JSON string.

        Args:
            json_str: JSON string containing policy definition

        Returns:
            Validated policy dictionary

        Raises:
            ValidationError: If policy is invalid or JSON is malformed
        """
        try:
            policy_dict = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")

        return self.load_from_dict(policy_dict)

    def _validate_policy(self, policy: Dict[str, Any]) -> None:
        """Validate policy structure per INIS §19.3.

        Args:
            policy: Policy dictionary to validate

        Raises:
            ValidationError: If policy structure is invalid
        """
        required_fields = ["policy_id", "subject", "resource", "action", "effect"]

        for field in required_fields:
            if field not in policy:
                raise ValidationError(f"Missing required field: {field}")

        if policy["effect"] not in ["allow", "deny"]:
            raise ValidationError("Effect must be 'allow' or 'deny'")

        if policy["action"] not in ["read", "write", "update", "delete", "transmit", "search"]:
            raise ValidationError("Invalid action")

        resource = policy["resource"]
        if "type" not in resource:
            raise ValidationError("Resource must have 'type' field")

        if resource["type"] not in ["information", "source", "dataset", "document"]:
            raise ValidationError("Invalid resource type")

        if "classification" in resource:
            if resource["classification"] not in ["public", "internal", "confidential", "restricted"]:
                raise ValidationError("Invalid classification")
