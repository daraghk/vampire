#!/usr/bin/env python3
"""Tests for VampireClausifier with mocked subprocess."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from parallel_search.clausify.clausifier import VampireClausifier


def test_clausify_writes_filtered_output(tmp_path):
    problem = tmp_path / "problem.p"
    problem.write_text("fof(a, axiom, p(a)).\n")
    logger = MagicMock()
    clausifier = VampireClausifier(
        logger, vampire_binary="vampire", output_dir=tmp_path, mode="clausify"
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "% Running in clausify mode\nfof(a, axiom, p(a)).\n"
    mock_result.stderr = ""

    with patch("parallel_search.clausify.clausifier.subprocess.run", return_value=mock_result):
        assert clausifier.clausify_problem(problem)

    out = tmp_path / "problem_clausified.p"
    assert out.exists()
    text = out.read_text()
    assert "Running in" not in text
    assert "fof(a" in text
