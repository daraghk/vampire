"""LLM lemma generation, axiom context sampling, and parallel entailment checking.

Definitions:
- C_ax = Axioms-only version used for entailment checking and LLM context
- L_i = Verified lemmas generated per variant and filtered by entailment

This module handles:
1. Sampling axioms for LLM context when problems are large (``--llm-axiom-cap``)
2. Parallel entailment checking of all lemmas for a variant (ProcessPoolExecutor)
3. Parsing and returning only verified ``Clause`` objects for variant writing

Every LLM-generated lemma is verified (C_ax ⊨ s) before inclusion in variants.

Used by ``scripts/main.py`` via ``generate_and_verify_lemmas()``.
"""

import io
import logging
import os
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Sequence

from parallel_search.entailment.checker import EntailmentChecker
from parallel_search.parsing.tptp import Clause, parse_cnf_clause, parse_tff_clause

DEFAULT_LLM_AXIOM_CAP = 30


def sample_axioms_for_llm(
    base_clauses: Sequence[Clause],
    cap: int = DEFAULT_LLM_AXIOM_CAP,
    sample_seed: Optional[int] = None,
) -> List[Clause]:
    """Select axiom clauses to include in the LLM prompt.

    When the axiom count exceeds ``cap``, keeps all unit clauses and randomly
    samples the remainder. Use ``--sample-seed`` on the CLI for reproducibility.

    Args:
        base_clauses: Full axiom set from C_ax.
        cap: Maximum number of axioms to pass to the LLM.
        sample_seed: Optional random seed for deterministic sampling.

    Returns:
        Subset of ``base_clauses`` (or all, if count <= cap).
    """
    if len(base_clauses) <= cap:
        return list(base_clauses)

    rng = random.Random(sample_seed)
    unit_clauses = [
        c
        for c in base_clauses
        if len(c.literals) < 50 and c.literals.count("|") == 0
    ]
    remaining = [c for c in base_clauses if c not in unit_clauses]
    selected = list(unit_clauses)
    slots = max(0, cap - len(selected))
    if slots and remaining:
        if len(remaining) <= slots:
            selected.extend(remaining)
        else:
            selected.extend(rng.sample(remaining, slots))
    return selected[:cap]


def check_lemma_entailment(
    lemma_index: int,
    lemma_content: str,
    clausified_path: Path,
    vampire_binary: str,
    timeout: int,
) -> tuple:
    """Check entailment for a single lemma (ProcessPoolExecutor worker).

    Args:
        lemma_index: Index of the lemma (for result ordering).
        lemma_content: Lemma clause in TPTP format.
        clausified_path: Path to C_ax (axioms-only file).
        vampire_binary: Path to Vampire executable.
        timeout: Entailment check timeout in seconds.

    Returns:
        Tuple of (lemma_index, is_entailed, debug_logs).
    """
    logger = logging.getLogger(f"entailment_{lemma_index}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    try:
        checker = EntailmentChecker(
            logger, vampire_binary=vampire_binary, timeout=timeout
        )
        is_entailed = checker.check_entailment(clausified_path, lemma_content)
        debug_logs = (
            log_capture.getvalue().strip().split("\n")
            if log_capture.getvalue().strip()
            else []
        )
        return (lemma_index, is_entailed, debug_logs)
    except Exception as exc:
        return (lemma_index, False, [f"Exception in subprocess: {exc}"])


def generate_and_verify_lemmas(
    variant_index: int,
    lemma_generator,
    base_clauses: List[Clause],
    problem_path: Path,
    axioms_only: Path,
    args,
    logger: logging.Logger,
) -> List[Clause]:
    """Generate lemma suggestions and verify each via entailment checking.

    Args:
        variant_index: Index of this variant (for logging).
        lemma_generator: ``LemmaGenerator`` instance or None.
        base_clauses: Full axiom set from C_ax.
        problem_path: Path to original (non-clausified) problem.
        axioms_only: Path to C_ax for entailment checking.
        args: Parsed CLI arguments.
        logger: Logger instance.

    Returns:
        List of verified lemma ``Clause`` objects (empty if generation fails or none verified).
    """
    if not lemma_generator:
        return []

    logger.info(f"  Generating lemmas for variant {variant_index}...")

    context = lemma_generator.extract_problem_context(problem_path)
    sampled = sample_axioms_for_llm(
        base_clauses,
        cap=getattr(args, "llm_axiom_cap", DEFAULT_LLM_AXIOM_CAP),
        sample_seed=getattr(args, "sample_seed", None),
    )
    if len(sampled) < len(base_clauses):
        logger.info(
            f"  Providing {len(sampled)} of {len(base_clauses)} axioms to LLM context"
        )
    else:
        logger.info(f"  Providing all {len(base_clauses)} axioms to LLM context")

    base_clause_strs = [str(clause) for clause in sampled]
    suggestions = lemma_generator.generate_lemmas(
        problem_context=context,
        base_clauses=base_clause_strs,
        num_lemmas=args.generate_lemmas,
        domain_hint=args.domain_hint,
    )

    entailment_results = {}
    entailment_debug_logs = {}
    if suggestions:
        logger.info(
            f"  Entailment checking (timeout: {args.entailment_timeout}s)"
        )
        logger.info(f"  Running {len(suggestions)} entailment checks in parallel...")

        max_workers = min(os.cpu_count() or 4, len(suggestions), 8)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    check_lemma_entailment,
                    j,
                    lemma.content,
                    axioms_only,
                    args.vampire,
                    args.entailment_timeout,
                ): j
                for j, lemma in enumerate(suggestions)
            }

            completed = 0
            for future in as_completed(futures):
                expected_idx = futures[future]
                try:
                    returned_idx, is_entailed, debug_logs = future.result()
                    entailment_results[returned_idx] = is_entailed
                    entailment_debug_logs[returned_idx] = debug_logs
                except Exception as exc:
                    logger.warning(
                        f"  Entailment check for lemma {expected_idx} raised exception: {exc}"
                    )
                    entailment_results[expected_idx] = False
                    entailment_debug_logs[expected_idx] = [f"Exception: {exc}"]
                completed += 1
                if len(suggestions) > 5:
                    logger.info(
                        f"  Progress: {completed}/{len(suggestions)} checks completed"
                    )

        logger.info(
            f"  All entailment checks completed ({completed}/{len(suggestions)})"
        )

    verified_lemmas: List[Clause] = []
    verified_count = 0
    failed_count = 0

    for j, lemma in enumerate(suggestions):
        logger.info("  " + "─" * 76)
        logger.info(f"  VARIANT {variant_index} LEMMA {j}")
        logger.info("  " + "─" * 76)
        logger.info(f"    Clause: {lemma.content}")
        logger.info(f"    Reason: {lemma.description}")
        logger.info(f"    Confidence: {lemma.confidence:.2f}")

        is_entailed = entailment_results.get(j, False)
        for log_line in entailment_debug_logs.get(j, []):
            if log_line.strip():
                logger.debug(log_line)

        if not is_entailed:
            logger.warning("    ✗ Entailment check failed, skipping lemma")
            failed_count += 1
            logger.info("")
            continue

        logger.info("    ✓ Entailment verified (C_ax ⊨ s)")
        verified_count += 1

        if lemma.content.strip().startswith("tff("):
            parsed = parse_tff_clause(lemma.content, logger)
        elif lemma.content.strip().startswith("cnf("):
            parsed = parse_cnf_clause(lemma.content, logger)
        else:
            logger.warning(
                f"    Lemma not in CNF or TFF format: {lemma.content[:50]}..."
            )
            parsed = None

        if parsed:
            verified_lemmas.append(parsed)
        else:
            logger.warning("    Failed to parse lemma, skipping")
            logger.error(
                "    ERROR: Entailment passed but parsing failed! This indicates a bug."
            )
            failed_count += 1

        logger.info("")

    if suggestions:
        logger.info(
            f"  Entailment results: {verified_count} verified, {failed_count} failed"
        )

    return verified_lemmas
