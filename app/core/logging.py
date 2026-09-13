"""Minimal structured logging configuration for INIS."""

import logging

import structlog


def configure_structlog(level: str = "INFO", json: bool = False) -> None:
    """Configure stdlib-backed structlog output at the requested level."""
    level_number = logging.getLevelNamesMapping().get(level.upper())
    if not isinstance(level_number, int):
        raise ValueError(f"Unknown log level: {level}")

    logging.basicConfig(level=level_number, format="%(message)s", force=True)
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level_number),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger."""
    return structlog.get_logger(name)
