# Coverage Plan

## Current Status

- Coverage is tracked with pytest-cov.
- Latest broad local review check: 90% total coverage with 83 tests passing.
- Target coverage: 90%+

Review command used:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=engine --cov=model --cov=main --cov=scripts --cov-report=term-missing -q
```

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

1. Continue closing the remaining cashflow and scenario branch gaps.
2. Add targeted RA edge case tests with small deterministic data.
3. Expand output/audit edge cases around Excel previews and optional dependencies.
4. Add one or two failure-path tests for main orchestration steps if needed.
5. Re-run coverage and reassess the largest remaining gaps.

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
