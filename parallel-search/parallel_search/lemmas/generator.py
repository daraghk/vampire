#!/usr/bin/env python3
"""Lemma generator (L_i) for parallel Vampire search.

Definitions:
- C_ax = Axioms-only version (negated_conjectures removed from C₀)
- L_i = Verified lemmas (LLM suggestions filtered by ``entailment_checker.py``)
- Variant = all axioms + verified lemmas + negated_conjectures

This module generates LLM lemma suggestions using OpenAI function calling.
Suggestions are unverified until ``lemma_pipeline.py`` confirms entailment (C_ax ⊨ s).

Workflow:
1. Extract problem context (header comments only; conjecture excluded)
2. Prompt LLM with axiom clauses from C_ax (format-matched CNF or TFF)
3. Parse structured response into ``SuggestedLemma`` objects
4. Return suggestions to ``lemma_pipeline.py`` for entailment verification

Requires:
- ``openai>=1.0.0`` (see requirements.txt)
- ``OPENAI_API_KEY`` environment variable

Usage:
    from parallel_search.lemmas.generator import LemmaGenerator

    generator = LemmaGenerator(logger, model="o4-mini")
    lemmas = generator.generate_lemmas(context, base_clauses, num_lemmas=5)
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass
class SuggestedLemma:
    """An LLM-suggested lemma before entailment verification.

    Attributes:
        content: The clause in TPTP format.
        description: LLM's explanation of the lemma.
        confidence: Optional confidence score (default: 1.0).
    """

    content: str
    description: str
    confidence: float = 1.0


class LemmaGenerator:
    """Generate lemma suggestions using OpenAI for L_i construction.

    Generated clauses are unverified suggestions that require entailment
    checking before being added to variants.
    """

    LEMMA_CLAUSES_SCHEMA = {
        "name": "generate_lemmas",
        "description": "Generate helpful lemmas for a theorem proving problem",
        "parameters": {
            "type": "object",
            "properties": {
                "lemma_clauses": {
                    "type": "array",
                    "description": "List of suggested lemmas",
                    "items": {
                        "type": "object",
                        "properties": {
                            "clause": {
                                "type": "string",
                                "description": "The clause in TPTP CNF or TFF format",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Brief explanation of why this lemma is useful",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score between 0 and 1",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["clause", "explanation"],
                    },
                }
            },
            "required": ["lemma_clauses"],
        },
    }

    def __init__(
        self,
        logger: logging.Logger,
        api_key: Optional[str] = None,
        model: str = "o4-mini",
    ):
        """Initialize the lemma generator.

        Args:
            logger: Logger instance for logging.
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var).
            model: OpenAI model to use (default: o4-mini).

        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self.logger = logger
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key."
            )

        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def generate_lemmas(
        self,
        problem_context: str,
        base_clauses: List[str],
        num_lemmas: int = 5,
        domain_hint: Optional[str] = None,
    ) -> List[SuggestedLemma]:
        """Generate lemma suggestions for a problem.

        Args:
            problem_context: Problem description or header comments.
            base_clauses: Sample of base clauses B_i for context.
            num_lemmas: Number of lemmas to generate.
            domain_hint: Optional domain hint (e.g., "group theory", "arithmetic").

        Returns:
            List of suggested lemmas (unverified).
        """
        self.logger.info(f"  Requesting {num_lemmas} lemmas from {self.model}")

        clause_format = "TFF"
        if base_clauses:
            first_clause = base_clauses[0].strip()
            if first_clause.startswith("cnf("):
                clause_format = "CNF"
            elif first_clause.startswith("tff("):
                clause_format = "TFF"

        prompt = self._build_prompt(
            problem_context, base_clauses, num_lemmas, domain_hint, clause_format
        )

        self.logger.info("")
        self.logger.info("  >>> LLM PROMPT START >>>")
        self.logger.info(prompt)
        self.logger.info("  <<< LLM PROMPT END <<<")
        self.logger.info("")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert in automated theorem proving and first-order logic. "
                            f"Your task is to suggest helpful lemmas and intermediate clauses that are "
                            f"logical consequences of the given axioms. Provide clauses in TPTP {clause_format} format. "
                            f"If {clause_format} is TFF, use type quantifiers. If {clause_format} is CNF, use disjunctive clauses."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                functions=[self.LEMMA_CLAUSES_SCHEMA],
                function_call={"name": "generate_lemmas"},
            )

            self.logger.info("")
            self.logger.info("  >>> LLM RESPONSE START >>>")
            self.logger.info(response.model_dump_json(indent=2))
            self.logger.info("  <<< LLM RESPONSE END <<<")
            self.logger.info("")

            message = response.choices[0].message
            function_args = json.loads(message.function_call.arguments)
            lemmas = self._parse_schema_response(function_args)

            self.logger.info(f"  Generated {len(lemmas)} lemma suggestions")
            return lemmas

        except Exception as exc:
            self.logger.error(f"  LLM generation failed: {exc}")
            return []

    def _build_prompt(
        self,
        problem_context: str,
        base_clauses: List[str],
        num_lemmas: int,
        domain_hint: Optional[str] = None,
        clause_format: str = "TFF",
    ) -> str:
        """Build the prompt for lemma generation."""
        domain_line = f"\nDomain: {domain_hint}\n" if domain_hint else ""

        clauses_context = "\n".join(base_clauses)
        clause_count = len(base_clauses)
        clauses_heading = (
            f"## Axiom Clauses ({clause_count} provided)"
            if clause_count
            else "## Axiom Clauses"
        )

        prompt = f"""
I need help generating useful lemmas for a theorem proving problem.

## Problem Context
{problem_context}
{domain_line}

{clauses_heading}
{clauses_context}

## Task
Generate {num_lemmas} lemmas or intermediate clauses that are logical consequences of the given axioms. These lemmas should capture interesting properties, relationships, or simplifications.

## Requirements

**Content Quality:**
- Focus on general lemmas that follow from the existing axioms
- Prioritize general properties, symmetries, or transitivity rules relevant to the domain
- Consider lemmas that simplify complex expressions or establish useful equivalences
- Ensure logical consistency with the given clauses

**Format Specifications:**
- Use TPTP {clause_format} syntax: `{clause_format.lower()}(name, role, clause).`
- Role should be `axiom` for general principles or `lemma` for derived facts
- Match the format of the sample clauses above
{f"- If using TFF format: Include explicit type quantifiers (e.g., `![X: $int]: ...` for integers)" if clause_format == "TFF" else ""}
{f"- If using CNF format: Use disjunctive form (e.g., `p(X) | ~q(Y) | r(Z)`) - clauses are disjunctions of literals separated by `|`" if clause_format == "CNF" else ""}
- Prefer simple forms: unit clauses or binary clauses when possible
- Use descriptive names that indicate the lemma's purpose
- Note: User-defined predicates/functions have no `$` prefix; built-in TPTP symbols like `$int`, `$real` do

## Output Format
For each lemma, provide:
1. The {clause_format} clause
2. A brief 1-sentence explanation of why this lemma could be useful

## Example
{f"tff(transitivity_leq, axiom, ![X: $int, Y: $int, Z: $int]: ((leq(X, Y) & leq(Y, Z)) => leq(X, Z)))." if clause_format == "TFF" else "cnf(transitivity_leq, axiom, ~leq(X, Y) | ~leq(Y, Z) | leq(X, Z))."}

Explanation: Establishes transitivity of the user-defined leq (less-than-or-equal) predicate, enabling chaining of inequalities.

---

Please generate the {num_lemmas} lemmas now.
"""
        return prompt

    def _parse_schema_response(self, function_args: Dict[str, Any]) -> List[SuggestedLemma]:
        """Parse structured schema response from function call."""
        lemmas = []
        lemma_data_list = function_args.get("lemma_clauses", [])

        for item in lemma_data_list:
            clause = item.get("clause", "").strip()
            explanation = item.get("explanation", "").strip()
            confidence = item.get("confidence", 1.0)

            if clause:
                lemmas.append(
                    SuggestedLemma(
                        content=clause,
                        description=explanation,
                        confidence=confidence,
                    )
                )

        return lemmas

    def extract_problem_context(self, problem_file: Path) -> str:
        """Extract problem context from TPTP file (header comments only)."""
        context_lines = []
        with open(problem_file, "r") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("%"):
                    context_lines.append(line)
                elif context_lines and not line.startswith("%") and line:
                    break

        return "\n".join(context_lines) if context_lines else "No context available"
