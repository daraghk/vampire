#!/usr/bin/env python3
"""Clausification module for parallel Vampire search.

Definitions:
- C₀ = Full clausified problem (Axioms ∪ negated_conjectures)

This module converts TPTP/SMT-LIB problems to clausified form using Vampire's
``--mode clausify`` (CNF) or ``--mode tclausify`` (TFF). This is the first step
in the workflow before C_ax creation and variant construction.

Modes:
- ``clausify``: CNF output — suitable for most CNF/FOF problems (default)
- ``tclausify``: TFF output — preserves type information for arithmetic

Used by ``main.py``. Also runnable standalone for batch clausification.

Usage:
    from parallel_search.clausify.clausifier import VampireClausifier

    clausifier = VampireClausifier(
        logger,
        vampire_binary="../build/vampire",
        output_dir=Path("output/clausified"),
        timeout=60,
        mode="clausify",
    )
    clausifier.clausify_problem(Path("problem.tptp"))
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from parallel_search.utils.logging import setup_logger


class VampireClausifier:
    """Clausify TPTP/SMT-LIB problems using Vampire.

    Filters Vampire diagnostic lines from stdout while preserving TPTP comments
    and clause output.
    """

    def __init__(
        self,
        logger: logging.Logger,
        vampire_binary: str = "../build/vampire",
        output_dir: Optional[Path] = None,
        timeout: int = 60,
        mode: str = "clausify",
    ):
        """Initialize the clausifier.

        Args:
            logger: Logger instance.
            vampire_binary: Path to Vampire executable.
            output_dir: Directory for clausified output; if None, writes alongside input.
            timeout: Clausification timeout in seconds.
            mode: ``clausify`` (CNF) or ``tclausify`` (TFF).
        """
        self.logger = logger
        self.vampire_binary = vampire_binary
        self.output_dir = output_dir
        self.timeout = timeout
        self.mode = mode
        if mode not in ("clausify", "tclausify"):
            raise ValueError(
                f"Invalid clausification mode: {mode}. Must be 'clausify' or 'tclausify'"
            )
        self.stats = {"success": 0, "error": 0, "timeout": 0}

    def is_problem_file(self, path: Path) -> bool:
        """Return True if ``path`` has a recognized problem extension."""
        return path.suffix in {".p", ".tptp", ".smt2", ".ax"}

    def clausify_problem(self, problem_path: Path) -> bool:
        """Clausify a single problem to C₀.

        Args:
            problem_path: Path to the input problem file.

        Returns:
            True if clausification succeeded (Vampire exit code 0).
        """
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = (
                self.output_dir / f"{problem_path.stem}_clausified{problem_path.suffix}"
            )
        else:
            output_path = (
                problem_path.parent
                / f"{problem_path.stem}_clausified{problem_path.suffix}"
            )

        try:
            result = subprocess.run(
                [self.vampire_binary, "--mode", self.mode, str(problem_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            with open(output_path, "w", encoding="utf-8") as handle:
                for line in result.stdout.splitlines():
                    if line.strip().startswith(
                        ("% Running in", "% Trying ", "% Failed with")
                    ):
                        continue
                    handle.write(line + "\n")

            if result.returncode == 0:
                self.stats["success"] += 1
                return True

            self.logger.error(f"Clausification error (code {result.returncode})")
            if result.stderr:
                self.logger.error(result.stderr[:200])
            self.stats["error"] += 1
            return False

        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout after {self.timeout}s")
            self.stats["timeout"] += 1
            return False
        except FileNotFoundError:
            self.logger.error(f"Vampire binary not found: {self.vampire_binary}")
            sys.exit(1)
        except Exception as exc:
            self.logger.error(f"Unexpected error: {exc}")
            self.stats["error"] += 1
            return False
