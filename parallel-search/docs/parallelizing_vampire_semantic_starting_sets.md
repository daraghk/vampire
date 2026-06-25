# Parallelizing Vampire via Semantically Entailed Starting Clause Sets

## Motivation

Vampire's saturation loop is hard to parallelize internally. Instead, run multiple independent Vampire instances from semantically related starting sets.

## Key idea

Generate alternative starting sets where each lemma is a logical consequence of the axioms. If any run proves the conjecture, the original problem is proved — provided the axiom base is the full axiom set (C_ax).

## Structure

Each variant uses:

- **C_ax** — all axioms (negated conjectures removed from C₀)
- **L_i** — verified lemmas (C_ax ⊨ s for each s ∈ L_i)
- **Original problem + L_i** — the configuration used in the GRP-655 benchmark

## Entailment checking

For lemma s, verify C_ax ⊨ s by adding s as a conjecture and running Vampire. Only refuted (UNSAT) lemmas are kept.

## LLM role

The LLM proposes lemmas; Vampire verifies them. The LLM never affects soundness.

## Algorithm

1. Clausify problem → C₀
2. Filter negated conjectures → C_ax
3. For each variant: LLM generates lemmas from axiom context (default 5 per variant)
4. Verify C_ax ⊨ s for each lemma (parallel)
5. Write original+lemmas variants; record manifest.json
6. Run Vampire in parallel on original (baseline) and original+lemmas variants — only when at least one variant has verified lemmas

## Soundness contract

When B_i = C_ax (all axioms) and every lemma is entailment-verified:

> UNSAT(original + verified lemmas) ⟹ UNSAT(original problem)

Subset axiom strategies are not part of the validated pipeline.

## Summary

We parallelize Vampire by launching independent runs on the original problem and on the same problem augmented with verified, entailed lemmas.
