# Parallelizing Vampire via Semantically Entailed Starting Clause Sets

## Motivation
Vampire’s main proving mode (superposition-based saturation) evolves a single global state from an initial clause set \( C_0 \). This makes internal parallelization difficult, since inference generation, redundancy checks, and indexing are tightly coupled. Rather than parallelizing the saturation loop, we instead parallelize multiple independent saturation runs, each starting from a different but semantically related clause set.

## Key Idea
Generate alternative starting clause sets \( C_1, \dots, C_k \) such that  
\[
C_0 \models C_i \quad \text{for all } i,
\]
and then run Vampire independently on each \( C_i \) in parallel.

If any run proves \( \mathrm{UNSAT}(C_i) \), then \( \mathrm{UNSAT}(C_0) \) follows immediately, since unsatisfiability is preserved under entailment.

## Semantic Reachability
Instead of requiring operational reachability via a specific sequence of superposition steps, we impose a **semantic reachability contract**:

> A starting set \( C_i \) is acceptable if and only if \( C_0 \models C_i \).

This avoids reasoning about prover internals and focuses purely on logical safety.

## Structure of a Starting Set
Each candidate starting set is constructed as
\[
C_i = B_i \cup S_i,
\]
where:
- \( B_i \subseteq C_0 \) is a base subset of original clauses and may be a **strict subset** of \( C_0 \), allowing aggressive clause dropping.
- \( S_i \) is a small set of added **seed clauses** (lemmas, units, rewrite hints).

Entailment reduces to checking that each seed clause is implied by \( C_0 \).

## Verifying Entailment
For a seed clause  
\[
s = (\ell_1 \lor \cdots \lor \ell_m),
\]
entailment is checked by refutation:
\[
C_0 \models s
\quad \Longleftrightarrow \quad
C_0 \cup \{\neg \ell_1, \dots, \neg \ell_m\} \text{ is UNSAT}.
\]

Vampire can be used directly for this check. Only candidates whose seeds are all certified are used for parallel proof search.

## Role of an LLM or Intelligent Agent
An LLM is used **only for hypothesis generation**, not for proof or verification. It proposes non-obvious seed clauses or reformulations that are difficult to enumerate syntactically. All proposals are filtered by semantic checking, so soundness depends solely on Vampire.

## High-Level Algorithm
1. Generate candidate forks \( (B_i, S_i) \).
2. Certify each seed via entailment checking.
3. Run Vampire independently on each certified \( C_i \).
4. If any run derives the empty clause, report \( \mathrm{UNSAT}(C_0) \).

## Why This Is Interesting
This approach:
- enables parallelism without shared mutable state,
- preserves soundness by construction,
- allows exploration of diverse semantically valid reformulations,
- and is fully compatible with existing Vampire infrastructure.

## One-Sentence Summary
We parallelize Vampire by launching independent saturation runs from clause sets semantically entailed by the original problem; candidate reformulations are generated heuristically and verified semantically before use.

## Seed Clauses
A **seed clause** is a clause that:
- is not explicitly present in the original clause set \( C_0 \),
- is logically implied by \( C_0 \),
- is injected into a modified starting set in order to bias proof search.

Intuitively, a seed clause represents a lemma that the prover might eventually derive on its own, but whose early availability can dramatically change the behavior of saturation. Seed clauses do not add logical strength; instead, they influence rewriting, clause selection, and redundancy elimination.

## Canonical Seed Clause Examples

### Equality Closure and Rewrite Seeds
- **Transitive equality**  
  \( f(x)=g(x),\ g(x)=h(x) \Rightarrow f(x)=h(x) \)

- **Ground equality shortcut**  
  \( f(a)=g(a),\ g(a)=h(a) \Rightarrow f(a)=h(a) \)

- **Rewrite orientation normalization**  
  \( x=f(x) \leadsto f(x)=x \)

### Unit Predicate Consequences
- From \( \neg P(x) \lor Q(x) \) and \( P(a) \), add \( Q(a) \)
- From \( \neg Q(a) \) and \( P(x) \lor Q(x) \), add \( P(a) \)

### Structural or Relational Seeds
- **Transitivity**  
  \( \neg R(x,y) \lor \neg R(y,z) \lor R(x,z) \)
- **Symmetry**  
  \( \neg R(x,y) \lor R(y,x) \)

### Functional Consistency Seeds
- **Injectivity-style**  
  \( f(x)=f(y) \Rightarrow x=y \)
- **Determinism**  
  \( P(f(x),y),\ P(f(x),z) \Rightarrow y=z \)

## Minimal Seed Grammar for Prompting

### Terms
\[
t ::= x \mid a \mid f(t_1,\dots,t_n)
\]

### Atoms
\[
A ::= P(t_1,\dots,t_n) \mid t_1 = t_2 \mid t_1 \neq t_2
\]

### Seed Clauses
\[
s ::= A \mid \neg A \mid A_1 \lor A_2 \mid \neg A_1 \lor A_2
\]

## Interpretation
Seed clauses form the interface between speculative hypothesis generation and sound proof search. An external agent (e.g., an LLM) proposes candidate seeds; Vampire verifies entailment and exploits the resulting reformulation during saturation.
