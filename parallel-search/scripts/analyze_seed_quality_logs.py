#!/usr/bin/env python3
"""Analyze seed quality and entailment outcomes from run log files.

This script scans log files produced by `main.py` and extracts metrics about:
- Seed generation counts
- Strict syntactic validity
- Entailment outcomes for strictly valid seeds

Default behavior is tuned for:
    output/results/vampire-5.0-results-GRP-655/**/*.log

Output is one CSV row per problem, aggregated across all variants.

Strict syntactic validity (used in this script):
- Excludes seeds with post-entailment parse rejection:
  `Failed to parse seed clause, skipping`
- Excludes seeds with entailment-stage syntax/type errors:
  parser/lexer exceptions or Vampire user errors (e.g., unquantified variables,
  undeclared type constructors, sort mismatch).

CSV columns:
- Problem_Name
- Logs_Processed
- Generated_Seeds_Total
- Strict_Syntactically_Correct_Seeds
- Strict_Syntactic_Quality_Rate
- Entailed_Seeds_From_Strict
- Entailment_Rate_Given_Strict_Syntax
- Post_Parse_Failures
- Entailment_SyntaxOrType_Failures
- Entailment_Timeout_Failures
- Entailment_SAT_Not_Entailed
- Entailment_Other_Failures
"""

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


# Regex patterns for known log events.
PROBLEM_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_(.+)")
GENERATED_RE = re.compile(r"Generated\s+(\d+)\s+seed clause suggestions")
SEED_HEADER_RE = re.compile(r"VARIANT\s+(\d+)\s+SEED\s+(\d+)")


@dataclass
class SeedRecord:
    """Per-seed state extracted from a log."""

    variant_index: int
    seed_index: int
    post_parse_failed: bool = False
    entailed: bool = False
    entailment_failed: bool = False
    entailment_timeout: bool = False
    entailment_sat_not_entailed: bool = False
    entailment_syntax_or_type_error: bool = False
    entailment_other_error: bool = False


@dataclass
class ProblemMetrics:
    """Aggregated metrics for one problem across one or more logs."""

    logs_processed: int = 0
    generated_seeds_total: int = 0
    strict_syntactically_correct_seeds: int = 0
    entailed_seeds_from_strict: int = 0
    post_parse_failures: int = 0
    entailment_syntax_or_type_failures: int = 0
    entailment_timeout_failures: int = 0
    entailment_sat_not_entailed: int = 0
    entailment_other_failures: int = 0


def extract_problem_name(name: str) -> str:
    """Extract problem name from timestamped filename stem/directory name."""
    match = PROBLEM_RE.match(name)
    return match.group(1) if match else name


def discover_logs(logs_root: Path) -> List[Path]:
    """Recursively discover `.log` files under the root path."""
    if not logs_root.exists():
        return []
    return sorted(p for p in logs_root.rglob("*.log") if p.is_file())


def _classify_seed_block(record: SeedRecord, block_lines: List[str]) -> None:
    """Classify seed-level outcomes from one seed block."""
    joined = "\n".join(block_lines)

    if "✓ Entailment verified (C_ax ⊨ s)" in joined:
        record.entailed = True

    if "✗ Entailment check failed, skipping seed" in joined:
        record.entailment_failed = True

    if "Failed to parse seed clause, skipping" in joined:
        record.post_parse_failed = True

    if "Entailment check timeout after" in joined:
        record.entailment_timeout = True

    if "Entailment check result: SAT (not entailed)" in joined:
        record.entailment_sat_not_entailed = True

    syntax_or_type_markers = [
        "Parser exception:",
        "Lexer exception:",
        "% User error:",
        "unquantified variable detected",
        "Undeclared type constructor",
        "is not an instance of sort",
        "parse error in",
    ]
    if any(marker in joined for marker in syntax_or_type_markers):
        record.entailment_syntax_or_type_error = True

    if (
        record.entailment_failed
        and not record.entailment_timeout
        and not record.entailment_sat_not_entailed
        and not record.entailment_syntax_or_type_error
    ):
        record.entailment_other_error = True


def parse_log_file(log_path: Path) -> Tuple[str, ProblemMetrics]:
    """Parse one log file and compute metrics for its problem."""
    problem_name = extract_problem_name(log_path.stem)
    generated_seed_counts: List[int] = []
    seed_records: Dict[Tuple[int, int], SeedRecord] = {}
    current_seed_key: Optional[Tuple[int, int]] = None
    current_seed_lines: List[str] = []

    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()

            # Generated seed counts (one per variant when generation succeeds).
            generated_match = GENERATED_RE.search(line)
            if generated_match:
                generated_seed_counts.append(int(generated_match.group(1)))

            # Enter a specific seed block.
            seed_match = SEED_HEADER_RE.search(line)
            if seed_match:
                if current_seed_key is not None:
                    _classify_seed_block(seed_records[current_seed_key], current_seed_lines)
                variant_index = int(seed_match.group(1))
                seed_index = int(seed_match.group(2))
                current_seed_key = (variant_index, seed_index)
                seed_records.setdefault(
                    current_seed_key,
                    SeedRecord(variant_index=variant_index, seed_index=seed_index),
                )
                current_seed_lines = [line]
                continue

            # Seed-level events are attributed to the current seed block.
            if current_seed_key is None:
                continue

            current_seed_lines.append(line)

    if current_seed_key is not None:
        _classify_seed_block(seed_records[current_seed_key], current_seed_lines)

    metrics = ProblemMetrics(logs_processed=1)

    # Prefer explicit per-seed records when present. Fallback to generated counts.
    if seed_records:
        metrics.generated_seeds_total = len(seed_records)
        metrics.post_parse_failures = sum(
            1 for seed in seed_records.values() if seed.post_parse_failed
        )
        metrics.entailment_syntax_or_type_failures = sum(
            1
            for seed in seed_records.values()
            if seed.entailment_syntax_or_type_error
        )
        metrics.entailment_timeout_failures = sum(
            1 for seed in seed_records.values() if seed.entailment_timeout
        )
        metrics.entailment_sat_not_entailed = sum(
            1 for seed in seed_records.values() if seed.entailment_sat_not_entailed
        )
        metrics.entailment_other_failures = sum(
            1 for seed in seed_records.values() if seed.entailment_other_error
        )

        # Strict syntactic validity excludes both post-parse failures and
        # entailment-stage syntax/type failures.
        metrics.strict_syntactically_correct_seeds = sum(
            1
            for seed in seed_records.values()
            if not seed.post_parse_failed and not seed.entailment_syntax_or_type_error
        )
        metrics.entailed_seeds_from_strict = sum(
            1
            for seed in seed_records.values()
            if seed.entailed
            and not seed.post_parse_failed
            and not seed.entailment_syntax_or_type_error
        )
    else:
        metrics.generated_seeds_total = sum(generated_seed_counts)
        metrics.strict_syntactically_correct_seeds = metrics.generated_seeds_total
        metrics.entailed_seeds_from_strict = 0
        metrics.post_parse_failures = 0
        metrics.entailment_syntax_or_type_failures = 0
        metrics.entailment_timeout_failures = 0
        metrics.entailment_sat_not_entailed = 0
        metrics.entailment_other_failures = 0

    return problem_name, metrics


def merge_metrics(target: ProblemMetrics, incoming: ProblemMetrics) -> None:
    """Merge one metrics object into another."""
    target.logs_processed += incoming.logs_processed
    target.generated_seeds_total += incoming.generated_seeds_total
    target.strict_syntactically_correct_seeds += incoming.strict_syntactically_correct_seeds
    target.entailed_seeds_from_strict += incoming.entailed_seeds_from_strict
    target.post_parse_failures += incoming.post_parse_failures
    target.entailment_syntax_or_type_failures += incoming.entailment_syntax_or_type_failures
    target.entailment_timeout_failures += incoming.entailment_timeout_failures
    target.entailment_sat_not_entailed += incoming.entailment_sat_not_entailed
    target.entailment_other_failures += incoming.entailment_other_failures


def safe_rate(numerator: int, denominator: int) -> str:
    """Return decimal string for a ratio, or N/A when undefined."""
    if denominator <= 0:
        return "N/A"
    return f"{(numerator / denominator):.4f}"


def write_csv(results: Dict[str, ProblemMetrics], output_file: Path) -> None:
    """Write aggregated metrics to CSV."""
    columns = [
        "Problem_Name",
        "Logs_Processed",
        "Generated_Seeds_Total",
        "Strict_Syntactically_Correct_Seeds",
        "Strict_Syntactic_Quality_Rate",
        "Entailed_Seeds_From_Strict",
        "Entailment_Rate_Given_Strict_Syntax",
        "Post_Parse_Failures",
        "Entailment_SyntaxOrType_Failures",
        "Entailment_Timeout_Failures",
        "Entailment_SAT_Not_Entailed",
        "Entailment_Other_Failures",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()

        for problem_name in sorted(results.keys()):
            metrics = results[problem_name]
            writer.writerow(
                {
                    "Problem_Name": problem_name,
                    "Logs_Processed": metrics.logs_processed,
                    "Generated_Seeds_Total": metrics.generated_seeds_total,
                    "Strict_Syntactically_Correct_Seeds": metrics.strict_syntactically_correct_seeds,
                    "Strict_Syntactic_Quality_Rate": safe_rate(
                        metrics.strict_syntactically_correct_seeds,
                        metrics.generated_seeds_total,
                    ),
                    "Entailed_Seeds_From_Strict": metrics.entailed_seeds_from_strict,
                    "Entailment_Rate_Given_Strict_Syntax": safe_rate(
                        metrics.entailed_seeds_from_strict,
                        metrics.strict_syntactically_correct_seeds,
                    ),
                    "Post_Parse_Failures": metrics.post_parse_failures,
                    "Entailment_SyntaxOrType_Failures": metrics.entailment_syntax_or_type_failures,
                    "Entailment_Timeout_Failures": metrics.entailment_timeout_failures,
                    "Entailment_SAT_Not_Entailed": metrics.entailment_sat_not_entailed,
                    "Entailment_Other_Failures": metrics.entailment_other_failures,
                }
            )


def analyze_logs(log_paths: Iterable[Path]) -> Dict[str, ProblemMetrics]:
    """Parse and aggregate metrics across many logs."""
    aggregated: Dict[str, ProblemMetrics] = {}
    for log_path in log_paths:
        problem_name, metrics = parse_log_file(log_path)
        aggregated.setdefault(problem_name, ProblemMetrics())
        merge_metrics(aggregated[problem_name], metrics)
    return aggregated


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze run logs for strict seed syntactic quality and entailment rate. "
            "Strict syntax excludes both post-parse failures and entailment-stage "
            "syntax/type errors."
        )
    )
    parser.add_argument(
        "--logs-root",
        type=Path,
        default=Path("output/results/vampire-5.0-results-GRP-655"),
        help="Root directory containing run logs (default: output/results/vampire-5.0-results-GRP-655).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("seed_quality_results_strict.csv"),
        help="Output CSV file path (default: seed_quality_results_strict.csv).",
    )
    return parser.parse_args()


def main() -> int:
    """Run analysis and write CSV output."""
    args = parse_args()
    logs = discover_logs(args.logs_root)

    if not logs:
        print(f"No log files found under: {args.logs_root}")
        return 1

    print(f"Scanning {len(logs)} log files under {args.logs_root}...")
    aggregated = analyze_logs(logs)
    write_csv(aggregated, args.output)
    print(f"Wrote {len(aggregated)} problem rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
