#!/usr/bin/env python3
"""Entailment checker for parallel Vampire search.

Definitions:
- C₀ = Full clausified problem (Axioms ∪ negated_conjectures)
- C_ax = Axioms-only version (negated_conjectures removed from C₀)

This module verifies that lemmas L_i are entailed by C_ax using Vampire's
native conjecture proving:

1. Read C_ax (axioms-only file)
2. Add lemma s with conjecture role (CNF lemmas converted to TFF)
3. Run Vampire; UNSAT/refutation means C_ax ⊨ s

Entailment is checked against C_ax (not C₀) to avoid vacuous truth.

Used by ``lemma_pipeline.py`` during lemma verification.

Usage:
    from parallel_search.entailment.checker import EntailmentChecker

    checker = EntailmentChecker(logger, vampire_binary="../build/vampire", timeout=10)
    is_entailed = checker.check_entailment(axioms_only_path, lemma_clause)
"""

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from parallel_search.parsing.tptp import set_tptp_role


class EntailmentChecker:
    """Verify C_ax ⊨ s by proving lemma s as a conjecture with Vampire."""

    def __init__(
        self,
        logger: logging.Logger,
        vampire_binary: str = "../build/vampire",
        timeout: int = 10,
    ):
        self.logger = logger
        self.vampire_binary = vampire_binary
        self.timeout = timeout

    def check_entailment(self, axioms_only: Path, lemma_clause: str) -> bool:
        """Check whether C_ax entails the given lemma.

        Args:
            axioms_only: Path to C_ax (axioms-only clausified file).
            lemma_clause: Lemma in CNF or TFF format.

        Returns:
            True if Vampire finds a refutation (lemma is entailed), False otherwise.
        """
        try:
            self.logger.debug(f"  Checking entailment for lemma: {lemma_clause}")

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".tptp", delete=False
            ) as tmp:
                tmp_path = Path(tmp.name)
                with open(axioms_only, "r", encoding="utf-8") as handle:
                    tmp.write(handle.read())

                if lemma_clause.startswith("tff("):
                    tmp.write(f"\n{set_tptp_role(lemma_clause, 'conjecture')}\n")
                elif lemma_clause.startswith("cnf("):
                    cnf_match = re.match(
                        r"cnf\(([^,]+),\s*([^,]+),\s*(.+)\)\.", lemma_clause
                    )
                    if not cnf_match:
                        self.logger.warning(
                            f"  Failed to parse CNF lemma: {lemma_clause[:50]}..."
                        )
                        return False
                    name = cnf_match.group(1).strip()
                    clause_content = cnf_match.group(3).strip()
                    tmp.write(f"\ntff({name}, conjecture, {clause_content}).\n")
                else:
                    self.logger.warning(
                        f"  Lemma not in CNF or TFF format: {lemma_clause}"
                    )
                    return False

            result = self._run_vampire(tmp_path)
            try:
                tmp_path.unlink()
            except OSError:
                pass
            return result == "unsat"

        except Exception as exc:
            self.logger.error(f"  Entailment check failed: {exc}", exc_info=True)
            return False

    def _run_vampire(self, problem_file: Path) -> str:
        """Run Vampire on a problem and classify the result."""
        try:
            cmd = [self.vampire_binary, str(problem_file)]
            self.logger.debug(f"  Running Vampire: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            output = result.stdout + result.stderr

            if "Refutation found" in output or "% SZS status Unsatisfiable" in output:
                self.logger.debug("  Entailment check result: UNSAT (entailed)")
                return "unsat"
            if "% SZS status Satisfiable" in output:
                self.logger.debug("  Entailment check result: SAT (not entailed)")
                return "sat"
            self.logger.debug("  Entailment check result: UNKNOWN")
            return "unknown"

        except subprocess.TimeoutExpired:
            self.logger.debug(
                f"  Entailment check timeout after {self.timeout}s (treated as unknown)"
            )
            return "unknown"
        except Exception as exc:
            self.logger.error(f"  Vampire execution failed: {exc}", exc_info=True)
            return "unknown"
