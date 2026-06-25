#!/usr/bin/env python3
"""Tests for LLM lemma prompt format selection."""

import logging
import sys
from unittest.mock import MagicMock

mock_openai = MagicMock()
mock_openai.OpenAI = MagicMock()
sys.modules["openai"] = mock_openai

from parallel_search.lemmas.generator import LemmaGenerator  # noqa: E402


def test_cnf_prompt_uses_cnf_format():
    generator = LemmaGenerator(logging.getLogger("test"), api_key="test-key")
    prompt = generator._build_prompt(
        "context",
        ["cnf(u1,axiom, p(a)).", "cnf(u2,axiom, q(b))."],
        num_lemmas=3,
        clause_format="CNF",
    )
    assert "CNF" in prompt
    assert "cnf(transitivity_leq" in prompt
    assert "tff(transitivity_leq" not in prompt


def test_tff_prompt_uses_tff_format():
    generator = LemmaGenerator(logging.getLogger("test"), api_key="test-key")
    prompt = generator._build_prompt(
        "context",
        ["tff(u1,axiom, p(X))."],
        num_lemmas=3,
        clause_format="TFF",
    )
    assert "TFF" in prompt
    assert "tff(transitivity_leq" in prompt
