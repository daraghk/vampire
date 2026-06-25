#!/usr/bin/env python3
"""Tests for EntailmentChecker with mocked Vampire."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from parallel_search.entailment.checker import EntailmentChecker


def test_entailment_unsat(tmp_path):
    axioms = tmp_path / "axioms.p"
    axioms.write_text("cnf(u1,axiom, p(a)).\n")
    logger = MagicMock()
    checker = EntailmentChecker(logger, vampire_binary="vampire", timeout=5)

    mock_result = MagicMock()
    mock_result.stdout = "% SZS status Unsatisfiable\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch("parallel_search.entailment.checker.subprocess.run", return_value=mock_result):
        assert checker.check_entailment(axioms, "cnf(s1, axiom, p(a)).") is True


def test_entailment_timeout(tmp_path):
    axioms = tmp_path / "axioms.p"
    axioms.write_text("cnf(u1,axiom, p(a)).\n")
    logger = MagicMock()
    checker = EntailmentChecker(logger, vampire_binary="vampire", timeout=1)

    import subprocess

    with patch(
        "parallel_search.entailment.checker.subprocess.run",
        side_effect=subprocess.TimeoutExpired("vampire", 1),
    ):
        assert not checker.check_entailment(axioms, "cnf(s1, axiom, p(a)).")
