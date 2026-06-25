#!/usr/bin/env python3
"""Tests for axioms_filter.create_axioms_file."""

from pathlib import Path

from parallel_search.variants.axioms import create_axioms_file, filter_negated_conjectures
from parallel_search.variants.constructor import BaseClauseSetConstructor


def test_filter_negated_conjectures():
    fixture = Path(__file__).parent / "fixtures" / "sample_c0.p"
    parser = BaseClauseSetConstructor(None, fixture)
    axioms = filter_negated_conjectures(parser.clauses)
    assert len(axioms) == 2
    assert all(c.name in ("u1", "u2") for c in axioms)


def test_create_axioms_file(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "sample_c0.p"
    clausified = tmp_path / "problem_clausified.p"
    clausified.write_text(fixture.read_text())
    axioms_path = create_axioms_file(clausified)
    assert axioms_path.exists()
    content = axioms_path.read_text()
    assert "negated_conjecture" not in content
    assert "cnf(u1" in content
    assert "cnf(c1" not in content
