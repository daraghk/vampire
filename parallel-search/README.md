# Parallel Search for Vampire

Parallelize Vampire by running independent proof searches from the original problem plus LLM-generated, entailment-verified lemmas. Variants are the original problem augmented with lemmas verified as entailed by the axioms (C_ax ⊨ s).

## Layout

```
parallel-search/
├── scripts/                  # Runnable entry points
│   main.py                   # Full pipeline
│   clausify.py               # Batch clausification only
│   analyze_results.py        # Evaluation results → CSV
│   select_random_problems.py # Random TPTP problem selection → input/
├── parallel_search/          # Importable library
│   clausify/                 # C₀ clausification
│   parsing/                  # TPTP parsing utilities
│   variants/                 # C_ax, manifest, variant files
│   lemmas/                   # LLM generation + entailment pipeline
│   entailment/               # C_ax ⊨ s checking
│   evaluation/               # Parallel Vampire runs
│   utils/                    # Logging
├── tests/
```

## Requirements

- Python 3.8+
- Vampire built at `../build/vampire`
- `pip install -r requirements.txt` and `OPENAI_API_KEY` (lemma generation runs by default)

Run commands from the `parallel-search/` directory:

```bash
pip install -r requirements.txt
# optional: pip install -e .  (editable install; scripts work without this)
```

## Quick start

```bash
# Default pipeline (3 variants, 5 lemmas each, entailment-verified)
python3 scripts/main.py examples/group_theory.tptp

# Full evaluation
python3 scripts/main.py examples/group_theory.tptp --run-vampire --vampire-timeout 60

# TFF clausification (arithmetic)
python3 scripts/main.py examples/ARI045_1.p --clausify-mode tclausify
```

## Pipeline

1. **Clausify** input problem → C₀ (axioms ∪ negated conjectures)
2. **Filter** negated conjectures → C_ax (axioms only)
3. **Generate** LLM lemma suggestions per variant (default 5)
4. **Verify** entailment C_ax ⊨ s for every lemma (mandatory, parallel)
5. **Write** original+lemmas variants + `manifest.json`
6. **Optionally run** Vampire in parallel (`--run-vampire`) when verified lemma variants exist

## Default parallel evaluation scope

With `--run-vampire`, parallel evaluation runs **only when at least one variant has verified lemmas**. The goal is to compare lemma-augmented variants against the original baseline — if no variants qualify, nothing is run (including the original).

When evaluation proceeds, the default runs are:

- `original` — unmodified problem (baseline for comparison)
- `variant_N_original` — original problem + verified lemmas

Variant selection requires `variants/manifest.json`; variants with `verified_lemma_count == 0` are skipped.

## Output layout

```
output/{timestamp}_{problem}/
├── {timestamp}_{problem}.log
├── clausified/
│   ├── {problem}_clausified.p
│   └── {problem}_clausified_axioms.p
├── variants/
│   ├── manifest.json
│   └── variant_0_original.tptp
└── results/          # when --run-vampire and verified lemmas exist
    ├── summary.json
    ├── original.out
    └── variant_0_original.out
```

## Module reference

| Module | Role |
|--------|------|
| `scripts/main.py` | Full workflow orchestrator |
| `scripts/clausify.py` | Standalone batch clausification CLI |
| `scripts/analyze_results.py` | Aggregate `results/summary.json` → CSV |
| `scripts/select_random_problems.py` | Random problem selection for batch runs |
| `parallel_search/clausify/clausifier.py` | Vampire clausify/tclausify wrapper |
| `parallel_search/parsing/tptp.py` | CNF/TFF clause parsing and manipulation |
| `parallel_search/variants/axioms.py` | Create C_ax from C₀ |
| `parallel_search/variants/constructor.py` | Parse clausified problems, expose axiom sets |
| `parallel_search/variants/writer.py` | Write original+lemmas variant files |
| `parallel_search/variants/manifest.py` | Read/write `manifest.json` |
| `parallel_search/lemmas/generator.py` | LLM lemma suggestion (OpenAI function calling) |
| `parallel_search/lemmas/pipeline.py` | Axiom sampling, parallel entailment verification |
| `parallel_search/entailment/checker.py` | C_ax ⊨ s via Vampire conjecture proving |
| `parallel_search/evaluation/parallel.py` | Parallel Vampire execution on variants |
| `parallel_search/utils/logging.py` | Shared logger setup |

## CLI reference — `scripts/main.py`

| Flag | Default | Description |
|------|---------|-------------|
| `path` | — | Problem file or directory (`.p`, `.tptp`, `.smt2`) |
| `-n`, `--num-variants` | 3 | Number of variants (distinct LLM lemma sets) |
| `-o`, `--output` | `output` | Base output directory |
| `-v`, `--vampire` | `../build/vampire` | Path to Vampire binary |
| `-t`, `--timeout` | 60 | Clausification timeout (seconds) |
| `-r`, `--recursive` | off | Recurse when `path` is a directory |
| `--generate-lemmas N` | 5 | LLM lemmas per variant (entailment-verified) |
| `--domain-hint` | none | Domain hint for lemma generation (e.g. `group theory`) |
| `--llm-model` | `gpt-5.4-nano` | OpenAI model for lemma generation |
| `--llm-axiom-cap` | 30 | Max axioms in LLM context when problem is large |
| `--sample-seed` | none | RNG seed for axiom sampling reproducibility |
| `--entailment-timeout` | 10 | Per-lemma entailment check timeout (seconds) |
| `--run-vampire` | off | Parallel proof runs (skipped if no verified lemmas) |
| `--clausify-mode` | `clausify` | `clausify` (CNF) or `tclausify` (TFF) |
| `--vampire-timeout` | 60 | Per-run Vampire timeout (seconds) |
| `--max-workers` | auto | Max parallel workers for Vampire execution |

## CLI reference — other scripts

### `scripts/clausify.py`

| Flag | Default | Description |
|------|---------|-------------|
| `path` | — | Problem file or directory |
| `-o`, `--output` | inline | Output directory for clausified files |
| `-v`, `--vampire` | `../build/vampire` | Vampire binary |
| `-t`, `--timeout` | 60 | Clausification timeout (seconds) |
| `-r`, `--recursive` | off | Recurse into subdirectories |
| `--mode` | `clausify` | `clausify` (CNF) or `tclausify` (TFF) |

### `scripts/analyze_results.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `output` | Root directory to scan for result bundles |
| `--output` | `evaluation_results.csv` | Output CSV path |

### `scripts/select_random_problems.py`

| Flag | Default | Description |
|------|---------|-------------|
| `num_problems` | — | Number of random problems to copy to `input/` |
| `--clear` | off | Clear `input/` before copying |
| `--seed` | none | Random seed for reproducible selection |
| `--max-lines` | 1500 | Skip files larger than this |
| `--type` | all | Filter by TPTP domain (e.g. `GRP`, `ARI`) |
| `--problems-dir` | `scripts/Problems` | Source problems directory |
| `--input-dir` | `scripts/input` | Destination directory |

## Analyzing results

```bash
python3 scripts/analyze_results.py --output-dir output --output evaluation_results.csv
```

For flat bundle layouts (e.g. `output/results/vampire-5.0-results-GRP-655/`), pass that path as `--output-dir`.

## Soundness

Sound proof transfer (UNSAT variant ⟹ UNSAT original) holds when the axiom base is the full C_ax (all axioms). The pipeline always uses all axioms; lemmas must pass entailment checking before use.

## LLM axiom context (current)

Lemma generation passes the LLM **clausified axioms from C_ax** (plus header comments from the original problem). Entailment is checked against the same precomputed C_ax file. Evaluation runs on the **original** problem + verified lemmas.

## Future work: original axioms for the LLM

A possible workflow change: give the LLM **original** axioms and assumptions from the input problem, while keeping entailment on **C_ax** (derived once from C₀) so each check still reuses the clausified axiom file without re-preprocessing.

This is **not implemented** and may not be worthwhile yet. The main risk is a **symbol/format mismatch**: lemmas stated in original syntax (e.g. named functions as written in the `.p` file) may not align with clausified C_ax (skolemization, renamed symbols, CNF structure), causing entailment checks to reject lemmas that are mathematically valid.

Only pursue this if experiments show that original axioms are **more interpretable to the LLM** and produce **better lemma candidates** (higher verification rate or better proof performance) than clausified C_ax context — enough to outweigh mismatch losses.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
