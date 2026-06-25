#!/usr/bin/env python3
"""Tests for result_discovery."""

from pathlib import Path

from parallel_search.analysis.discovery import discover_problem_directories


def test_discover_flat_and_timestamped_layouts(tmp_path):
    ts_dir = tmp_path / "2026-01-28_12-00-00_GRP029-2"
    flat_dir = tmp_path / "GRP441-1"
    for d in (ts_dir, flat_dir):
        results = d / "results"
        results.mkdir(parents=True)
        (results / "summary.json").write_text('{"problem": "x", "results": []}')

    found = discover_problem_directories(tmp_path)
    assert len(found) == 2
