# Coverage Plan

- Current coverage: 79%
- Target coverage: 90%+

## Priority Areas

- outputs/audit
- cashflows
- CSM
- RA
- grouping
- scenarios

## Testing Approach

- Keep tests deterministic and small.
- Prefer public functions and documented outputs.
- Use compact fixtures instead of large generated datasets.
- Validate key reconciliations and output schemas.
- Avoid brittle tests that duplicate implementation details, depend on log text, or assert incidental row ordering.
