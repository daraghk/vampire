#!/usr/bin/env python3
"""Standalone CLI for batch clausification of TPTP problems.

Wraps ``parallel_search.clausify.clausifier.VampireClausifier``. Run from the
``parallel-search/`` directory.

Usage:
    python3 scripts/clausify.py problem.tptp -o output/clausified
"""

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from parallel_search.clausify.clausifier import VampireClausifier
from parallel_search.utils.logging import setup_logger


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-clausify TPTP problems")
    parser.add_argument("path", type=Path, help="Problem file or directory")
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument("-v", "--vampire", default="../build/vampire")
    parser.add_argument("-t", "--timeout", type=int, default=60)
    parser.add_argument(
        "--mode",
        default="clausify",
        choices=["clausify", "tclausify"],
    )
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    logger = setup_logger(Path("clausify.log"), logger_name="vampire_clausify")
    clausifier = VampireClausifier(
        logger,
        vampire_binary=args.vampire,
        output_dir=args.output,
        timeout=args.timeout,
        mode=args.mode,
    )

    if args.path.is_file():
        problems = [args.path]
    elif args.path.is_dir():
        pattern = "**/*" if args.recursive else "*"
        problems = [p for p in args.path.glob(pattern) if clausifier.is_problem_file(p)]
    else:
        print(f"Error: {args.path} not found")
        return 1

    for problem in sorted(problems):
        clausifier.clausify_problem(problem)

    logger.info(
        f"Done: success={clausifier.stats['success']} "
        f"errors={clausifier.stats['error']} timeouts={clausifier.stats['timeout']}"
    )
    return 0 if clausifier.stats["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
