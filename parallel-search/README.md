# Parallel Search for Vampire

Parallelize Vampire by running independent proof searches from the original problem plus LLM-generated, entailment-verified lemmas. See [docs/parallelizing_vampire_semantic_starting_sets.md](docs/parallelizing_vampire_semantic_starting_sets.md) for the theory.

## Layout

```
parallel-search/
├── scripts/                  # Runnable entry points
│   main.py                   # Full pipeline
│   clausify.py               # Batch clausification only
│   analyze_results.py        # Evaluation results → CSV
│   analyze_seed_quality_logs.py  # Legacy GRP log analysis
│   select_random_problems.py
├── parallel_search/          # Importable library
│   clausify/                 # C₀ clausification
│   parsing/                  # TPTP parsing utilities
│   variants/                 # C_ax, manifest, variant files
│   lemmas/                   # LLM generation + entailment pipeline
│   entailment/               # C_ax ⊨ s checking
│   evaluation/               # Parallel Vampire runs
│   analysis/                 # Result discovery helpers
│   utils/                    # Logging
├── tests/
├── docs/
└── notes/                    # Historical GRP analysis notes/CSV
```

## Requirements

- Python 3.8+
- Vampire built at `../build/vampire`
- `pip install -r requirements.txt` and `OPENAI_API_KEY` (lemma generation runs by default)

Run commands from the `parallel-search/` directory.

## Quick start

```bash
# Default pipeline (3 variants, 5 lemmas each, entailment-verified)
python3 scripts/main.py examples/group_theory.tptp

# Full evaluation
python3 scripts/main.py examples/group_theory.tptp --run-vampire --vampire-timeout 60

# TFF clausification (arithmetic)
python3 scripts/main.py examples/ARI045_1.p --clausify-mode tclausify
```

## Default parallel evaluation scope

With `--run-vampire`, parallel evaluation runs **only when at least one variant has verified lemmas**. The goal is to compare lemma-augmented variants against the original baseline — if no variants qualify, nothing is run.

When evaluation proceeds, the default runs are:

- `original` — unmodified problem (baseline for comparison)
- `variant_N_original` — original problem + verified lemmas

Clausified runs (`original_clausified`, clausified `variant_N`) are opt-in via `--include-clausified-runs`.

Lemma generation (default 5 per variant) always runs entailment verification (C_ax ⊨ s) before lemmas are included in variants.

## Output layout

```
output/{timestamp}_{problem}/
├── {timestamp}_{problem}.log
├── clausified/
│   ├── {problem}_clausified.p
│   └── {problem}_clausified_axioms.p
├── variants/
│   ├── manifest.json
│   ├── variant_0.tptp
│   └── variant_0_original.tptp
└── results/          # when --run-vampire and verified lemmas exist
    ├── summary.json
    ├── original.out
    └── variant_0_original.out
```

## CLI reference

| Flag | Default | Description |
|------|---------|-------------|
| `-n` | 3 | Number of variants (distinct LLM lemma sets) |
| `--generate-lemmas N` | 5 | LLM lemmas per variant (entailment-verified) |
| `--run-vampire` | off | Parallel proof runs |
| `--include-clausified-runs` | off | Also run clausified configurations |
| `--llm-model` | o4-mini | OpenAI model |
| `--llm-axiom-cap` | 30 | Max axioms in LLM context |
| `--sample-seed` | none | RNG seed for axiom sampling |
| `--vampire-timeout` | 60 | Per-run timeout (seconds) |
| `--entailment-timeout` | 10 | Per-lemma entailment check timeout |

## GRP-655 reproduction

```bash
python3 scripts/main.py input/ -r \
  --run-vampire --llm-model gpt-5-mini --vampire-timeout 60
```

Published results: [output/results/vampire-5.0-results-GRP-655/README.md](output/results/vampire-5.0-results-GRP-655/README.md)

Regenerate CSV:

```bash
python3 scripts/analyze_results.py \
  --output-dir output/results/vampire-5.0-results-GRP-655 \
  --output notes/evaluation_results.csv

# Historical GRP logs use legacy "seed" terminology in log format
python3 scripts/analyze_seed_quality_logs.py \
  --logs-root output/results/vampire-5.0-results-GRP-655
```

## Soundness

Sound proof transfer (UNSAT variant ⟹ UNSAT original) holds when the axiom base is the full C_ax (all axioms). The pipeline always uses all axioms; lemmas must pass entailment checking before use.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Status

- GRP-655 evaluation complete (655 problems)
- Default pipeline matches validated benchmark configuration
