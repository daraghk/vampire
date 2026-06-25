#!/usr/bin/env python3
"""Parallel Vampire execution on original and lemma-augmented variants.

Parallel evaluation runs only when at least one variant has verified lemmas.
The original problem is included as a baseline for comparison against
lemma-augmented variants; if no variants qualify, nothing is run.

When variants exist, this module runs Vampire in parallel on:
- The original (non-clausified) problem (baseline)
- Optionally the clausified C₀ baseline (``--include-clausified-runs``)
- Each variant with verified lemmas (``variant_N_original.tptp`` by default)

Variant selection uses ``variants/manifest.json`` when present (preferred).
A deprecated log-regex fallback exists for legacy GRP output directories without
a manifest (parses old ``VARIANT N SEED M`` log format).

Results are written to ``results/*.out`` and summarized in ``results/summary.json``.

Used by ``main.py`` when ``--run-vampire`` is set.
"""

import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from parallel_search.variants.manifest import (
    get_runnable_variant_paths,
    read_manifest,
)


def _run_vampire_worker(
    problem_file: str,
    output_file: str,
    vampire_binary: str,
    timeout: Optional[int],
    name: str,
) -> Dict:
    """Run Vampire in a worker process (no logger — returns structured result).

    Designed for ``ProcessPoolExecutor``: captures stdout/stderr to a file and
    parses SZS status markers to classify the run.

    Args:
        problem_file: Path to the TPTP problem file.
        output_file: Path where Vampire output will be written.
        vampire_binary: Path to the Vampire executable.
        timeout: Per-run timeout in seconds (None for no limit).
        name: Short label for this run (e.g. ``original``, ``variant_1_original``).

    Returns:
        Dict with keys: name, status, time, exit_code, output_file, message,
        and optionally error.
    """
    start_time = time.time()
    problem_path = Path(problem_file)
    out_path = Path(output_file)

    try:
        cmd = [vampire_binary, str(problem_path)]
        if timeout:
            cmd.extend(["-t", str(timeout)])

        subprocess_timeout = timeout + 5 if timeout else None
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=subprocess_timeout,
        )
        elapsed = time.time() - start_time

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(result.stdout)
            if result.stderr:
                handle.write("\n=== STDERR ===\n")
                handle.write(result.stderr)

        output = result.stdout
        if (
            "Refutation found" in output
            or "Theorem" in output
            or "% SZS status Theorem" in output
        ):
            status = "PROVED"
        elif "% SZS status Unsatisfiable" in output:
            status = "UNSAT"
        elif "% SZS status Satisfiable" in output:
            status = "SAT"
        elif "Time limit reached" in output or "% SZS status Timeout" in output:
            status = "TIMEOUT"
        else:
            status = "UNKNOWN"

        return {
            "name": name,
            "status": status,
            "time": elapsed,
            "exit_code": result.returncode,
            "output_file": str(out_path),
            "message": f"{name}: {status} in {elapsed:.2f}s",
        }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(f"Vampire execution timed out after {timeout} seconds\n")
        return {
            "name": name,
            "status": "TIMEOUT",
            "time": elapsed,
            "exit_code": None,
            "output_file": str(out_path),
            "message": f"{name}: TIMEOUT after {timeout}s",
        }

    except Exception as exc:
        elapsed = time.time() - start_time
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(f"Error running Vampire: {exc}\n")
        return {
            "name": name,
            "status": "ERROR",
            "time": elapsed,
            "exit_code": None,
            "output_file": str(out_path),
            "error": str(exc),
            "message": f"{name}: ERROR - {exc}",
        }


def _legacy_has_verified_lemmas(variant_path: Path, log_file: Path) -> bool:
    """Deprecated fallback: infer verified lemmas from legacy GRP log format.

    Scans the main run log for ``VARIANT N SEED M`` blocks (historical format)
    and checks whether any entry for variant N has ``✓ Entailment verified``.
    Used only when ``manifest.json`` is absent.
    """
    import re

    variant_name = variant_path.stem
    if not variant_name.startswith("variant_"):
        return False
    parts = variant_name.split("_")
    if len(parts) < 2 or not parts[1].isdigit():
        return False
    variant_num = parts[1]

    with open(log_file, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read()

    pattern = rf"VARIANT {variant_num} SEED \d+.*?(?:✓ Entailment verified|✗ Entailment check failed)"
    for match in re.findall(pattern, content, re.DOTALL):
        if "✓ Entailment verified" in match:
            return True
    return False


def _resolve_runnable_variants(
    variants_dir: Path,
    include_clausified: bool,
    logger,
) -> List[Path]:
    """Determine which variant problem files should be run.

    Prefers ``manifest.json`` (only variants with ``verified_lemma_count > 0``).
    Falls back to log-regex verification, then to globbing all matching files.

    Args:
        variants_dir: Directory containing variant TPTP files and manifest.
        include_clausified: If True, include clausified variants (``variant_N.tptp``).
        logger: Logger for warnings about fallback behaviour.

    Returns:
        Sorted list of variant file paths to execute.
    """
    manifest = read_manifest(variants_dir)
    if manifest:
        return get_runnable_variant_paths(
            variants_dir, include_clausified=include_clausified, manifest=manifest
        )

    log_files = sorted(variants_dir.parent.glob("*.log"))
    if not log_files:
        logger.warning("No manifest.json or log file; using *_original.tptp variants")
        if include_clausified:
            return sorted(variants_dir.glob("variant_*.tptp"))
        return sorted(variants_dir.glob("variant_*_original.tptp"))

    log_file = log_files[0]
    logger.warning("Using deprecated log-based lemma verification fallback (GRP format)")
    candidates = sorted(variants_dir.glob("variant_*.tptp"))
    if include_clausified:
        verified = [v for v in candidates if _legacy_has_verified_lemmas(v, log_file)]
    else:
        verified = [
            v
            for v in variants_dir.glob("variant_*_original.tptp")
            if _legacy_has_verified_lemmas(
                variants_dir / v.name.replace("_original.tptp", ".tptp"), log_file
            )
        ]
    return verified


def run_parallel_evaluation(
    problem_output_dir: Path,
    logger,
    vampire_binary: str = "../build/vampire",
    timeout: int = 60,
    max_workers: Optional[int] = None,
    original_problem: Optional[Path] = None,
    include_clausified_runs: bool = False,
) -> Dict:
    """Run Vampire in parallel on original and lemma-augmented variants.

    Requires at least one runnable variant (verified lemmas). When variants exist,
    runs the original as a comparison baseline plus each runnable variant.
    Skips entirely when no variants qualify.

    Args:
        problem_output_dir: Per-problem timestamped output directory.
        logger: Logger instance.
        vampire_binary: Path to Vampire executable.
        timeout: Per-run timeout in seconds.
        max_workers: Process pool size (None = default executor sizing).
        original_problem: Path to the original input problem file.
        include_clausified_runs: Also run C₀ and clausified lemma variants.

    Returns:
        Summary dict (also written to ``results/summary.json``) with keys:
        problem, timestamp, configuration, results, statistics.
    """
    variants_dir = problem_output_dir / "variants"
    runnable_variants = _resolve_runnable_variants(
        variants_dir, include_clausified_runs, logger
    )

    logger.info("")
    logger.info("=" * 80)
    logger.info("PARALLEL VAMPIRE EVALUATION")
    logger.info("=" * 80)
    if original_problem and original_problem.exists():
        logger.info(f"Original problem: {original_problem.name}")
    logger.info(f"Runnable variants: {len(runnable_variants)}")
    logger.info(f"Include clausified runs: {include_clausified_runs}")

    if not runnable_variants:
        logger.info("")
        logger.info("No variants with verified lemmas found.")
        logger.info("Skipping parallel execution.")
        logger.info("=" * 80)
        return {
            "results": [],
            "statistics": {"total_runs": 0, "proved": 0, "timeout": 0, "unknown": 0},
            "proved": [],
        }

    results_dir = problem_output_dir / "results"
    results_dir.mkdir(exist_ok=True)

    runs: List[Tuple[Path, Path, str]] = []

    if original_problem and original_problem.exists():
        runs.append((original_problem, results_dir / "original.out", "original"))

    if include_clausified_runs:
        clausified_dir = problem_output_dir / "clausified"
        clausified_files = list(clausified_dir.glob("*_clausified.*"))
        if clausified_files:
            runs.append(
                (
                    clausified_files[0],
                    results_dir / "original_clausified.out",
                    "original_clausified",
                )
            )

    for variant in runnable_variants:
        runs.append((variant, results_dir / f"{variant.stem}.out", variant.stem))

    logger.info(f"Timeout: {timeout}s per run")
    logger.info(f"Executing {len(runs)} runs in parallel...")
    logger.info("")

    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_vampire_worker,
                str(problem_file),
                str(output_file),
                vampire_binary,
                timeout,
                name,
            ): name
            for problem_file, output_file, name in runs
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            icon = "✓" if result["status"] in ("PROVED", "UNSAT") else "✗"
            logger.info(f"  {icon} {result['message']}")

    def sort_key(item: Dict) -> tuple:
        if item["name"] == "original":
            return (0, item["name"])
        if item["name"] == "original_clausified":
            return (1, item["name"])
        return (2, item["name"])

    results.sort(key=sort_key)

    logger.info("")
    logger.info("=" * 80)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 80)

    proved = [r for r in results if r["status"] in ("PROVED", "UNSAT")]
    timeout_count = sum(1 for r in results if r["status"] == "TIMEOUT")
    unknown_count = sum(1 for r in results if r["status"] == "UNKNOWN")

    for result in results:
        icon = "✓" if result["status"] in ("PROVED", "UNSAT") else "✗"
        logger.info(
            f"  {icon} {result['name']:20s} {result['status']:10s} {result['time']:8.2f}s"
        )

    logger.info("")
    logger.info(f"Proved: {len(proved)}/{len(results)}")
    logger.info(f"Timeout: {timeout_count}/{len(results)}")
    logger.info(f"Unknown: {unknown_count}/{len(results)}")

    if proved:
        logger.info("")
        logger.info("Winners:")
        for item in proved:
            logger.info(f"    {item['name']} in {item['time']:.2f}s")

    summary = {
        "problem": problem_output_dir.name,
        "timestamp": datetime.now().isoformat(),
        "configuration": {
            "timeout": timeout,
            "vampire_binary": vampire_binary,
            "include_clausified_runs": include_clausified_runs,
            "runnable_variants": len(runnable_variants),
        },
        "results": results,
        "statistics": {
            "total_runs": len(results),
            "proved": len(proved),
            "timeout": timeout_count,
            "unknown": unknown_count,
        },
    }

    summary_file = results_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    logger.info("")
    logger.info(f"Results saved to: {results_dir}")
    logger.info("=" * 80)

    return summary
