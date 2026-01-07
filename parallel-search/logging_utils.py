#!/usr/bin/env python3
"""Logging utilities for Parallel Vampire Search.

Provides centralized logging setup with file and console output.
Each problem run creates a timestamped log file in its dedicated output directory.

Log timestamps use HH:MM format (hours:minutes) since the full date
is already present in the output directory name.
"""

import logging
from pathlib import Path


def setup_logger(
    log_file: Path,
    log_to_console: bool = True,
    log_level: int = logging.INFO,
) -> logging.Logger:
    """Set up a logger with file and optional console output.

    Timestamps in logs use HH:MM format for conciseness.

    Args:
        log_file: Path to log file.
        log_to_console: Whether to also log to console (default: True).
        log_level: Logging level (default: INFO).

    Returns:
        Configured logger instance.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("vampire_parallel")
    # Always log DEBUG to file for debugging, but respect log_level for console
    logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    logger.handlers.clear()

    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)

    # Formatter (time only, no date - date is in folder name)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M"
    )
    fh.setFormatter(formatter)

    logger.addHandler(fh)

    # Console handler (optional)
    if log_to_console:
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    logger.info(f"Log file: {log_file}")
    return logger
