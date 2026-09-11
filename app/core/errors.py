"""Application exceptions and delivery statuses without infrastructure dependencies."""

from enum import Enum


class InisError(Exception):
    """Base exception for all INIS errors."""


class DomainError(InisError):
    """Raised when a domain rule is violated."""


class InfrastructureError(InisError):
    """Raised when an infrastructure operation fails."""


class ValidationError(InisError):
    """Raised when an INIS validation invariant is violated."""


class OutputStatus(str, Enum):
    """Authorized output statuses defined by INIS section 1.3."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_STALE = "SOURCE_STALE"
    ACCESS_DENIED = "ACCESS_DENIED"
    DATA_INVALID = "DATA_INVALID"
    TOOL_FAILURE = "TOOL_FAILURE"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"
