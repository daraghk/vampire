#!/usr/bin/env python3
"""Tests for parallel_search.parsing.tptp."""

from parallel_search.parsing.tptp import (
    parse_cnf_clause,
    parse_tff_clause,
    set_tptp_role,
    strip_quantifiers,
)


def test_parse_cnf_clause():
    clause = parse_cnf_clause("cnf(c1, axiom, p(X) | ~q(Y)).")
    assert clause is not None
    assert clause.name == "c1"
    assert "p(X)" in clause.literals


def test_parse_tff_clause_strips_quantifiers():
    clause = parse_tff_clause("tff(u10,axiom, (![X0] : ((mult(e,X0) = X0)))).")
    assert clause is not None
    assert "mult(e,X0)" in clause.literals


def test_strip_quantifiers():
    assert strip_quantifiers("![X0 : $int] : p(X)") == "p(X)"


def test_set_tptp_role():
    original = "cnf(seed1, axiom, p(a))."
    assert set_tptp_role(original, "lemma") == "cnf(seed1, lemma, p(a))."
    tff = "tff(seed2, hypothesis, p(X))."
    assert set_tptp_role(tff, "conjecture") == "tff(seed2, conjecture, p(X))."
