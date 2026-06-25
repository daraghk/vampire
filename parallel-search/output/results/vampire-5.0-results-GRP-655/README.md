# Vampire 5.0 Results — GRP Problems (655 problems)

## Overview

This dataset contains logs from the parallel-search framework running **Vampire 5.0** on **655 problems** from the **GRP (Group Theory)** domain of the TPTP library (v9.2.1).

Runs used a **60-second timeout** per Vampire invocation.

These runs were produced with the **pre-refactor pipeline**, which logged ``seed`` terminology
(``VARIANT N SEED M``). The current codebase uses **lemma** terminology throughout; see
the main [README.md](../../../README.md) for the updated CLI.

## Results summary

- **463 / 655** problems had at least one successful proof
- **192 / 655** problems had no proof within the timeout

## Directory structure

Each problem has its own directory (flat layout in this bundle):

```
{problem}/
├── {problem}.log
├── clausified/
│   ├── {problem}_clausified.p
│   └── {problem}_clausified_axioms.p
├── variants/
│   ├── variant_0.tptp              # exploratory (clausified)
│   ├── variant_0_original.tptp     # paper configuration
│   └── ...
└── results/
    ├── summary.json
    ├── original.out
    ├── original_clausified.out     # exploratory
    ├── variant_0.out                 # exploratory
    └── variant_0_original.out
```

## Run configurations

| Configuration | In paper | Description |
|---------------|----------|-------------|
| `original` | Yes | Unmodified TPTP problem |
| `variant_N_original` | Yes | Original problem + verified LLM lemmas |
| `original_clausified` | No | Clausified C₀ (exploratory) |
| `variant_N` | No | Clausified axioms + lemmas + negated conjectures (exploratory) |

The paper reports only `original` and `variant_N_original`.

## Variant generation

- **3 variants** per problem (distinct LLM lemma sets)
- Full axiom base (all axioms from C_ax)
- **5 lemmas** per variant from **gpt-5-mini** (`gpt-5-mini-2025-08-07`)
- Entailment-verified before inclusion (C_ax ⊨ s)

## Reproducibility

- **Prover:** Vampire 5.0 (built from source)
- **LLM:** gpt-5-mini-2025-08-07
- **Timeout:** 60 seconds per run
- **Problem source:** TPTP v9.2.1, GRP domain

Re-run with the current pipeline (from ``parallel-search/``):

```bash
python3 scripts/main.py input/ -r -n 3 \
  --generate-lemmas 5 --run-vampire \
  --llm-model gpt-5-mini --vampire-timeout 60
```

Entailment checking is always performed when lemmas are generated; there is no
``--check-entailment`` flag in the current CLI.

Analyze this bundle:

```bash
python3 scripts/analyze_results.py \
  --output-dir output/results/vampire-5.0-results-GRP-655 \
  --output notes/evaluation_results.csv

# Legacy log format only (seed terminology in logs)
python3 scripts/analyze_seed_quality_logs.py \
  --logs-root output/results/vampire-5.0-results-GRP-655 \
  --output notes/seed_quality_results_strict.csv
```
