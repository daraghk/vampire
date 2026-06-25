# Seed Generation Analysis (Strict)

This note summarizes the strict seed-quality analysis from:

- `seed_quality_results_strict.csv`

The strict definition treats a seed as syntactically correct only if it avoids:

- post-parse rejection (`Failed to parse seed clause, skipping`), and
- entailment-stage syntax/type failures (parser/lexer/user-error diagnostics).

## Global Totals

Across 655 problems, expected seeds at 15/problem are:

- `655 * 15 = 9825`

Observed totals:

- `Generated_Seeds_Total = 9808`
- `Strict_Syntactically_Correct_Seeds = 8238`
- `Entailed_Seeds_From_Strict = 7061`

## Count Breakdown

From expected to generated:

- Under-generation: `9825 - 9808 = 17`

From generated to strict syntactically correct:

- Removed as syntactically invalid (strict): `9808 - 8238 = 1570`
  - `Post_Parse_Failures = 5`
  - `Entailment_SyntaxOrType_Failures = 1565`

Strict syntactically correct but not entailed:

- `8238 - 7061 = 1177`
  - `Entailment_Timeout_Failures = 1154`
  - `Entailment_SAT_Not_Entailed = 0`
  - `Entailment_Other_Failures = 23`

## Under-Generation Problems (`Generated_Seeds_Total < 15`)

- GRP203-1 (9 generated; 6 short)
- GRP593-1 (11 generated; 4 short)
- GRP126-4.005 (13 generated; 2 short)
- GRP133-1.003 (13 generated; 2 short)
- GRP614-1 (13 generated; 2 short)
- GRP736-1 (14 generated; 1 short)

## Post-Parse Failure Problems (`Post_Parse_Failures > 0`)

- GRP025-3 (1)
- GRP034-4 (1)
- GRP128-1.004 (1)
- GRP415-1 (2)

## Practical Interpretation

- The dominant source of seeds failing strict syntactic validity is entailment-stage syntax/type errors (1565), not post-parse failures (5).
- The dominant source of non-entailed seeds among strict-valid seeds is timeout (1154 of 1177), with no observed SAT-not-entailed cases.
