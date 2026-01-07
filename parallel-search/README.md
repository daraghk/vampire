# Parallel Search for Vampire

This directory contains work on parallelizing Vampire via semantically entailed starting clause sets.

## Contents

- **`main.py`** - Main entry point for the workflow
- **`clausify_problems.py`** - VampireClausifier class for TFF conversion (using tclausify mode)
- **`base_clause_set_constructor.py`** - BaseClauseSetConstructor class for B_i selection
- **`seed_clause_set_constructor.py`** - SeedClauseGenerator class for S_i generation (requires `openai` package)
- **`entailment_checker.py`** - EntailmentChecker class for verifying C₀ ⊨ s (where s is an LLM-generated seed clause)
- **`run_parallel.py`** - Parallel Vampire execution module for running C₀ and verified variants
- **`tptp_parsing_utils.py`** - Shared TFF parsing utilities (quantifier/parentheses handling)
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

# Generate seeds with entailment checking (verifies C₀ ⊨ s)
python3 main.py examples/group_theory.tptp --generate-seeds 5 --check-entailment

# Full workflow: generate, verify, and run Vampire in parallel
python3 main.py examples/group_theory.tptp --generate-seeds 5 --check-entailment --run-vampire

# Run Vampire with custom timeout (default 60s)
python3 main.py examples/PLA046_1.p -n 5 --run-vampire --vampire-timeout 120
```

**Output structure**:
```
output/
└── {timestamp}_{problem}/             # One directory per problem per run
    ├── {timestamp}_{problem}.log      # Single log file (HH:MM timestamps)
    ├── clausified/                    # Clausified problems (TFF/typed clause form)
    │   └── {problem}_clausified.tptp
    ├── variants/                      # Generated clause set variants (C_i = B_i ∪ S_i)
    │   ├── variant_0.tptp
    │   ├── variant_1.tptp
    │   └── ...
    └── results/                       # Vampire execution results (only if --run-vampire used and verified variants exist)
        ├── original.out               # Vampire output for original problem
        ├── variant_0.out              # Vampire output for variant_0
        ├── variant_1.out              # Vampire output for variant_1
        ├── ...
        └── summary.json               # Execution summary with statistics
```

Each run creates a timestamped directory containing everything: the log file and all artifacts.
Log timestamps show only HH:MM since the date is in the directory name.

## Workflow

The workflow performs up to five main steps:

1. **Clausification**: Convert the input problem to TFF using Vampire's `--mode tclausify`
   - Produces TFF (Typed First-order Form) output with quantified clauses
   - Preserves type information for arithmetic problems ($int, $real, etc.)
2. **Base Clause Set Construction (B_i)**: Generate N different base clause sets using the selected strategy:
   - `all`: Use all clauses (B_i = C_0)
   - `random`: Randomly select a subset of clauses
   - `priority`: Keep conjectures and unit clauses, sample others
   - `stratified`: Divide clauses into non-overlapping strata
3. **Seed Clause Generation (S_i)** (optional): Use LLM to generate helpful lemmas for each variant
   - Seeds are problem-specific and based on variant context
   - Each seed includes an explanation and confidence score
4. **Entailment Checking** (optional): Verify each seed clause using Vampire
   - Checks C₀ ⊨ s by proving s as a conjecture from C₀
   - Converts C₀'s negated_conjecture clauses to hypothesis role
   - Adds seed clause s with conjecture role
   - Only verified seeds (proved by Vampire) are added to variants
   - Ensures soundness: UNSAT(C_i) ⟹ UNSAT(C₀)
5. **Parallel Execution** (optional, requires `--run-vampire`): Run Vampire in parallel on:
   - The original clausified problem (C₀)
   - All variants with at least one verified seed clause
   - Skipped entirely if no variants have verified seeds (no point comparing original alone)
   - Captures execution time, exit status, and full Vampire output
   - Generates summary with statistics and identifies which runs proved the problem

Each variant C_i = B_i ∪ S_i is saved as a separate TPTP file ready for parallel proof search.

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

1. **Extract C₀**: Use `--mode tclausify` to get the initial typed clause set
2. **Generate variants**: Create alternative starting sets C₁, ..., Cₖ where each Cᵢ = Bᵢ ∪ Sᵢ
   - Bᵢ ⊆ C₀ (base clauses)
   - Sᵢ (seed clauses - lemmas that are entailed by C₀)
3. **Verify entailment**: Check that C₀ ⊨ s for each seed clause s using Vampire
4. **Run in parallel**: Launch independent Vampire instances on each certified Cᵢ
5. **First to finish wins**: If any proves UNSAT(Cᵢ), then UNSAT(C₀) follows

## Key Properties

- **Sound by construction**: All seed clauses are verified to be entailed by C₀
- **Embarrassingly parallel**: No shared state between workers
- **Semantic reachability**: Uses logical entailment rather than operational reachability
- **Heuristic generation**: LLMs can propose seed clauses, but Vampire verifies them

## Current Status

- ✅ Clausification (C_0 extraction with type preservation via `tclausify`)
- ✅ Base clause set construction (B_i selection with multiple strategies)
- ✅ TFF format support (Typed First-order Form with quantified clauses)
- ✅ Shared TPTP parsing utilities (`tptp_parsing_utils.py` for quantifier/parentheses handling)
- ✅ LLM interface for seed clause suggestions (S_i generation via `seed_clause_set_constructor.py`)
- ✅ TFF seed generation (LLM generates TFF clauses with type information)
- ✅ Entailment checking via conjecture proving (C_0 ⊨ s verification using `entailment_checker.py`)
- ✅ Native Vampire conjecture handling (cleaner than manual clause negation)
- ✅ Variant file generation (C_i = B_i ∪ S_i written to TPTP files)
- ✅ Structured logging with timestamped outputs
- ✅ Parallel execution framework (running C₀ + variants with verified seeds via `run_parallel.py`)
- ✅ Results capture (execution time, status, full Vampire output, JSON summary)
- ⏳ Large-scale evaluation on TPTP benchmark problems

## References

See `docs/parallelizing_vampire_semantic_starting_sets.md` for the complete technical description.

