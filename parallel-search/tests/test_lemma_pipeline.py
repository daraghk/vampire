#!/usr/bin/env python3
"""Tests for parallel_search.lemmas.pipeline axiom sampling."""

from parallel_search.lemmas.pipeline import sample_axioms_for_llm
from parallel_search.parsing.tptp import parse_cnf_clause


def _cnf(name, body):
    return parse_cnf_clause(f"cnf({name}, axiom, {body}).")


def test_sample_all_when_under_cap():
    clauses = [_cnf(f"c{i}", f"p{i}(a)") for i in range(5)]
    sampled = sample_axioms_for_llm(clauses, cap=30, sample_seed=42)
    assert len(sampled) == 5


def test_sample_caps_large_set():
    clauses = [_cnf(f"c{i}", f"p{i}(a)") for i in range(50)]
    sampled = sample_axioms_for_llm(clauses, cap=10, sample_seed=42)
    assert len(sampled) == 10
