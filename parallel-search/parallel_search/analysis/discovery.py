"""Shared discovery helpers for result analysis scripts.

Locates per-problem output directories that contain evaluation results,
supporting both the current timestamped layout and legacy flat bundles
from the GRP-655 benchmark reproduction.

Used by ``analyze_results.py`` and related tooling.
"""

from pathlib import Path
from typing import List


def discover_problem_directories(output_dir: Path) -> List[Path]:
    """Find problem run directories containing results/summary.json.

    Walks ``output_dir`` recursively and returns the parent of each
    ``results/`` directory that contains ``summary.json``.

    Supports:
    - Timestamped runs: ``output/2026-01-28_GRP029-2/results/summary.json``
    - Flat bundles: ``output/results/vampire-5.0-results-GRP-655/GRP029-2/results/summary.json``

    Args:
        output_dir: Root directory to search (e.g. ``output/``).

    Returns:
        Sorted list of unique problem directory paths.
    """
    problem_dirs = []
    for summary_path in output_dir.rglob("results/summary.json"):
        problem_dirs.append(summary_path.parent.parent)
    return sorted(set(problem_dirs), key=lambda path: path.name)
