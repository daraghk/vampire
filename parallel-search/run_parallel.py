#!/usr/bin/env python3
"""Parallel Vampire Execution Module for Parallel Vampire Search.

This module executes Vampire in parallel on the original problem (non-clausified),
the original clausified problem (C₀), and all variants with at least one verified
seed clause. Used by main.py to execute the final evaluation phase of the parallel
search workflow.

The parallel execution workflow:
1. Identify the original problem file (if provided)
2. Identify the clausified original problem (C₀)
3. Identify all variants that have verified seed clauses (from log file)
4. Run Vampire in parallel on:
   - Original problem (non-clausified, if provided)
   - Original clausified problem C₀
   - All variants C_i with verified seeds
5. Capture execution time, exit status, and full Vampire output for each run
6. Generate summary with statistics (proved, timeout, unknown counts)
7. Save results to results/ directory with JSON summary

Only variants with at least one verified seed clause are executed. This ensures
all runs are sound: if any variant C_i is UNSAT, then C₀ is UNSAT.

If no variants have verified seeds, the execution is skipped entirely (no point
comparing the original against nothing).

IMPORTANT:
    - This module only handles Vampire execution, not variant construction.
    - Variants must already exist (created by main.py using B_i and S_i).
    - Seed verification is read from the log file (created by entailment_checker.py).
    - If no verified variants exist, execution is skipped and empty results returned.
    - Results are saved in problem_output_dir/results/ with summary.json.

Used by main.py to run parallel Vampire evaluation (--run-vampire flag).

Usage:
    from run_parallel import run_parallel_evaluation

    # Run Vampire in parallel on all valid variants
    summary = run_parallel_evaluation(
        problem_output_dir=Path("output/2026-01-07_17-26-25_PUZ139_1"),
        logger=logger,
        vampire_binary="../build/vampire",
        timeout=60,
        max_workers=None,  # Auto-detect
        original_problem=Path("problem.p")  # Optional: original non-clausified problem
    )

    # Check results
    if summary["statistics"]["proved"] > 0:
        print(f"Found proof! {summary['proved']}")
"""

import json
import logging
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def has_verified_seeds(variant_path: Path, log_file: Path) -> bool:
    """Check if a variant has at least one verified seed clause.

    Args:
        variant_path: Path to variant file.
        log_file: Path to the problem's log file.

    Returns:
        True if variant has verified seeds, False otherwise.
    """
    variant_name = variant_path.stem  # e.g., "variant_0"
    variant_num = variant_name.split("_")[1]

    # Read log and check for verified seeds in this variant
    with open(log_file, "r") as f:
        content = f.read()

    # Look for pattern: "VARIANT {num} SEED ..." followed by "✓ Entailment verified"
    import re

    pattern = rf"VARIANT {variant_num} SEED \d+.*?(?:✓ Entailment verified|✗ Entailment check failed)"
    matches = re.findall(pattern, content, re.DOTALL)

    for match in matches:
        if "✓ Entailment verified" in match:
            return True

    return False


def run_vampire(
    problem_file: Path,
    output_file: Path,
    vampire_binary: str,
    timeout: Optional[int],
    logger: logging.Logger,
    name: str,
) -> Dict:
    """Run Vampire on a single problem and capture results.

    Args:
        problem_file: Path to TPTP problem file.
        output_file: Path to save Vampire output.
        vampire_binary: Path to Vampire executable.
        timeout: Timeout in seconds passed to Vampire via -t flag (None for no timeout).
        logger: Logger instance.
        name: Name for logging (e.g., "original", "variant_0").

    Returns:
        Dictionary with execution results containing:
        - name: Run identifier
        - status: PROVED/UNSAT/SAT/TIMEOUT/UNKNOWN/ERROR
        - time: Execution time in seconds
        - exit_code: Vampire exit code
        - output_file: Path to output file
    """
    start_time = time.time()

    logger.info(f"  Starting Vampire: {name}")

    try:
        # Build command with timeout flag for Vampire
        cmd = [vampire_binary, str(problem_file)]
        if timeout:
            cmd.extend(["-t", str(timeout)])

        logger.debug(f"    Command: {' '.join(cmd)}")

        # Use slightly longer subprocess timeout as backup
        subprocess_timeout = timeout + 5 if timeout else None

        result = subprocess.run(
            cmd + ["--mode", "casc"],
            # cmd,
            capture_output=True,
            text=True,
            timeout=subprocess_timeout,
        )

        elapsed = time.time() - start_time

        # Write output to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n=== STDERR ===\n")
                f.write(result.stderr)

        # Determine status from output
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

        logger.info(f"    ✓ {name}: {status} in {elapsed:.2f}s")

        return {
            "name": name,
            "status": status,
            "time": elapsed,
            "exit_code": result.returncode,
            "output_file": str(output_file),
        }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.info(f"    ✗ {name}: TIMEOUT after {timeout}s")

        with open(output_file, "w") as f:
            f.write(f"Vampire execution timed out after {timeout} seconds\n")

        return {
            "name": name,
            "status": "TIMEOUT",
            "time": elapsed,
            "exit_code": None,
            "output_file": str(output_file),
        }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"    ✗ {name}: ERROR - {e}")

        with open(output_file, "w") as f:
            f.write(f"Error running Vampire: {e}\n")

        return {
            "name": name,
            "status": "ERROR",
            "time": elapsed,
            "exit_code": None,
            "output_file": str(output_file),
            "error": str(e),
        }


def run_parallel_evaluation(
    problem_output_dir: Path,
    logger: logging.Logger,
    vampire_binary: str = "../build/vampire",
    timeout: int = 60,
    max_workers: Optional[int] = None,
    original_problem: Optional[Path] = None,
) -> Dict:
    """Run Vampire in parallel on original problem and variants with verified seeds.

    If no variants have verified seeds, execution is skipped (no point comparing
    original against nothing).

    Args:
        problem_output_dir: Path to problem output directory.
        logger: Logger instance.
        vampire_binary: Path to Vampire executable.
        timeout: Timeout per run in seconds.
        max_workers: Max parallel workers (None for auto-detect).
        original_problem: Path to original problem file (non-clausified). If provided,
            this will also be run in parallel.

    Returns:
        Dictionary with evaluation results containing:
        - results: List of individual run results
        - statistics: Summary statistics
        - proved: List of runs that proved the problem
        Returns empty dict if no verified variants exist.
    """
    # Find clausified problem
    clausified_dir = problem_output_dir / "clausified"
    clausified_files = list(clausified_dir.glob("*_clausified.*"))
    if not clausified_files:
        logger.error(f"No clausified problem found in {clausified_dir}")
        return {"results": [], "statistics": {}, "proved": []}

    original_clausified_problem = clausified_files[0]

    # Find variants
    variants_dir = problem_output_dir / "variants"
    all_variants = sorted(variants_dir.glob("variant_*.tptp"))

    # Find log file to check for verified seeds
    log_files = list(problem_output_dir.glob("*.log"))
    if not log_files:
        logger.warning("No log file found, will run all variants")
        verified_variants = all_variants
    else:
        log_file = log_files[0]
        verified_variants = [v for v in all_variants if has_verified_seeds(v, log_file)]

    logger.info("")
    logger.info("=" * 80)
    logger.info("PARALLEL VAMPIRE EVALUATION")
    logger.info("=" * 80)
    if original_problem and original_problem.exists():
        logger.info(f"Original problem: {original_problem.name}")
    logger.info(f"Original clausified problem: {original_clausified_problem.name}")
    logger.info(f"Total variants: {len(all_variants)}")
    logger.info(f"Variants with verified seeds: {len(verified_variants)}")

    # Skip execution if no verified variants
    if len(verified_variants) == 0:
        logger.info("")
        logger.info("No variants with verified seeds found.")
        logger.info(
            "Skipping parallel execution (nothing to compare against original)."
        )
        logger.info("=" * 80)
        return {
            "results": [],
            "statistics": {"total_runs": 0, "proved": 0, "timeout": 0, "unknown": 0},
            "proved": [],
        }

    logger.info(f"Timeout: {timeout}s per run")
    logger.info("")

    # Create results directory
    results_dir = problem_output_dir / "results"
    results_dir.mkdir(exist_ok=True)

    # Prepare runs
    runs = []

    # Original problem (non-clausified) if provided
    if original_problem and original_problem.exists():
        runs.append(
            (
                original_problem,
                results_dir / "original.out",
                vampire_binary,
                timeout,
                "original",
            )
        )

    # Original clausified problem
    runs.append(
        (
            original_clausified_problem,
            results_dir / "original_clausified.out",
            vampire_binary,
            timeout,
            "original_clausified",
        )
    )

    # Variants with verified seeds
    for variant in verified_variants:
        variant_name = variant.stem
        runs.append(
            (
                variant,
                results_dir / f"{variant_name}.out",
                vampire_binary,
                timeout,
                variant_name,
            )
        )

    logger.info(f"Executing {len(runs)} runs in parallel...")

    # Execute in parallel
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        futures = {
            executor.submit(
                run_vampire,
                problem_file,
                output_file,
                vampire_binary,
                timeout,
                logger,
                name,
            ): name
            for problem_file, output_file, vampire_binary, timeout, name in runs
        }

        # Collect results as they complete
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    # Sort results: original first, then original_clausified, then variants
    def sort_key(x):
        if x["name"] == "original":
            return (0, x["name"])
        elif x["name"] == "original_clausified":
            return (1, x["name"])
        else:
            return (2, x["name"])
    
    results.sort(key=sort_key)

    # Generate summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 80)

    proved = [r for r in results if r["status"] in ["PROVED", "UNSAT"]]
    timeout_count = len([r for r in results if r["status"] == "TIMEOUT"])
    unknown_count = len([r for r in results if r["status"] == "UNKNOWN"])

    for result in results:
        status_icon = "✓" if result["status"] in ["PROVED", "UNSAT"] else "✗"
        logger.info(
            f"  {status_icon} {result['name']:20s} {result['status']:10s} {result['time']:8.2f}s"
        )

    logger.info("")
    logger.info(f"Proved: {len(proved)}/{len(results)}")
    logger.info(f"Timeout: {timeout_count}/{len(results)}")
    logger.info(f"Unknown: {unknown_count}/{len(results)}")

    if proved:
        logger.info("")
        logger.info("✓ Winners:")
        for r in proved:
            logger.info(f"    {r['name']} in {r['time']:.2f}s")

    # Save JSON summary
    summary = {
        "problem": problem_output_dir.name,
        "timestamp": datetime.now().isoformat(),
        "configuration": {
            "timeout": timeout,
            "vampire_binary": vampire_binary,
            "total_variants": len(all_variants),
            "variants_with_seeds": len(verified_variants),
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
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("")
    logger.info(f"Results saved to: {results_dir}")
    logger.info("=" * 80)

    return summary
