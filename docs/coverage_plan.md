# Coverage Plan

## Current Status

- Current coverage: 69%
- Target coverage: 90%+

The goal is to improve confidence in the model mechanics without creating brittle tests that merely duplicate implementation details.

## Priority Areas To Test

Highest-priority areas:

- Projection validation and external sample policy input
- Mortality table fallback behavior
- Cashflow columns and present value columns
- BEL reconciliation
- RA edge cases
- CSM onerous/profitable logic
- Outputs and audit JSON
- Scenario isolation
- Benchmark script smoke behavior

## Suggested High-Value Tests

- Validate external sample policy input accepts valid data and rejects missing required columns.
- Validate duplicate `policy_id` values are rejected.
- Validate negative `sum_assured` and invalid issue ages are rejected.
- Test mortality table interpolation and fallback qx behavior.
- Test projection output includes expected policy-year rows and in-force flags.
- Test cashflow output includes required raw cashflow and PV columns.
- Test opening discount factors are used for premiums and reinsurance ceding.
- Test closing discount factors are used for claims, expenses, surrender, recovery, and default cost.
- Test BEL reconciliation at policy level:

```text
bel_per_policy = pv_bel_outflows - pv_bel_inflows
```

- Test RA with small deterministic inputs and edge cases for confidence level / cost-of-capital settings.
- Test CSM profitable and onerous cases:

```text
initial_csm = max(-(BEL + RA), 0)
onerous_loss = max(BEL + RA, 0)
```

- Test audit JSON contains assumption hash, row counts, reconciliation totals, and BEL diagnostics.
- Test scenario runs do not overwrite base BEL diagnostics.
- Test benchmark script starts and produces a summary for a small policy count.

## Files And Modules Likely Needing Tests

Priority modules:

- `engine/projection.py`
- `engine/cashflows.py`
- `engine/bel.py`
- `engine/ra.py`
- `engine/csm.py`
- `engine/scenarios.py`
- `engine/outputs.py`
- `engine/audit.py`
- `scripts/benchmark_engine.py`
- `model/config_model.py`

Lower-priority modules can be covered through integration-style smoke tests unless they contain important branch logic.

## Order Of Implementation

1. Add projection and sample input validation tests.
2. Add mortality table and fallback tests.
3. Add cashflow column and PV timing tests.
4. Expand BEL reconciliation and diagnostic tests.
5. Add RA edge case tests with small deterministic data.
6. Expand CSM profitable / onerous tests.
7. Add audit JSON structure tests.
8. Add scenario isolation tests.
9. Add benchmark script smoke test.
10. Re-run coverage and reassess the largest remaining gaps.

## What Should Not Be Over-Tested

Avoid over-testing:

- Pandas internals
- NumPy arithmetic behavior
- Exact formatting of log messages
- Exact ordering of unrelated output columns unless the order is part of the public interface
- Large benchmark runtimes in CI
- Random generated values when deterministic invariants are enough

## How To Avoid Brittle Tests

- Prefer invariants and reconciliations over exact row-by-row duplication of implementation logic.
- Use small deterministic fixtures.
- Test public outputs and documented behavior.
- Keep numeric tolerances explicit and appropriate for float32 / float64 behavior.
- Avoid asserting on incidental implementation details.
- Separate fast unit tests from optional large benchmark checks.
- Use scenario names and output schemas as contracts only where they are intended public behavior.
