#!/usr/bin/env python3
"""Main script for parallel Vampire search workflow.

This script orchestrates the complete workflow:
1. Clausify problems (convert to TFF using Vampire's tclausify mode)
2. Construct base clause sets B_i using various selection strategies
3. Optionally generate seed clauses S_i using LLM (--generate-seeds)
4. Optionally verify entailment C₀ ⊨ s using Vampire (--check-entailment)
5. Write complete variants C_i = B_i ∪ S_i

Each problem gets its own timestamped directory with a dedicated log file.

Output structure (single problem):
    output/{timestamp}_{problem}/
    ├── {timestamp}_{problem}.log
    ├── clausified/
    │   └── {problem}_clausified.tptp
    └── variants/
        └── variant_{i}.tptp

Output structure (multiple problems):
    output/
    ├── {timestamp}_{problem1}/
    │   ├── {timestamp}_{problem1}.log
    │   ├── clausified/
    │   └── variants/
    ├── {timestamp}_{problem2}/
    │   ├── {timestamp}_{problem2}.log
    │   ├── clausified/
    │   └── variants/
    └── ...

Usage:
    python main.py <problem_or_dir> [options]

Examples:
    # Process single problem with 3 variants
    python main.py examples/group_theory.tptp -n 3

    # Process directory (each problem gets its own timestamped directory)
    python main.py examples/ -s priority -n 3

    # Generate seed clauses using LLM (requires OPENAI_API_KEY)
    python main.py examples/group_theory.tptp -n 3 --generate-seeds 5

    # Generate seeds with domain hint
    python main.py examples/group_theory.tptp --generate-seeds 5 --domain-hint "group theory"

    # Generate seeds with entailment checking (verifies C_0 ⊨ s)
    python main.py examples/group_theory.tptp --generate-seeds 5 --check-entailment

    # Recursive processing
    python main.py examples/ -r -n 5
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from clausify_problems import VampireClausifier
from base_clause_set_constructor import BaseClauseSetConstructor
from entailment_checker import EntailmentChecker
from logging_utils import setup_logger


def write_variant_clause_set(clauses, output_path, problem_name, num_clauses):
    """Write a complete variant clause set (C_i = B_i ∪ S_i) to a TPTP file.

    Args:
        clauses: List of Clause objects to write.
        output_path: Path to output file.
        problem_name: Name of the original problem.
        num_clauses: Total number of clauses in C_i.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("% Generated clause set variant (C_i = B_i ∪ S_i)\n")
        f.write(f"% Original problem: {problem_name}\n")
        f.write(f"% Number of clauses: {num_clauses}\n\n")

        for clause in clauses:
            f.write(f"{clause}\n")


def setup_problem_output(problem_path, base_output_dir):
    """Create timestamped output directory and logger for a problem.

    Args:
        problem_path: Path to the problem file.
        base_output_dir: Base output directory.

    Returns:
        Tuple of (problem_output_dir, logger, timestamp).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    problem_name = problem_path.stem
    problem_output = base_output_dir / f"{timestamp}_{problem_name}"
    problem_output.mkdir(parents=True, exist_ok=True)

    log_file = problem_output / f"{timestamp}_{problem_name}.log"
    logger = setup_logger(log_file)

    logger.info(f"Processing: {problem_path}")
    logger.info(f"Output directory: {problem_output}")

    return problem_output, logger, timestamp


def clausify_problem_file(problem_path, problem_output, args, logger):
    """Clausify a problem using Vampire.

    Args:
        problem_path: Path to the problem file.
        problem_output: Output directory for this problem.
        args: Command-line arguments.
        logger: Logger instance.

    Returns:
        Path to clausified file, or None if clausification failed.
    """
    logger.info("Clausifying...")
    clausifier = VampireClausifier(
        logger,
        vampire_binary=args.vampire,
        output_dir=problem_output / "clausified",
        timeout=args.timeout,
    )

    if not clausifier.clausify_problem(problem_path):
        logger.error("Clausification failed")
        return None

    logger.info("Clausification complete")

    clausified = (
        problem_output
        / "clausified"
        / f"{problem_path.stem}_clausified{problem_path.suffix}"
    )

    logger.info(f"Clausified problem: {clausified}")
    return clausified


def initialize_seed_generator(logger, args):
    """Initialize LLM seed generator if requested.

    Args:
        logger: Logger instance.
        args: Command-line arguments.

    Returns:
        SeedClauseGenerator instance, or None if not requested or initialization failed.
    """
    if not args.generate_seeds:
        return None

    try:
        from seed_clause_set_constructor import SeedClauseGenerator

        seed_generator = SeedClauseGenerator(logger)
        logger.info(
            f"LLM seed generation enabled: {args.generate_seeds} seeds per variant"
        )
        return seed_generator
    except ImportError as e:
        logger.error(f"Cannot import seed generator (openai package required): {e}")
        logger.info("Continuing without seed generation")
        return None
    except ValueError as e:
        logger.error(f"Cannot initialize seed generator: {e}")
        logger.info("Continuing without seed generation")
        return None


def construct_variant(
    variant_index,
    constructor,
    stats,
    seed_generator,
    clausified,
    problem_path,
    problem_output,
    args,
    logger,
):
    """Construct a single variant C_i = B_i ∪ S_i.

    Args:
        variant_index: Index of this variant.
        constructor: BaseClauseSetConstructor instance.
        stats: Statistics dict from constructor.
        seed_generator: SeedClauseGenerator instance or None.
        clausified: Path to clausified problem.
        problem_path: Path to original problem.
        problem_output: Output directory for this problem.
        args: Command-line arguments.
        logger: Logger instance.

    Returns:
        True if successful, False otherwise.
    """
    logger.info("=" * 80)
    logger.info(f"VARIANT {variant_index}")
    logger.info("=" * 80)

    # Construct base clause set B_i
    base = constructor.construct_base_set(strategy=args.strategy)
    kept_pct = (
        (len(base) / stats["total_clauses"] * 100) if stats["total_clauses"] > 0 else 0
    )
    logger.info(
        f"  B_i = {len(base)}/{stats['total_clauses']} clauses from C_0 ({kept_pct:.1f}%)"
    )

    # Generate seed clauses S_i if requested
    seed_clauses = []
    if seed_generator:
        logger.info(f"  Generating S_i seed clauses for variant {variant_index}...")

        # Extract context from original problem
        context = seed_generator.extract_problem_context(problem_path)

        # Convert base clauses to strings for LLM context
        base_clause_strs = [str(clause) for clause in base]

        # Generate seeds
        seeds = seed_generator.generate_seeds(
            problem_context=context,
            base_clauses=base_clause_strs,
            num_seeds=args.generate_seeds,
            domain_hint=args.domain_hint,
        )

        # Initialize entailment checker if requested
        entailment_checker = None
        if args.check_entailment:
            entailment_checker = EntailmentChecker(
                logger, vampire_binary=args.vampire, timeout=args.entailment_timeout
            )
            logger.info(
                f"  Entailment checking enabled (timeout: {args.entailment_timeout}s)"
            )

        verified_count = 0
        failed_count = 0

        for j, seed in enumerate(seeds):
            logger.info("  " + "─" * 76)
            logger.info(f"  VARIANT {variant_index} SEED {j}")
            logger.info("  " + "─" * 76)
            logger.info(f"    Clause: {seed.content}")
            logger.info(f"    Reason: {seed.description}")
            logger.info(f"    Confidence: {seed.confidence:.2f}")

            # Check entailment if requested
            if entailment_checker:
                is_entailed = entailment_checker.check_entailment(
                    clausified, seed.content
                )
                if is_entailed:
                    logger.info(f"    ✓ Entailment verified (C_0 ⊨ s)")
                    verified_count += 1
                else:
                    logger.warning(f"    ✗ Entailment check failed, skipping seed")
                    failed_count += 1
                    continue

            # Parse seed clause to add to variant
            parsed = constructor._parse_tff_clause(seed.content)
            if parsed:
                seed_clauses.append(parsed)
            else:
                logger.warning(f"    Failed to parse seed clause, skipping")

            logger.info("")  # Blank line after each seed

        if entailment_checker:
            logger.info(
                f"  Entailment results: {verified_count} verified, {failed_count} failed"
            )

    # Combine B_i ∪ S_i to form complete variant C_i and write to file
    complete_clause_set = base + seed_clauses

    output_path = problem_output / "variants" / f"variant_{variant_index}.tptp"
    write_variant_clause_set(
        complete_clause_set,
        output_path,
        problem_path.name,
        len(complete_clause_set),
    )

    logger.info(f"  Written to: {output_path}")
    logger.info(
        f"  Summary: C_i = B_i ({len(base)} clauses) ∪ S_i ({len(seed_clauses)} seeds) = {len(complete_clause_set)} total clauses"
    )
    logger.info("")

    return True


def process_problem(problem_path, base_output_dir, args):
    """Clausify a problem and construct C_i variants (C_i = B_i ∪ S_i).

    Each problem gets its own timestamped output directory and log file.
    Creates base clause sets B_i using the selected strategy, optionally
    generates seed clauses S_i using LLM, and writes complete variants.

    Args:
        problem_path: Path to the problem file.
        base_output_dir: Base output directory (e.g., "output").
        args: Parsed command-line arguments.

    Returns:
        True if successful, False otherwise.
    """
    # Setup output directory and logger
    problem_output, logger, timestamp = setup_problem_output(
        problem_path, base_output_dir
    )

    # Clausify the problem
    clausified = clausify_problem_file(problem_path, problem_output, args, logger)
    if not clausified:
        return False

    # Initialize constructor and get statistics
    constructor = BaseClauseSetConstructor(logger, clausified)
    stats = constructor.get_statistics()

    logger.info(
        f"Constructing {args.num_variants} variant(s) using '{args.strategy}' strategy for the base set"
    )
    logger.info(f"Original problem: {stats['total_clauses']} clauses")

    # Initialize seed generator if requested
    seed_generator = initialize_seed_generator(logger, args)

    # Construct complete variants C_i = B_i ∪ S_i
    for i in range(args.num_variants):
        construct_variant(
            i,
            constructor,
            stats,
            seed_generator,
            clausified,
            problem_path,
            problem_output,
            args,
            logger,
        )

    logger.info("=" * 80)
    logger.info(f"COMPLETED: {problem_path.name}")
    logger.info(f"Generated {args.num_variants} variant(s)")
    logger.info("=" * 80)
    return True


def main():
    """Main entry point for the parallel search workflow.

    Orchestrates clausification, base clause set construction (B_i),
    optional seed clause generation (S_i), and variant writing (C_i = B_i ∪ S_i).
    Each problem gets its own timestamped directory with log and artifacts.
    """
    parser = argparse.ArgumentParser(description="Parallel Vampire search workflow")
    parser.add_argument("path", type=Path, help="Problem file or directory")
    parser.add_argument(
        "-s",
        "--strategy",
        default="random",
        choices=["all", "random", "priority", "stratified"],
    )
    parser.add_argument("-n", "--num-variants", type=int, default=3)
    parser.add_argument("-o", "--output", type=Path, default=Path("output"))
    parser.add_argument("-v", "--vampire", default="../build/vampire")
    parser.add_argument("-t", "--timeout", type=int, default=60)
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument(
        "--generate-seeds",
        type=int,
        metavar="N",
        help="Generate N seed clauses per variant using LLM (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--domain-hint",
        type=str,
        help="Domain hint for seed generation (e.g., 'group theory', 'arithmetic')",
    )
    parser.add_argument(
        "--check-entailment",
        action="store_true",
        help="Verify seed clauses using entailment checking (C_0 ⊨ s)",
    )
    parser.add_argument(
        "--entailment-timeout",
        type=int,
        default=10,
        help="Timeout for each entailment check in seconds (default: 10)",
    )

    args = parser.parse_args()

    # Find problems
    if args.path.is_file():
        problems = [args.path]
    elif args.path.is_dir():
        pattern = "**/*" if args.recursive else "*"
        problems = [
            p for p in args.path.glob(pattern) if p.suffix in {".p", ".tptp", ".smt2"}
        ]
    else:
        print(f"Error: {args.path} not found")
        sys.exit(1)

    if not problems:
        print(f"No problems found in {args.path}")
        sys.exit(1)

    # Process each problem (each gets its own directory and log)
    print(f"Found {len(problems)} problem(s)")
    success = sum(process_problem(p, args.output, args) for p in problems)
    print(f"Summary: {success}/{len(problems)} successful")


if __name__ == "__main__":
    main()
