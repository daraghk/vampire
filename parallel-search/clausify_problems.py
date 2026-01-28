#!/usr/bin/env python3
"""Clausification module for Parallel Vampire Search.

Definitions:
- C₀ = Full clausified problem (Axioms ∪ negated_conjectures)
- C_ax = Axioms-only version (negated_conjectures removed from C₀)
- Variant = B_i + verified seeds + negated_conjectures

This module provides the VampireClausifier class for converting TPTP/SMT-LIB
problems to clausified form using Vampire's --mode clausify or --mode tclausify.

- 'clausify' mode: Produces CNF output (default, suitable for CNF/FOF problems)
- 'tclausify' mode: Produces TFF output (preserves type information for arithmetic)

This is the first step in the workflow: converting problems to clausified form (C₀)
before constructing variants. Main.py then creates C_ax by filtering negated_conjectures.

Used by main.py to perform the clausification step of the workflow.

Usage:
    from clausify_problems import VampireClausifier

    clausifier = VampireClausifier(
        logger,
        vampire_binary="../build/vampire",
        output_dir=Path("output/clausified"),
        timeout=60,
    )
    clausifier.clausify_problem(Path("problem.tptp"))
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional


class VampireClausifier:
    """Handles clausification of TPTP/SMT-LIB problems using Vampire.

    Supports two clausification modes:
    - 'clausify': Produces CNF (Clause Normal Form) output - suitable for most problems
    - 'tclausify': Produces TFF (Typed First-order Form) output - preserves type information
      for arithmetic problems but converts everything to TFF format
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
            logger: Logger instance for logging.
            vampire_binary: Path to vampire executable.
            output_dir: Directory to save clausified outputs. If None, saves
                alongside original files with '_clausified' suffix.
            timeout: Timeout in seconds for each problem.
            mode: Clausification mode: 'clausify' (CNF output) or 'tclausify' (TFF output).
                Default is 'clausify' for compatibility with CNF/FOF problems.
        """
        self.logger = logger
        self.vampire_binary = vampire_binary
        self.output_dir = output_dir
        self.timeout = timeout
        self.mode = mode
        if mode not in ["clausify", "tclausify"]:
            raise ValueError(
                f"Invalid clausification mode: {mode}. Must be 'clausify' or 'tclausify'"
            )
        self.stats = {"success": 0, "error": 0, "timeout": 0, "skipped": 0}

    def is_problem_file(self, path: Path) -> bool:
        """Check if a file is a problem file.

        Args:
            path: File path to check.

        Returns:
            True if file has a recognized problem extension (.p, .tptp, .smt2, .ax).
        """
        return path.suffix in {".p", ".tptp", ".smt2", ".ax"}

    def clausify_problem(self, problem_path: Path) -> bool:
        """Clausify a single problem.

        Args:
            problem_path: Path to the problem file.

        Returns:
            True if clausification succeeded, False otherwise.
        """
        # Determine output path
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
            # Run vampire in the specified clausification mode
            # 'clausify' produces CNF output, 'tclausify' produces TFF output (preserves types)
            result = subprocess.run(
                [self.vampire_binary, "--mode", self.mode, str(problem_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            # Save output, filtering out Vampire's diagnostic messages
            with open(output_path, "w") as f:
                for line in result.stdout.splitlines():
                    # Skip Vampire's diagnostic messages (but keep TPTP comments)
                    if (
                        line.strip().startswith("% Running in")
                        or line.strip().startswith("% Trying ")
                        or line.strip().startswith("% Failed with")
                    ):
                        continue
                    f.write(line + "\n")

            # Check if clausification was successful
            if result.returncode == 0:
                self.stats["success"] += 1
                return True
            else:
                self.logger.error(
                    f"    Clausification error (code {result.returncode})"
                )
                if result.stderr:
                    self.logger.error(f"    {result.stderr[:200]}")
                self.stats["error"] += 1
                return False

        except subprocess.TimeoutExpired:
            self.logger.warning(f"    Timeout after {self.timeout}s")
            self.stats["timeout"] += 1
            return False
        except FileNotFoundError:
            self.logger.error(f"    Vampire binary not found: {self.vampire_binary}")
            self.logger.error(f"    Make sure Vampire is built: cd build && make")
            sys.exit(1)
        except Exception as e:
            self.logger.error(f"    Unexpected error: {e}")
            self.stats["error"] += 1
            return False

    def process_directory(self, directory: Path, recursive: bool = False) -> None:
        """Process all problems in a directory.

        Args:
            directory: Directory containing problem files.
            recursive: Whether to recurse into subdirectories.
        """
        if not directory.exists():
            self.logger.error(f"Error: Directory not found: {directory}")
            sys.exit(1)

        # Collect problem files
        if recursive:
            problems = [p for p in directory.rglob("*") if self.is_problem_file(p)]
        else:
            problems = [p for p in directory.glob("*") if self.is_problem_file(p)]

        if not problems:
            self.logger.warning(f"No problem files found in {directory}")
            return

        self.logger.info(f"Found {len(problems)} problem(s)")

        # Process each problem
        for i, problem in enumerate(sorted(problems), 1):
            self.logger.info(f"[{i}/{len(problems)}]")
            self.clausify_problem(problem)

        # Log summary
        self.logger.info("=" * 40)
        self.logger.info("Summary:")
        self.logger.info(f"  Success:  {self.stats['success']}")
        self.logger.info(f"  Errors:   {self.stats['error']}")
        self.logger.info(f"  Timeouts: {self.stats['timeout']}")
        self.logger.info(f"  Total:    {len(problems)}")

    def process_single_file(self, file_path: Path) -> None:
        """Process a single problem file.

        Args:
            file_path: Path to the problem file to clausify.
        """
        if not file_path.exists():
            self.logger.error(f"Error: File not found: {file_path}")
            sys.exit(1)

        if not self.is_problem_file(file_path):
            self.logger.warning(
                f"Warning: {file_path} doesn't look like a problem file"
            )
            self.logger.warning("  Expected extensions: .p, .tptp, .smt2, .ax")

        self.clausify_problem(file_path)
