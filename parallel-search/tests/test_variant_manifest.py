#!/usr/bin/env python3
"""Tests for variant_manifest."""

from pathlib import Path

from parallel_search.variants.manifest import (
    VariantManifestEntry,
    get_runnable_variant_paths,
    read_manifest,
    write_manifest,
)


def test_manifest_round_trip(tmp_path):
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir()
    (variants_dir / "variant_0_original.tptp").write_text("fof(a,axiom,p(a)).")

    entries = [
        VariantManifestEntry(
            index=0,
            original="variant_0_original.tptp",
            verified_lemma_count=2,
        ),
        VariantManifestEntry(
            index=1,
            original=None,
            verified_lemma_count=0,
        ),
    ]
    write_manifest(variants_dir, entries)
    manifest = read_manifest(variants_dir)
    assert manifest is not None
    assert len(manifest["variants"]) == 2

    paths = get_runnable_variant_paths(variants_dir)
    assert len(paths) == 1
    assert paths[0].name == "variant_0_original.tptp"
