# IFRS 17 Term Life Engine

## Actuarial Methodology and Validation Report

**Project type:** Academic / CV portfolio project  
**Product scope:** Term-life insurance  
**Measurement basis:** Simplified IFRS 17 General Measurement Model concepts  
**Data basis:** Synthetic policy portfolio and sample mortality table  
**Methodology status:** Educational model, not production-approved  

## 1. Executive Summary

This report documents the actuarial methodology, assumptions, validation checks, and limitations of the IFRS 17 Term Life Valuation Engine.

The engine projects a synthetic portfolio of term-life insurance contracts at policy-year level and calculates expected cashflows, discounting, Best Estimate Liability, Risk Adjustment, Contractual Service Margin, onerous contract indicators, IFRS 17-style groups, scenario results, and audit outputs.

The model is suitable as a final-year actuarial science portfolio project. It demonstrates understanding of insurance cashflow projection, present value measurement, non-financial risk allowance, CSM mechanics, scenario testing, and model validation practices. It is not intended for regulatory reporting or financial statement production.

## 2. Product and Portfolio Scope

The model represents a simplified term-life product with the following features:

- fixed term coverage
- annual projection periods
- mortality risk
- lapse risk
- premium inflows
- death benefit outflows
- operating expense outflows
- term-life surrender benefit logic, defaulting to zero cash surrender value
- simplified reinsurance ceding and recovery
- simplified counterparty default cost

The portfolio is synthetically generated because real actuarial insurance datasets are normally confidential. This is an expected constraint in actuarial student projects, especially for life insurance where policy-level data can include sensitive demographic, financial, underwriting, and claims information.

## 3. Data and Assumptions

The engine uses:

- synthetic policy master data generated from configuration assumptions
- a sample mortality table stored in `data/mortality_table.csv`
- deterministic lapse assumptions
- deterministic expense assumptions
- flat discount-rate assumptions with scenario shifts
- stochastic Risk Adjustment simulations based on configured volatilities

Key assumptions are stored in `config/config.json` and validated through the Pydantic model in `model/config_model.py`.

Each run can produce:

- `assumption_snapshot.json`
- `audit_report.json`
- `run_registry.csv`

These outputs provide lightweight governance metadata, including assumption hash, methodology version, approval status, data lineage paths, row counts, and reconciliation totals.

## 4. Projection Methodology

The model creates a policy-year projection grid. For each policy and year, it calculates:

- current age
- coverage status
- mortality rate
- lapse rate
- survival multiplier
- opening survival ratio
- sum assured
- issue year
- portfolio identifier

The survival convention is:

```text
survival_multiplier(t) = (1 - qx(t)) * (1 - lapse_rate(t))
survival_ratio(t) = product of survival_multiplier from year 1 to year t-1
```

Therefore, year 1 has an opening survival ratio of 1.

## 5. Cashflow Methodology

The engine calculates the following cashflow components:

- gross premium inflow
- net premium inflow
- death benefits
- surrender benefit
- operating expenses
- reinsurance ceding
- reinsurance recovery
- counterparty default cost
- total inflows
- total outflows
- net cashflow

Premiums are priced using a simplified present value approach. Gross premiums include loading for profit margin, contingency loading, and collection cost.

## 6. Discounting Methodology

The model uses separate discount factors for different cashflow timings:

```text
discount_factor(t) = 1 / (1 + r)^t
discount_factor_opening(t) = 1 / (1 + r)^(t - 1)
```

Timing convention:

- premium inflows use opening discount factors
- reinsurance ceding uses opening discount factors
- claims, expenses, surrender benefits, reinsurance recoveries, and default costs use closing discount factors

This distinction is covered by automated validation tests.

## 7. BEL Methodology

BEL is calculated using a liability-positive convention:

```text
BEL = PV(outflows) - PV(inflows)
```

Interpretation:

- positive BEL means net liability
- negative BEL means net asset

Cashflows and BEL use the same adjusted mortality basis:

```text
adjusted_qx = qx * (1 - lapse_mortality_correlation * lapse_rate)
```

Death benefits, reinsurance recoveries, BEL, RA, and CSM diagnostics use this same adjusted death-benefit basis. The adjustment is a simplified selection-effect assumption and should not be interpreted as calibrated production behaviour.

## 8. Risk Adjustment Methodology

Risk Adjustment is calculated using a simplified stochastic confidence-level method:

```text
RA = CoC ratio * max(quantile(PV liability) - mean(PV liability), 0)
```

Risk drivers include:

- mortality volatility
- lapse volatility
- expense volatility
- counterparty default events

The approach is appropriate for an educational model but is not a substitute for a formally approved IFRS 17 Risk Adjustment methodology.

## 9. CSM Methodology

The engine calculates fulfilment cashflows as:

```text
total_liability = BEL + RA
```

Initial CSM:

```text
initial_csm = max(-(BEL + RA), 0)
```

Onerous loss:

```text
onerous_loss = max(BEL + RA, 0)
```

This avoids double-counting premiums because BEL already includes premium inflows.

CSM release is allocated using simplified coverage units:

```text
coverage_unit(t) = in_force(t) * survival_ratio(t) * (1 - lapse_rate(t))
```

The current implementation produces a single reporting-period roll-forward based on `reporting_year`.

## 10. IFRS 17 Grouping Methodology

The grouping module assigns IFRS 17-style groups using:

- portfolio group
- annual cohort
- profitability bucket
- mortality/lapse/reinsurance risk group
- onerous status

Profitability buckets include:

- onerous
- no significant possibility of becoming onerous
- other profitable

The model uses synthetic portfolio fields where real policy administration data is unavailable. This is acceptable for an academic model but would need replacement with real portfolio and issue-date data in production.

## 11. Scenario Testing

The engine supports scenario analysis by rebuilding projection, cashflows, BEL, RA, and CSM under shocked assumptions.

Included scenario types:

- mortality increase
- lapse increase
- expense increase
- discount-rate decrease

Scenario outputs include total BEL, total RA, CSM opening, CSM closing, onerous count, and onerous loss.

## 12. Validation Performed

Automated tests cover:

- module imports
- discount curve uniqueness
- projection schema
- discount curve merge integrity
- cashflow and BEL smoke checks
- float64 precision mode
- PV cashflow component timing
- initial CSM formula
- grouping policy counts
- opening survival ratio identity
- premium and claim discount timing
- BEL reconciliation to adjusted liability cashflows
- CSM release allocation
- mortality shock direction
- audit snapshot determinism
- audit registry creation
- IFRS 17-style grouping fields

Current test command:

```powershell
python -m pytest -q
```

Expected result at the time of this report:

```text
17 passed
```

## 13. Limitations

The model has the following limitations:

- policy data is synthetic
- assumptions are not calibrated to insurer experience
- mortality and lapse behaviour are simplified
- Risk Adjustment is educational, not production-approved
- CSM methodology is simplified
- grouping is IFRS 17-style but not a full insurer implementation
- no full financial statement disclosure package is produced
- audit outputs are lightweight metadata, not a formal governance workflow
- no independent actuarial peer review has been performed

## 14. Conclusion

This engine is a strong actuarial science portfolio project. It demonstrates practical understanding of life insurance projection, IFRS 17 measurement concepts, model structure, scenario testing, auditability, and automated validation.

The model is suitable for CV and interview discussion, especially for actuarial internship, junior actuarial analyst, insurance risk, or valuation-oriented roles.
