#!/usr/bin/env python3
"""Main entry point for the parallel Vampire search workflow.

Definitions:
- C₀ = Full clausified problem (Axioms ∪ negated_conjectures)
- C_ax = Axioms-only version (negated_conjectures removed from C₀)
- L_i = Verified lemmas (LLM suggestions with C_ax ⊨ s)
- Variant = all axioms + verified lemmas + negated_conjectures (clausified)
- Original variant = original (non-clausified) problem + verified lemmas

This script orchestrates the complete workflow:
1. Clausify problems (Vampire clausify/tclausify mode) → C₀
2. Create C_ax by filtering negated_conjectures from C₀
3. Use the full axiom base from C_ax for each variant
4. Generate lemma suggestions using LLM (default: 5 per variant)
5. Verify entailment C_ax ⊨ s in parallel for every generated lemma
6. Write clausified variants and original+lemmas variants
7. Write variants/manifest.json recording verified lemma counts
8. Optionally run Vampire in parallel (--run-vampire), when verified lemma variants exist

Each problem gets its own timestamped output directory with a dedicated log file.
See README.md for CLI reference and GRP-655 reproduction steps.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from parallel_search.variants.axioms import create_axioms_file
from parallel_search.variants.constructor import BaseClauseSetConstructor
from parallel_search.clausify.clausifier import VampireClausifier
from parallel_search.lemmas.pipeline import generate_and_verify_lemmas
from parallel_search.utils.logging import setup_logger
from parallel_search.evaluation.parallel import run_parallel_evaluation
from parallel_search.variants.manifest import VariantManifestEntry, write_manifest
from parallel_search.variants.writer import write_original_with_lemmas, write_variant_clause_set

DEFAULT_LEMMAS_PER_VARIANT = 5


def setup_problem_output(problem_path: Path, base_output_dir: Path):
    """Create timestamped output directory and logger for a problem."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    problem_name = problem_path.stem
    problem_output = base_output_dir / f"{timestamp}_{problem_name}"
    problem_output.mkdir(parents=True, exist_ok=True)

    log_file = problem_output / f"{timestamp}_{problem_name}.log"
    logger = setup_logger(log_file, logger_name=f"vampire_parallel.{problem_name}")

    logger.info(f"Processing: {problem_path}")
    logger.info(f"Output directory: {problem_output}")
    return problem_output, logger


def clausify_problem_file(problem_path, problem_output, args, logger):
    """Clausify a problem using Vampire."""
    logger.info(f"Clausifying (mode: {args.clausify_mode})...")
    clausifier = VampireClausifier(
        logger,
        vampire_binary=args.vampire,
        output_dir=problem_output / "clausified",
        timeout=args.timeout,
        mode=args.clausify_mode,
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


def initialize_lemma_generator(logger, args):
    """Initialize the LLM lemma generator."""
    try:
        from parallel_search.lemmas.generator import LemmaGenerator

        generator = LemmaGenerator(logger, model=args.llm_model)
        logger.info(
            f"LLM lemma generation: {args.generate_lemmas} lemmas per variant "
            f"(model: {args.llm_model})"
        )
        return generator
    except (ImportError, ValueError) as exc:
        logger.error(f"Cannot initialize lemma generator: {exc}")
        logger.info("Continuing without lemma generation")
        return None


def process_problem(problem_path: Path, base_output_dir: Path, args) -> bool:
    """Process a single problem through the complete parallel search workflow."""
    problem_output, logger = setup_problem_output(problem_path, base_output_dir)

    clausified = clausify_problem_file(problem_path, problem_output, args, logger)
    axioms_only = create_axioms_file(clausified, logger) if clausified else None
    if not clausified or not axioms_only:
        return False

    axiom_parser = BaseClauseSetConstructor(logger, axioms_only)
    c0_parser = BaseClauseSetConstructor(logger, clausified)
    stats = axiom_parser.get_statistics()
    negated_conjectures = c0_parser.negated_conjectures()

    logger.info(f"Constructing {args.num_variants} variant(s)")
    logger.info(f"C_ax (axioms only): {stats['total_clauses']} clauses")
    logger.info(f"Negated conjectures: {len(negated_conjectures)} clause(s)")

    lemma_generator = initialize_lemma_generator(logger, args)
    manifest_entries = []

    for i in range(args.num_variants):
        base = axiom_parser.all_axioms()
        logger.info("=" * 80)
        logger.info(f"VARIANT {i}")
        logger.info("=" * 80)
        logger.info(f"  Using all {len(base)} axioms from C_ax")

        verified_lemmas = generate_and_verify_lemmas(
            i,
            lemma_generator,
            base,
            problem_path,
            axioms_only,
            args,
            logger,
        )

        clausified_name = f"variant_{i}.tptp"
        clausified_path = problem_output / "variants" / clausified_name
        complete_clause_set = base + verified_lemmas + negated_conjectures
        write_variant_clause_set(complete_clause_set, clausified_path, problem_path.name)
        logger.info(f"  Written clausified variant: {clausified_path}")

        original_name = None
        if verified_lemmas:
            original_name = f"variant_{i}_original.tptp"
            original_path = problem_output / "variants" / original_name
            if write_original_with_lemmas(problem_path, verified_lemmas, original_path):
                logger.info(f"  Written original variant: {original_path}")
            else:
                logger.warning("  Failed to write original variant with lemmas")
                original_name = None

        manifest_entries.append(
            VariantManifestEntry(
                index=i,
                clausified=clausified_name,
                original=original_name,
                verified_lemma_count=len(verified_lemmas),
            )
        )
        logger.info("")

    write_manifest(problem_output / "variants", manifest_entries)

    logger.info("=" * 80)
    logger.info(f"COMPLETED: {problem_path.name}")
    logger.info(f"Generated {args.num_variants} variant(s)")
    logger.info("=" * 80)

    if args.run_vampire:
        run_parallel_evaluation(
            problem_output,
            logger,
            vampire_binary=args.vampire,
            timeout=args.vampire_timeout,
            max_workers=args.max_workers,
            original_problem=problem_path,
            include_clausified_runs=args.include_clausified_runs,
        )

    return True


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for ``main.py``."""
    parser = argparse.ArgumentParser(description="Parallel Vampire search workflow")
    parser.add_argument("path", type=Path, help="Problem file or directory")
    parser.add_argument("-n", "--num-variants", type=int, default=3)
    parser.add_argument("-o", "--output", type=Path, default=Path("output"))
    parser.add_argument("-v", "--vampire", default="../build/vampire")
    parser.add_argument("-t", "--timeout", type=int, default=60)
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument(
        "--generate-lemmas",
        type=int,
        default=DEFAULT_LEMMAS_PER_VARIANT,
        metavar="N",
        help=f"Lemmas per variant via LLM (default: {DEFAULT_LEMMAS_PER_VARIANT}; requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--domain-hint",
        type=str,
        help="Domain hint for lemma generation (e.g., 'group theory')",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="o4-mini",
        help="OpenAI model for lemma generation (default: o4-mini)",
    )
    parser.add_argument(
        "--entailment-timeout",
        type=int,
        default=10,
        help="Timeout for each entailment check in seconds (default: 10)",
    )
    parser.add_argument(
        "--run-vampire",
        action="store_true",
        help="Run Vampire in parallel on original (baseline) and original+lemmas variants; skipped if no verified lemmas",
    )
    parser.add_argument(
        "--include-clausified-runs",
        action="store_true",
        help="Also run clausified original and clausified lemma variants (exploratory)",
    )
    parser.add_argument(
        "--clausify-mode",
        type=str,
        default="clausify",
        choices=["clausify", "tclausify"],
        help="Clausification mode: clausify (CNF) or tclausify (TFF)",
    )
    parser.add_argument(
        "--vampire-timeout",
        type=int,
        default=60,
        help="Timeout for Vampire execution in seconds (default: 60)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max parallel workers for Vampire execution",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="Random seed for LLM axiom sampling reproducibility",
    )
    parser.add_argument(
        "--llm-axiom-cap",
        type=int,
        default=30,
        help="Max axioms passed to LLM context when problem is large (default: 30)",
    )
    return parser


def main() -> None:
    """Main entry point: parse args, process all problems, exit non-zero on total failure."""
    parser = build_parser()
    args = parser.parse_args()

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

    print(f"Found {len(problems)} problem(s)")
    success = sum(process_problem(p, args.output, args) for p in problems)
    print(f"Summary: {success}/{len(problems)} successful")
    if success == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
