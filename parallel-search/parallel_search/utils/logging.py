#!/usr/bin/env python3
"""Logging utilities for parallel Vampire search.

Provides a shared logger setup used by ``scripts/main.py``, ``scripts/clausify.py``,
and analysis scripts. Each problem run gets its own log file under the
timestamped output directory; DEBUG goes to the file and INFO+ to the console
by default.
"""

import logging
from pathlib import Path


def setup_logger(
    log_file: Path,
    log_to_console: bool = True,
    log_level: int = logging.INFO,
    logger_name: str = "vampire_parallel",
) -> logging.Logger:
    """Set up a logger with file and optional console output.

    Clears any existing handlers on the named logger to avoid duplicate output
    when processing multiple problems in one process.

    Args:
        log_file: Path to the log file (parent directories are created).
        log_to_console: If True, also emit INFO+ messages to stderr.
        log_level: Console handler level (file always receives DEBUG).
        logger_name: Logger name (use per-problem names to isolate handlers).

    Returns:
        Configured ``logging.Logger`` instance.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M"
    )

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.info(f"Log file: {log_file}")
    return logger
