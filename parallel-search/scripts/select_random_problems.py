#!/usr/bin/env python3
"""Problem selection utility for parallel Vampire search.

This utility selects random TPTP problems from the Problems/all-problems/
directory and copies them to the input/ folder for batch processing with
``scripts/main.py``.

The script supports:
- Random selection of N problems from the complete TPTP problem set (26,000+ problems)
- Optional filtering by problem type/domain (e.g., ARI, BOO, GRP, etc.)
- Automatic filtering of large problems (>1500 lines by default)
- Automatic filtering of problems with include statements (require external axiom files)
- Optional clearing of the input directory before copying
- Reproducible selection via random seed
- Customizable paths for problems and input directories

This is a preprocessing step before running the main parallel search workflow. Use
this script to prepare problem sets for experimentation, especially when testing
different strategies, configurations, or parameter sweeps.

Typical workflow:
    1. Use this script to select random problems → input/
    2. Run ``scripts/main.py`` on input/ directory to process all problems
    3. Analyze results in output/ directory

Usage (run from ``parallel-search/``):
    python3 scripts/select_random_problems.py <num_problems> [--clear] [--seed SEED]

Arguments:
    num_problems: Number of random problems to select
    --clear: Clear the input folder before copying (default: False)
    --seed: Random seed for reproducibility (optional)
    --max-lines: Maximum lines per problem file (default: 1500)
    --type: Problem type/domain to select from (e.g., ARI, BOO, GRP)
    --problems-dir: Custom path to Problems directory (optional)
    --input-dir: Custom path to input directory (optional)

Examples:
    # Select 10 random problems from all domains (max 1500 lines each)
    python3 scripts/select_random_problems.py 10

    # Select 20 arithmetic problems only
    python3 scripts/select_random_problems.py 20 --type ARI

    # Select 50 boolean algebra problems, clearing input folder first
    python3 scripts/select_random_problems.py 50 --type BOO --clear

    # Select 100 problems with reproducible seed for experiments
    python3 scripts/select_random_problems.py 100 --seed 42

    # Select 15 group theory problems, allowing larger files
    python3 scripts/select_random_problems.py 15 --type GRP --max-lines 5000
"""

import argparse
import random
import shutil
from pathlib import Path
from typing import List


def count_lines(file_path: Path) -> int:
    """Count the number of lines in a file.

    Args:
        file_path: Path to the file to count lines in.

    Returns:
        Number of lines in the file.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        # If we can't read the file, assume it's too large or problematic
        return float("inf")


def get_all_problems(problems_dir: Path, problem_type: str = None) -> List[Path]:
    """Get all .p files from the all-problems directory or a specific problem type subdirectory.

    Args:
        problems_dir: Path to the Problems directory containing subdirectories.
        problem_type: Optional problem type/domain (e.g., 'ARI', 'BOO', 'GRP').
                     If None, selects from all-problems/. If specified, selects
                     from the corresponding subdirectory (e.g., Problems/ARI/).

    Returns:
        List of Path objects for all .p files found in the target directory.

    Raises:
        FileNotFoundError: If the target directory doesn't exist or contains no .p files.
    """
    if problem_type:
        # Select from specific problem type subdirectory
        target_dir = problems_dir / problem_type.upper()
        if not target_dir.exists():
            raise FileNotFoundError(
                f"Problem type directory not found: {target_dir}\n"
                f"Available types: {', '.join(sorted([d.name for d in problems_dir.iterdir() if d.is_dir() and d.name != 'all-problems']))}"
            )
    else:
        # Select from all-problems directory
        target_dir = problems_dir / "all-problems"
        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {target_dir}")

    problems = list(target_dir.glob("*.p"))

    if not problems:
        raise FileNotFoundError(f"No .p files found in {target_dir}")

    return problems


def has_include_statements(file_path: Path) -> bool:
    """Check if a problem file contains include statements.

    Args:
        file_path: Path to the problem file to check.

    Returns:
        True if the file contains include statements, False otherwise.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Check for include statements (case-insensitive, handles whitespace)
                stripped = line.strip().lower()
                if stripped.startswith("include(") or stripped.startswith("include "):
                    return True
        return False
    except Exception:
        # If we can't read the file, assume it has includes to be safe
        return True


def filter_problems_by_include(problems: List[Path]) -> tuple:
    """Filter out problems that contain include statements.

    Args:
        problems: List of problem files to filter.

    Returns:
        Tuple of (filtered_problems, excluded_count) where filtered_problems
        contains only problems without include statements, and excluded_count is
        the number of problems that were filtered out.
    """
    filtered = []
    excluded = 0

    print("Filtering problems with include statements...")

    for problem in problems:
        if not has_include_statements(problem):
            filtered.append(problem)
        else:
            excluded += 1
            if excluded <= 5:  # Show first 5 excluded problems
                print(f"  Excluded: {problem.name} (contains include statements)")

    if excluded > 5:
        print(f"  ... and {excluded - 5} more excluded problems")

    return filtered, excluded


def filter_problems_by_size(problems: List[Path], max_lines: int) -> tuple:
    """Filter out problems that exceed the maximum line count.

    Args:
        problems: List of problem files to filter.
        max_lines: Maximum number of lines allowed per problem.

    Returns:
        Tuple of (filtered_problems, excluded_count) where filtered_problems
        contains only problems within the size limit, and excluded_count is
        the number of problems that were filtered out.
    """
    filtered = []
    excluded = 0

    print(f"Filtering problems by size (max {max_lines} lines)...")

    for problem in problems:
        line_count = count_lines(problem)
        if line_count <= max_lines:
            filtered.append(problem)
        else:
            excluded += 1
            if excluded <= 5:  # Show first 5 excluded problems
                print(f"  Excluded: {problem.name} ({line_count} lines)")

    if excluded > 5:
        print(f"  ... and {excluded - 5} more excluded problems")

    return filtered, excluded


def select_random_problems(
    all_problems: List[Path], num_problems: int, seed: int = None
) -> List[Path]:
    """Randomly select a subset of problems from the complete problem list.

    Args:
        all_problems: List of all available problem files.
        num_problems: Number of problems to select.
        seed: Optional random seed for reproducible selection.

    Returns:
        List of randomly selected problem paths. If num_problems exceeds the
        available problems, returns all available problems.
    """
    if seed is not None:
        random.seed(seed)

    if num_problems > len(all_problems):
        print(
            f"Warning: Requested {num_problems} problems but only {len(all_problems)} available."
        )
        print(f"Selecting all {len(all_problems)} problems.")
        return all_problems

    return random.sample(all_problems, num_problems)


def copy_problems_to_input(
    selected_problems: List[Path], input_dir: Path, clear: bool = False
) -> tuple:
    """Copy selected problems to the input directory.

    Args:
        selected_problems: List of problem files to copy.
        input_dir: Destination directory for the problems.
        clear: If True, remove all existing .p files from input_dir before copying.

    Returns:
        Tuple of (copied_count, skipped_count) indicating how many files were
        copied and how many were skipped (already existed).
    """
    # Create input directory if it doesn't exist
    input_dir.mkdir(exist_ok=True)

    # Clear input directory if requested
    if clear:
        print(f"Clearing input directory: {input_dir}")
        for file in input_dir.glob("*.p"):
            file.unlink()

    # Copy problems
    copied = 0
    skipped = 0

    for problem in selected_problems:
        dest = input_dir / problem.name

        if dest.exists():
            print(f"  Skipping (already exists): {problem.name}")
            skipped += 1
            continue

        shutil.copy2(problem, dest)
        copied += 1

    return copied, skipped


def main():
    """Main entry point for the problem selection utility.

    Parses command-line arguments, selects random problems from all-problems/,
    and copies them to the input/ directory for batch processing with ``scripts/main.py``.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Select random TPTP problems and copy them to the input folder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Select 10 random problems from all domains (max 1500 lines each):
    python3 scripts/select_random_problems.py 10
  
  Select 20 arithmetic problems only:
    python3 scripts/select_random_problems.py 20 --type ARI
  
  Select 50 boolean algebra problems, clearing input folder first:
    python3 scripts/select_random_problems.py 50 --type BOO --clear
  
  Select 100 problems with reproducible seed:
    python3 scripts/select_random_problems.py 100 --seed 42
  
  Select 15 group theory problems, allowing larger files:
    python3 scripts/select_random_problems.py 15 --type GRP --max-lines 5000
        """,
    )

    parser.add_argument(
        "num_problems", type=int, help="Number of random problems to select"
    )

    parser.add_argument(
        "--clear", action="store_true", help="Clear the input folder before copying"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (optional)",
    )

    parser.add_argument(
        "--problems-dir",
        type=Path,
        default=None,
        help="Path to Problems directory (default: ../Problems relative to script)",
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Path to input directory (default: ./input relative to script)",
    )

    parser.add_argument(
        "--max-lines",
        type=int,
        default=1500,
        help="Maximum number of lines per problem file (default: 1500)",
    )

    parser.add_argument(
        "--type",
        type=str,
        default=None,
        help="Problem type/domain to select from (e.g., ARI, BOO, GRP). If not specified, selects from all problems",
    )

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    problems_dir = args.problems_dir or (script_dir / "Problems")
    input_dir = args.input_dir or (script_dir / "input")

    print("=" * 80)
    print("RANDOM PROBLEM SELECTOR")
    print("=" * 80)
    print(f"Problems directory: {problems_dir}")
    print(f"Input directory: {input_dir}")
    print(f"Number to select: {args.num_problems}")
    print(f"Max lines per problem: {args.max_lines}")
    if args.type:
        print(f"Problem type filter: {args.type.upper()}")
    if args.seed is not None:
        print(f"Random seed: {args.seed}")
    print()

    try:
        # Get all available problems
        all_problems = get_all_problems(problems_dir, args.type)
        if args.type:
            print(
                f"Found {len(all_problems)} problems in {args.type.upper()}/ directory"
            )
        else:
            print(f"Found {len(all_problems)} problems in all-problems/")

        # Filter by include statements first
        filtered_problems, excluded_includes = filter_problems_by_include(all_problems)
        print(
            f"After filtering includes: {len(filtered_problems)} problems available ({excluded_includes} excluded)"
        )
        print()

        # Filter by size
        filtered_problems, excluded_size = filter_problems_by_size(
            filtered_problems, args.max_lines
        )
        print(
            f"After filtering by size: {len(filtered_problems)} problems available ({excluded_size} excluded)"
        )
        print()

        # Select random subset
        selected = select_random_problems(
            filtered_problems, args.num_problems, args.seed
        )
        print(f"Selected {len(selected)} random problems")
        print()

        # Copy to input directory
        print(f"Copying problems to {input_dir}...")
        copied, skipped = copy_problems_to_input(selected, input_dir, args.clear)

        print()
        print("=" * 80)
        print("SUMMARY:")
        print(f"  Total problems scanned: {len(all_problems)}")
        print(f"  Excluded (has includes): {excluded_includes}")
        print(f"  Excluded (too large): {excluded_size}")
        print(f"  Available after filtering: {len(filtered_problems)}")
        print(f"  ✓ Copied: {copied}")
        if skipped > 0:
            print(f"  - Skipped (already exist): {skipped}")
        print(f"  Total in input/: {len(list(input_dir.glob('*.p')))}")
        print("=" * 80)

        # Show sample of copied files
        if copied > 0:
            print()
            print("Sample of selected problems:")
            for i, problem in enumerate(selected[:10], 1):
                print(f"  {i}. {problem.name}")
            if len(selected) > 10:
                print(f"  ... and {len(selected) - 10} more")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
