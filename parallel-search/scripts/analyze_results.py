#!/usr/bin/env python3
"""Analysis script for parallel Vampire search results.

This script iterates over all output directories and extracts evaluation results
from summary.json files, outputting them in CSV format for easy analysis.

The script:
- Scans all problem directories in the output folder
- Parses summary.json files to extract evaluation results
- Creates a CSV with columns for each variant type found
- Includes all problems, even those without evaluation results (marked as "N/A")

CSV column structure:
- Problem_Name: Extracted problem name (timestamp prefix removed)
- Original_Status, Original_Time: Status and execution time (seconds) for original (non-clausified) problem
- Original_Clausified_Status, Original_Clausified_Time: Status and execution time (seconds) for original clausified problem (C₀)
- Variant_X_Status, Variant_X_Time: Status and execution time (seconds) for clausified variant X
- Variant_X_Original_Status, Variant_X_Original_Time: Status and execution time (seconds) for original (non-clausified) variant X

Status values: PROVED, TIMEOUT, UNKNOWN
Time values: Execution time in seconds (float)
Missing data is represented as "N/A" in both Status and Time columns.

Usage:
    python analyze_results.py [--output OUTPUT.csv] [--output-dir OUTPUT_DIR]

Examples:
    # Analyze results in default output directory
    python analyze_results.py

    # Specify custom output directory and CSV file
    python analyze_results.py --output-dir output --output results.csv
"""

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from parallel_search.analysis.discovery import discover_problem_directories


def extract_problem_name(directory_name: str) -> str:
    """Extract problem name from timestamped directory name.

    Args:
        directory_name: Directory name like "2026-01-19_13-20-17_GRP441-1"

    Returns:
        Problem name like "GRP441-1"
    """
    # Pattern: YYYY-MM-DD_HH-MM-SS_PROBLEMNAME
    # Extract everything after the last underscore that follows a timestamp pattern
    match = re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_(.+)", directory_name)
    if match:
        return match.group(1)
    # Fallback: return as-is if pattern doesn't match
    return directory_name


def parse_summary_json(summary_path: Path) -> Optional[Dict]:
    """Parse summary.json file and return results data.

    Args:
        summary_path: Path to summary.json file.

    Returns:
        Dictionary with keys:
        - "problem_name": Extracted problem name (str)
        - "results": Dictionary mapping variant names to (status, time) tuples
        Returns None if parsing fails.
    """
    try:
        with open(summary_path, "r") as f:
            data = json.load(f)

        # Extract problem name from the "problem" field or directory
        problem_full = data.get("problem", "")
        problem_name = extract_problem_name(problem_full)

        # Get results array
        results = data.get("results", [])

        # Create a mapping of run name to (status, time)
        results_dict = {}
        for result in results:
            name = result.get("name", "")
            status = result.get("status", "UNKNOWN")
            time = result.get("time", 0.0)
            results_dict[name] = (status, time)

        return {"problem_name": problem_name, "results": results_dict}
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        print(f"Warning: Failed to parse {summary_path}: {e}")
        return None


def collect_all_variant_names(output_dir: Path) -> Set[str]:
    """Collect all unique variant names across all problems.

    Args:
        output_dir: Path to output directory.

    Returns:
        Set of all unique variant names found.
    """
    variant_names = set()

    for problem_dir in discover_problem_directories(output_dir):
        summary_path = problem_dir / "results" / "summary.json"
        data = parse_summary_json(summary_path)
        if data:
            variant_names.update(data["results"].keys())

    return variant_names


def variant_name_to_base_name(variant_name: str) -> str:
    """Convert variant name to base column name.

    Args:
        variant_name: Variant name from summary.json (e.g., "variant_0_original").

    Returns:
        Base column name (e.g., "Variant_0_Original").
    """
    if variant_name == "original":
        return "Original"
    elif variant_name == "original_clausified":
        return "Original_Clausified"
    elif variant_name.startswith("variant_") and not variant_name.endswith("_original"):
        return variant_name.replace("variant_", "Variant_")
    elif variant_name.endswith("_original") and variant_name.startswith("variant_"):
        # Convert variant_0_original to Variant_0_Original
        parts = variant_name.replace("variant_", "Variant_").split("_")
        if len(parts) == 3:
            return f"{parts[0]}_{parts[1]}_{parts[2].capitalize()}"
        else:
            return variant_name.replace("variant_", "Variant_")
    else:
        return variant_name


def get_ordered_columns(variant_names: Set[str]) -> List[str]:
    """Get ordered list of column names for CSV (Status and Time pairs).

    Args:
        variant_names: Set of all variant names.

    Returns:
        Ordered list of column names, with Status and Time columns for each variant.
        Format: Problem_Name, then pairs of {Variant}_Status, {Variant}_Time for each variant.
    """
    # Standard columns first
    columns = ["Problem_Name"]

    # Special cases: original and original_clausified first
    special_variants = []
    if "original" in variant_names:
        special_variants.append("original")
    if "original_clausified" in variant_names:
        special_variants.append("original_clausified")

    # Regular variants (variant_0, variant_1, etc.)
    regular_variants = sorted(
        [
            v
            for v in variant_names
            if v.startswith("variant_") and not v.endswith("_original")
        ]
    )

    # Original variants (variant_0_original, variant_1_original, etc.)
    original_variants = sorted(
        [
            v
            for v in variant_names
            if v.endswith("_original") and v.startswith("variant_")
        ]
    )

    # Add columns: special, regular variants, original variants
    # For each variant, add Status and Time columns
    all_variants_ordered = special_variants + regular_variants + original_variants

    for variant_name in all_variants_ordered:
        base_name = variant_name_to_base_name(variant_name)
        columns.append(f"{base_name}_Status")
        columns.append(f"{base_name}_Time")

    return columns


def analyze_results(output_dir: Path, output_file: Path):
    """Analyze all results and write to CSV.

    Args:
        output_dir: Path to output directory.
        output_file: Path to output CSV file.
    """
    # Collect all variant names first
    print(f"Scanning {output_dir} for results...")
    all_variant_names = collect_all_variant_names(output_dir)
    print(f"Found {len(all_variant_names)} unique variant types")

    # Get ordered column names (Status and Time pairs)
    columns = get_ordered_columns(all_variant_names)

    # Map variant names to base column names
    variant_to_base = {}
    for variant_name in all_variant_names:
        variant_to_base[variant_name] = variant_name_to_base_name(variant_name)

    # Collect all problem data
    all_problems = []

    for problem_dir in discover_problem_directories(output_dir):
        summary_path = problem_dir / "results" / "summary.json"
        data = parse_summary_json(summary_path)
        if data:
            all_problems.append(data)
        else:
            all_problems.append(
                {
                    "problem_name": extract_problem_name(problem_dir.name),
                    "results": {},
                }
            )

    print(f"Found {len(all_problems)} problems")

    # Write CSV
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(columns)

        # Write data rows
        for problem_data in all_problems:
            row = [problem_data["problem_name"]]
            results = problem_data["results"]

            # Fill in data for each column (skip Problem_Name)
            # Columns come in pairs: Status, Time
            for col in columns[1:]:
                # Extract base name from column (remove _Status or _Time suffix)
                if col.endswith("_Status"):
                    base_name = col[:-7]  # Remove "_Status"

                    # Find the variant name that maps to this base name
                    variant_name = None
                    for vname, base in variant_to_base.items():
                        if base == base_name:
                            variant_name = vname
                            break

                    # Add Status value
                    if variant_name and variant_name in results:
                        status, _ = results[variant_name]
                        row.append(status)
                    else:
                        row.append("N/A")

                elif col.endswith("_Time"):
                    base_name = col[:-5]  # Remove "_Time"

                    # Find the variant name that maps to this base name
                    variant_name = None
                    for vname, base in variant_to_base.items():
                        if base == base_name:
                            variant_name = vname
                            break

                    # Add Time value
                    if variant_name and variant_name in results:
                        _, time = results[variant_name]
                        row.append(f"{time:.2f}")
                    else:
                        row.append("N/A")
                else:
                    # Should not happen, but handle gracefully
                    row.append("N/A")

            writer.writerow(row)

    print(f"Results written to {output_file}")
    print(f"Total problems: {len(all_problems)}")
    print(f"Problems with results: {sum(1 for p in all_problems if p['results'])}")
    print(
        f"Problems without results: {sum(1 for p in all_problems if not p['results'])}"
    )


def main():
    """Main entry point for the results analysis script.

    Parses command-line arguments, analyzes all results in the output directory,
    and writes a CSV file with evaluation results.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Analyze parallel Vampire search results and output CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze results in default output directory
  python analyze_results.py

  # GRP-655 flat bundle layout
  python analyze_results.py --output-dir output/results/vampire-5.0-results-GRP-655

  # Specify custom output directory and CSV file
  python analyze_results.py --output-dir output --output results.csv
        """,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation_results.csv"),
        help="Output CSV file path (default: evaluation_results.csv)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory to analyze (default: output)",
    )

    args = parser.parse_args()

    if not args.output_dir.exists():
        print(f"Error: Output directory not found: {args.output_dir}")
        return 1

    analyze_results(args.output_dir, args.output)
    return 0


if __name__ == "__main__":
    exit(main())
