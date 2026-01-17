# Parallel Search for Vampire

This directory contains work on parallelizing Vampire via semantically entailed starting clause sets.

## Contents

- **`main.py`** - Main entry point for the workflow
- **`clausify_problems.py`** - VampireClausifier class for clausification (CNF via clausify, or TFF via tclausify)
- **`base_clause_set_constructor.py`** - BaseClauseSetConstructor class for B_i selection
- **`seed_clause_set_constructor.py`** - SeedClauseGenerator class for S_i generation (requires `openai` package)
- **`entailment_checker.py`** - EntailmentChecker class for verifying C_ax ⊨ s (where C_ax is the axioms-only version with negated_conjectures removed, and s is an LLM-generated seed clause)
- **`run_parallel.py`** - Parallel Vampire execution module for running the original problem and verified variants
- **`tptp_parsing_utils.py`** - Shared TPTP parsing utilities (CNF and TFF clause parsing, quantifier/parentheses handling)
- **`logging_utils.py`** - Logging utilities
- **`examples/`** - Example TPTP problems
- **`docs/`** - Design documents

## Requirements

**Core requirements:**
- Python 3.8+
- Vampire theorem prover (built at `../build/vampire`)

**Optional (for seed generation):**
- `openai` package: `pip install openai>=1.0.0`
- OpenAI API key (set `OPENAI_API_KEY` environment variable)
- Default LLM model: `o4-mini` (configurable via `--llm-model` flag)

The workflow functions without the `openai` package but seed generation will be disabled.

## Quick Start

Run the complete workflow using `main.py`:

```bash
# Process a single problem with 3 random variants
python3 main.py examples/group_theory.tptp -n 3

# Use priority strategy (keeps conjectures and unit clauses)
python3 main.py examples/PUZ001+1.p -s priority -n 4

# Use stratified strategy (divides clauses into non-overlapping strata)
python3 main.py examples/group_theory.tptp -s stratified -n 5

# Process all examples in a directory
python3 main.py examples/ -n 3 --recursive

# Generate seed clauses using LLM (requires OPENAI_API_KEY)
python3 main.py examples/group_theory.tptp -n 3 --generate-seeds 5

# Generate seeds with domain hint
python3 main.py examples/group_theory.tptp --generate-seeds 5 --domain-hint "group theory"

# Generate seeds with specific LLM model
python3 main.py examples/group_theory.tptp --generate-seeds 5 --llm-model gpt-4o

# Generate seeds with entailment checking (verifies C_ax ⊨ s)
python3 main.py examples/group_theory.tptp --generate-seeds 5 --check-entailment

# Full workflow: generate, verify, and run Vampire in parallel
python3 main.py examples/group_theory.tptp --generate-seeds 5 --check-entailment --run-vampire

# Run Vampire with custom timeout (default 60s)
python3 main.py examples/PLA046_1.p -n 5 --run-vampire --vampire-timeout 120

# Use TFF clausification mode (preserves types, for arithmetic problems)
python3 main.py examples/ARI045_1.p -n 3 --clausify-mode tclausify
```

**Output structure**:
```
output/
└── {timestamp}_{problem}/             # One directory per problem per run
    ├── {timestamp}_{problem}.log      # Single log file (HH:MM timestamps)
    ├── clausified/                    # Clausified problems (CNF or TFF format)
    │   └── {problem}_clausified.tptp
    ├── variants/                      # Generated clause set variants (Variant = B_i + verified seeds + negated_conjectures)
    │   ├── variant_0.tptp
    │   ├── variant_1.tptp
    │   └── ...
    └── results/                       # Vampire execution results (only if --run-vampire used and verified variants exist)
        ├── original.out               # Vampire output for original problem (non-clausified)
        ├── original_clausified.out    # Vampire output for original clausified problem (C₀)
        ├── variant_0.out              # Vampire output for variant_0
        ├── variant_1.out              # Vampire output for variant_1
        ├── ...
        └── summary.json               # Execution summary with statistics
```

Each run creates a timestamped directory containing everything: the log file and all artifacts.
Log timestamps show only HH:MM since the date is in the directory name.

## Workflow

The workflow performs up to six main steps:

**Definitions:**
- **C₀** = Full clausified problem (Axioms ∪ negated_conjectures)
- **C_ax** = Axioms-only version (negated_conjecture formulas removed from C₀)

**Steps:**

1. **Clausification**: Convert the input problem to CNF (default) or TFF using Vampire's `--mode clausify` or `--mode tclausify`
   - Default (`clausify`): Produces **C₀** in CNF format - suitable for most CNF/FOF problems
   - Optional (`tclausify`): Produces **C₀** in TFF format - preserves type information for arithmetic problems
   - Use `--clausify-mode tclausify` if you need type preservation
2. **Create C_ax**: Filter out `negated_conjecture` formulas from C₀ to create **C_ax** (axioms only)
   - Used for base clause selection and entailment checking
   - Avoids vacuous truth problem in entailment verification
3. **Base Clause Set Construction (B_i)**: Generate N different base clause sets from **C_ax** using the selected strategy:
   - `all`: Use all axioms (B_i = C_ax)
   - `random`: Randomly select a subset of axioms
   - `priority`: Keep unit clauses, sample others
   - `stratified`: Divide axioms into non-overlapping strata
4. **Seed Clause Generation (S_i)** (optional): Use LLM to generate helpful lemmas for each variant
   - Seeds are problem-specific and based on variant context
   - Each seed includes an explanation and confidence score
5. **Entailment Checking** (optional): Verify each seed clause using Vampire in parallel
   - All seed clauses for a variant are checked in parallel for performance
   - Checks **C_ax ⊨ s** (verifies seed follows from axioms only)
   - This avoids vacuous truth: if C₀ is UNSAT, all seeds would trivially entail
   - Only verified seeds (proved by Vampire) are added to variants
   - Ensures soundness: UNSAT(variant) ⟹ UNSAT(C₀)
6. **Parallel Execution** (optional, requires `--run-vampire`): Run Vampire in parallel on:
   - The original problem (non-clausified)
   - The original clausified problem (C₀)
   - All variants: **B_i + verified seeds + negated_conjectures**
   - Skipped entirely if no variants have verified seeds (no point comparing original alone)
   - Captures execution time, exit status, and full Vampire output
   - Generates summary with statistics and identifies which runs proved the problem

Each variant consists of: B_i (selected axioms) + verified seeds + negated_conjectures (to prove).

All operations are logged with structured output. Log timestamps show HH:MM format for
readability (full date is in the directory name). Visual separators clearly mark each variant.

## Example Problems

The `examples/` directory contains test problems across multiple domains:
- `group_theory.tptp` - Group theory (order-2 implies commutativity)
- `PUZ001+1.p` - "Who killed Aunt Agatha?" logic puzzle
- `PUZ139_1.p` - Coffee/syrup puzzle (typed logic)
- `ARI045_1.p` - Integer arithmetic
- `NUM919_1.p` - Number theory (harder problem)
- `PLA046_1.p` - Planning problem (hardest, rating 1.00)

## Approach Overview

The parallel search strategy works as follows:

1. **Extract C₀**: Use `--mode clausify` (default, CNF) or `--mode tclausify` (TFF) to get the full clausified problem (Axioms ∪ negated_conjectures)
2. **Create C_ax**: Filter out negated_conjectures to get axioms-only version
3. **Generate variants**: Create alternative starting sets where each variant = Bᵢ + Sᵢ + negated_conjectures
   - Bᵢ ⊆ C_ax (base clauses selected from axioms using strategy: random, priority, stratified, etc.)
   - Sᵢ (seed clauses - lemmas that are entailed by C_ax)
   - negated_conjectures (the negated conjectures to prove)
   - Variant = Bᵢ + Sᵢ + negated_conjectures
4. **Verify entailment**: Check that **C_ax ⊨ s** for each seed clause s using Vampire
5. **Run in parallel**: Launch independent Vampire instances on the original problem (non-clausified), the original clausified problem (C₀), and each variant
6. **First to finish wins**: If any proves UNSAT(variant), then UNSAT(C₀) follows

## Key Properties

- **Sound by construction**: All seed clauses are verified to be entailed by C_ax (axioms only)
- **Embarrassingly parallel**: No shared state between workers
- **Semantic reachability**: Uses logical entailment rather than operational reachability
- **Heuristic generation**: LLMs can propose seed clauses, but Vampire verifies them
- **Avoids vacuous truth**: Entailment checked against C_ax (without negated_conjectures), not full C₀

## Current Status

- ✅ Clausification (C₀ extraction via `clausify` (CNF, default) or `tclausify` (TFF))
- ✅ Base clause set construction (B_i selection with multiple strategies)
- ✅ CNF and TFF format support (configurable via `--clausify-mode`)
- ✅ Shared TPTP parsing utilities (`tptp_parsing_utils.py` for quantifier/parentheses handling)
- ✅ LLM interface for seed clause suggestions (S_i generation via `seed_clause_set_constructor.py`)
- ✅ Seed generation (LLM generates clauses matching the clausification format)
- ✅ Parallel entailment checking (all seed clauses checked in parallel for performance)
- ✅ Entailment checking via conjecture proving (C_ax ⊨ s verification using `entailment_checker.py`)
- ✅ Native Vampire conjecture handling (cleaner than manual clause negation)
- ✅ Axioms-only filtering (C_ax creation to avoid vacuous truth in entailment)
- ✅ Variant file generation (B_i + verified seeds + negated_conjectures written to TPTP files)
- ✅ Structured logging with timestamped outputs
- ✅ Parallel execution framework (running original problem, original clausified problem, and variants via `run_parallel.py`)
- ✅ Results capture (execution time, status, full Vampire output, JSON summary)
- ⏳ Large-scale evaluation on TPTP benchmark problems

## References

See `docs/parallelizing_vampire_semantic_starting_sets.md` for the complete technical description.

