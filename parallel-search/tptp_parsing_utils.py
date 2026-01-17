"""TPTP parsing utilities for Parallel Vampire Search.

This module provides shared parsing utilities for handling TFF (Typed First-order
Form) and CNF (Clause Normal Form) clauses from Vampire's clausify/tclausify modes.
These utilities are used by multiple modules to parse, manipulate, and transform
TPTP clauses.

Typical usage:
    from tptp_parsing_utils import parse_tff_clause, parse_cnf_clause, Clause, ClauseRole

    clause = parse_tff_clause("tff(u1, axiom, p(X)).", logger)
    clause = parse_cnf_clause("cnf(c1, axiom, p(X) | q(Y)).", logger)
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


def strip_quantifiers(formula: str) -> str:
    """Strip type quantifiers from a TFF formula.

    Removes patterns like:
    - ![X0] :
    - ![X0, X1, X2] :
    - ![X0 : $int] :
    - ![X0 : $int, X1 : $real] :
    - ?[X0] : (existential)

    Args:
        formula: TFF formula with quantifiers.

    Returns:
        Formula with quantifiers stripped.
    """
    formula = formula.strip()

    # Match quantifier patterns: ![...] : or ?[...] :
    # We need to handle nested brackets in type annotations
    if formula.startswith("!") or formula.startswith("?"):
        # Find the matching ] for the opening [
        if "[" in formula:
            bracket_depth = 0
            i = formula.index("[")
            while i < len(formula):
                if formula[i] == "[":
                    bracket_depth += 1
                elif formula[i] == "]":
                    bracket_depth -= 1
                    if bracket_depth == 0:
                        # Found the closing bracket
                        # Now look for the colon after it
                        j = i + 1
                        while j < len(formula) and formula[j].isspace():
                            j += 1
                        if j < len(formula) and formula[j] == ":":
                            # Skip the colon and any whitespace
                            j += 1
                            while j < len(formula) and formula[j].isspace():
                                j += 1
                            return formula[j:]
                        break
                i += 1

    return formula


def strip_outer_parentheses(formula: str) -> str:
    """Strip outermost parentheses if they wrap the entire formula.

    Args:
        formula: Formula potentially wrapped in parentheses.

    Returns:
        Formula with outermost parentheses removed if applicable.
    """
    formula = formula.strip()

    if not (formula.startswith("(") and formula.endswith(")")):
        return formula

    # Check if the outer parentheses match and wrap the whole thing
    depth = 0
    for i, char in enumerate(formula):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            # If we hit 0 before the end, outer parens don't wrap everything
            if depth == 0 and i < len(formula) - 1:
                return formula

    # Outer parentheses wrap everything, remove them
    return formula[1:-1].strip()


class ClauseRole(Enum):
    """TPTP clause roles."""

    AXIOM = "axiom"
    HYPOTHESIS = "hypothesis"
    NEGATED_CONJECTURE = "negated_conjecture"
    CONJECTURE = "conjecture"
    LEMMA = "lemma"
    THEOREM = "theorem"
    DEFINITION = "definition"
    UNKNOWN = "unknown"


@dataclass
class Clause:
    """Represents a single TPTP clause (TFF or CNF format).

    Attributes:
        name: Clause identifier (e.g., "u12", "c1").
        role: TPTP role (axiom, hypothesis, negated_conjecture, etc.).
        literals: Clause content (for TFF: with quantifiers stripped; for CNF: disjunction of literals).
        original_line: Full TPTP line for reconstruction.
    """

    name: str
    role: ClauseRole
    literals: str
    original_line: str

    def __str__(self) -> str:
        return self.original_line

    def __repr__(self) -> str:
        return f"Clause({self.name}, {self.role.value})"


def parse_tff_clause(line: str, logger: Optional[logging.Logger] = None) -> Optional[Clause]:
    """Parse a TFF (Typed First-order Form) clause.

    Handles quantified formulas from tclausify mode, stripping quantifiers
    and extracting the clause content.

    Args:
        line: TFF clause line (may be multi-line joined with spaces).
        logger: Optional logger for warning messages.

    Returns:
        Parsed Clause object, or None if parsing fails.

    Example:
        parse_tff_clause("tff(u10,axiom, (![X0] : ((mult(e,X0) = X0)))).", logger)
        -> Clause with literals: mult(e,X0) = X0
    """
    try:
        # Extract clause name
        name_start = line.index("tff(") + 4
        name_end = line.index(",", name_start)
        name = line[name_start:name_end]

        # Extract role
        role_start = name_end + 1
        role_end = line.index(",", role_start)
        role_str = line[role_start:role_end].strip()

        try:
            role = ClauseRole(role_str)
        except ValueError:
            role = ClauseRole.UNKNOWN

        # Extract formula (everything between role and final ").")
        formula_start = role_end + 1
        formula_end = line.rindex(").")
        formula = line[formula_start:formula_end].strip()

        # First strip one layer of outer parentheses to expose quantifiers
        formula = strip_outer_parentheses(formula)

        # Strip quantifiers: ![X0] : or ![X0, X1] : or ![X0 : $int] :
        formula = strip_quantifiers(formula)

        # Strip remaining outer parentheses if they wrap the entire formula
        # May need to do this multiple times for nested wrapping
        prev_formula = None
        while prev_formula != formula:
            prev_formula = formula
            formula = strip_outer_parentheses(formula)

        return Clause(name=name, role=role, literals=formula, original_line=line)
    except (ValueError, IndexError) as e:
        if logger:
            logger.warning(f"Failed to parse TFF clause: {line[:50]}... ({e})")
        return None


def parse_cnf_clause(line: str, logger: Optional[logging.Logger] = None) -> Optional[Clause]:
    """Parse a CNF (Clause Normal Form) clause.

    CNF format: cnf(name, role, clause).
    where clause is a disjunction of literals (e.g., "p(X) | ~q(Y) | r(Z)").

    Args:
        line: CNF clause line (may be multi-line joined with spaces).
        logger: Optional logger for warning messages.

    Returns:
        Parsed Clause object, or None if parsing fails.

    Example:
        parse_cnf_clause("cnf(c1, axiom, p(X) | ~q(Y) | r(Z)).", logger)
        -> Clause with literals: p(X) | ~q(Y) | r(Z)
    """
    try:
        # Extract clause name, role, and content
        # Pattern: cnf(name, role, clause).
        match = re.match(r"cnf\(([^,]+),\s*([^,]+),\s*(.+)\)\.", line)
        if not match:
            return None

        name = match.group(1).strip()
        role_str = match.group(2).strip()
        clause_content = match.group(3).strip()

        # Map role string to ClauseRole enum
        try:
            role = ClauseRole(role_str)
        except ValueError:
            role = ClauseRole.UNKNOWN

        # For CNF, the literals field stores the clause content (disjunction)
        # CNF clauses are disjunctions: literal1 | literal2 | ...
        literals = clause_content.strip()

        return Clause(name=name, role=role, literals=literals, original_line=line)

    except Exception as e:
        if logger:
            logger.warning(f"Failed to parse CNF clause: {line[:50]}... ({e})")
        return None
