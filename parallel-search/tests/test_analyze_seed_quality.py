#!/usr/bin/env python3
"""Tests for analyze_seed_quality_logs classification."""

from analyze_seed_quality_logs import SeedRecord, _classify_seed_block


def test_classify_entailed_seed():
    record = SeedRecord(variant_index=0, seed_index=0)
    lines = [
        "VARIANT 0 SEED 0",
        "    ✓ Entailment verified (C_ax ⊨ s)",
    ]
    _classify_seed_block(record, lines)
    assert record.entailed
    assert not record.post_parse_failed


def test_classify_syntax_error():
    record = SeedRecord(variant_index=0, seed_index=1)
    lines = [
        "VARIANT 0 SEED 1",
        "    ✗ Entailment check failed, skipping seed",
        "    Parser exception: syntax error",
    ]
    _classify_seed_block(record, lines)
    assert record.entailment_syntax_or_type_error
