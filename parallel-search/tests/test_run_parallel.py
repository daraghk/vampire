#!/usr/bin/env python3
"""Tests for run_parallel manifest-driven selection."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from parallel_search.evaluation.parallel import _resolve_runnable_variants, run_parallel_evaluation
from parallel_search.variants.manifest import VariantManifestEntry, write_manifest


def test_resolve_runnable_variants_from_manifest(tmp_path):
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir()
    (variants_dir / "variant_0_original.tptp").write_text("fof(a,axiom,p(a)).\n")

    write_manifest(
        variants_dir,
        [
            VariantManifestEntry(
                index=0,
                original="variant_0_original.tptp",
                verified_lemma_count=1,
            )
        ],
    )

    logger = MagicMock()
    paths = _resolve_runnable_variants(variants_dir, logger)
    assert len(paths) == 1
    assert paths[0].name == "variant_0_original.tptp"


def test_run_parallel_uses_manifest(tmp_path):
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir()
    (variants_dir / "variant_0_original.tptp").write_text("fof(a,axiom,p(a)).\n")

    write_manifest(
        variants_dir,
        [
            VariantManifestEntry(
                index=0,
                original="variant_0_original.tptp",
                verified_lemma_count=1,
            )
        ],
    )

    logger = MagicMock()
    fake_result = {
        "name": "variant_0_original",
        "status": "PROVED",
        "time": 1.0,
        "exit_code": 0,
        "output_file": str(tmp_path / "results" / "variant_0_original.out"),
        "message": "ok",
    }

    class FakeFuture:
        def result(self):
            return fake_result

    class FakeExecutor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, *_args, **_kwargs):
            return FakeFuture()

    with patch("parallel_search.evaluation.parallel.ProcessPoolExecutor", return_value=FakeExecutor()):
        with patch(
            "parallel_search.evaluation.parallel.as_completed",
            side_effect=lambda futures: list(futures.keys()),
        ):
            summary = run_parallel_evaluation(
                tmp_path,
                logger,
                vampire_binary="vampire",
                timeout=10,
                max_workers=1,
                original_problem=None,
            )

    assert summary["statistics"]["total_runs"] == 1
    assert summary["statistics"]["proved"] == 1
