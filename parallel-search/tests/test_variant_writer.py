#!/usr/bin/env python3
"""Tests for variant_writer."""

from pathlib import Path

from parallel_search.parsing.tptp import parse_cnf_clause
from parallel_search.variants.writer import write_original_with_lemmas


def test_write_original_with_lemmas(tmp_path):
    original = tmp_path / "orig.p"
    original.write_text("fof(a, axiom, p(a)).\n")
    lemma = parse_cnf_clause("cnf(lemma1, axiom, q(a)).")
    out = tmp_path / "variant_0_original.p"
    assert write_original_with_lemmas(original, [lemma], out)
    content = out.read_text()
    assert "Generated lemmas" in content
    assert "lemma" in content
