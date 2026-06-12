"""Logging setup (M0 P1-6 r1 修订: structlog 配置)."""
import logging
import structlog

from app.config import settings


def configure_logging() -> None:
    """Configure structlog + stdlib logging from settings.log."""
    level = getattr(logging, settings.log.level.upper(), logging.INFO)

    # stdlib logging (for uvicorn / sqlalchemy / etc)
    logging.basicConfig(
        format="%(message)s",
        level=level,
    )

    # structlog config
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if settings.log.json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger."""
    return structlog.get_logger(name)
