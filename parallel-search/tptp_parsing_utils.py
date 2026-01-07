"""TPTP parsing utilities for Parallel Vampire Search.

This module provides shared parsing utilities for handling TFF (Typed First-order
Form) clauses from Vampire's tclausify mode. These utilities are used by multiple
modules to parse, manipulate, and transform TFF clauses.

Typical usage:
    from tptp_parsing_utils import strip_quantifiers, strip_outer_parentheses

    formula = "![X: $int]: p(X)"
    clean_formula = strip_quantifiers(formula)
    clean_formula = strip_outer_parentheses(clean_formula)
"""


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
