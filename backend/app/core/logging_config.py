"""Centralised logging configuration for the RFP Intelligence Platform.

Provides:
- Coloured console output via ``colorlog``
- Plain-text daily-rotating file log at ``logs/crawl.log`` (7-day retention)
- A single call-site: ``setup_logging()`` in ``main.py`` app factory

Color scheme
------------
BLUE    = INFO
GREEN   = SUCCESS  (custom level 25, between INFO and WARNING)
YELLOW  = WARNING
RED     = ERROR / CRITICAL
CYAN    = DATA     (custom level 15, between DEBUG and INFO)
MAGENTA = PROMPT   (custom level 22, between DATA and INFO)

Usage
-----
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    logger.info("plain info")
    logger.success("opportunity saved")         # green
    logger.data("content preview: %s", text)    # cyan
    logger.prompt("sending prompt: %s", text)   # magenta
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Custom levels
# ---------------------------------------------------------------------------
_DATA_LEVEL = 15       # cyan  — raw content/data previews
_PROMPT_LEVEL = 22     # magenta — LLM prompt / response log
_SUCCESS_LEVEL = 25    # green  — persisted doc/opportunity


def _add_level(level: int, name: str, method: str) -> None:
    """Register a custom log level and add a convenience method to Logger."""
    logging.addLevelName(level, name)

    def _log(self: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
        if self.isEnabledFor(level):
            self._log(level, message, args, **kwargs)  # noqa: SLF001

    _log.__name__ = method
    setattr(logging.Logger, method, _log)


_add_level(_DATA_LEVEL, "DATA", "data")
_add_level(_PROMPT_LEVEL, "PROMPT", "prompt")
_add_level(_SUCCESS_LEVEL, "SUCCESS", "success")


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
_CONSOLE_FORMAT = (
    "%(log_color)s%(asctime)s │ %(levelname)-8s │ %(name)s%(reset)s\n"
    "%(log_color)s    %(message)s%(reset)s"
)

_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LOG_COLORS: dict[str, str] = {
    "DATA": "cyan",
    "DEBUG": "white",
    "PROMPT": "purple",
    "INFO": "blue",
    "SUCCESS": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}


def _make_console_handler() -> logging.Handler:
    try:
        import colorlog  # noqa: PLC0415

        handler = colorlog.StreamHandler(sys.stdout)
        handler.setFormatter(
            colorlog.ColoredFormatter(
                _CONSOLE_FORMAT,
                datefmt=_DATE_FORMAT,
                log_colors=_LOG_COLORS,
                reset=True,
                style="%",
            )
        )
    except ImportError:
        # colorlog not installed — fall back to plain formatter (no crash)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _make_file_handler(log_dir: Path) -> logging.Handler:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "crawl.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        utc=True,
    )
    handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
    return handler


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    level: int | str | None = None,
    log_dir: str | Path = "logs",
) -> None:
    """Configure root logger with coloured console + rotating file handlers.

    Call once from the FastAPI application factory (``main.py``).
    Subsequent calls are no-ops once the root logger has handlers.
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. in tests or multiple factory calls)
        return

    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()

    numeric = getattr(logging, str(level), logging.INFO)
    # Our custom levels must be discoverable at the root level
    root.setLevel(min(numeric, _DATA_LEVEL))

    root.addHandler(_make_console_handler())
    root.addHandler(_make_file_handler(Path(log_dir)))

    # Quieten noisy third-party loggers
    for _noisy in ("httpx", "httpcore", "asyncio", "uvicorn.access"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised — level=%s, file=%s/crawl.log", level, log_dir
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Always prefer this over ``logging.getLogger``
    so custom levels (success/data/prompt) are guaranteed to be registered."""
    return logging.getLogger(name)
