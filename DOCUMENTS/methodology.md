# Methodology

## 1. Purpose and Scope

This project is a portfolio-grade IFRS 17 Term Life valuation engine. It models a simplified but explainable IFRS 17 principles-aligned valuation workflow for term life insurance contracts.

The purpose is educational and demonstrative: to show actuarial engineering, model structure, testability, diagnostics, and audit-oriented output design. It is not a production IFRS 17 system, not a regulatory reporting tool, and not official actuarial or accounting advice.

The engine focuses on:

- Policy projection
- Insurance cashflows
- Best Estimate Liability (BEL)
- Risk Adjustment (RA)
- Contractual Service Margin (CSM)
- Simplified IFRS 17 grouping
- Scenario and sensitivity analysis
- Diagnostics, audit files, and reproducible outputs

## 2. End-to-End Valuation Workflow

The valuation workflow follows a layered sequence:

```text
config / assumptions
-> projection
-> cashflows
-> BEL
-> RA
-> CSM
-> grouping
-> scenarios
-> outputs / audit
```

Each stage has a focused responsibility:

- `config / assumptions`: Defines model parameters, portfolio size, projection horizon, mortality, lapse, expense, discount, reinsurance, scenario, and diagnostic settings.
- `projection`: Creates policy-year records for each contract and projection year.
- `cashflows`: Calculates premiums, claims, expenses, surrender benefits, reinsurance flows, default costs, totals, and present value columns.
- `BEL`: Calculates liability-positive best estimate liability at policy level using discounted inflows and outflows.
- `RA`: Calculates a simplified risk adjustment using scenario distribution logic and cost-of-capital scaling.
- `CSM`: Calculates initial CSM, onerous loss, and simplified release / roll-forward outputs where implemented.
- `grouping`: Assigns simplified IFRS 17-style groups using portfolio, cohort, risk, and profitability attributes.
- `scenarios`: Runs deterministic sensitivity shocks and summarizes scenario-level impacts.
- `outputs / audit`: Saves CSV, optional Excel, JSON diagnostics, assumption snapshots, hashes, and audit summaries.

## 3. Projection Methodology

The engine supports both synthetic policy portfolios and sample policy data. Synthetic portfolios use deterministic random generation where applicable, controlled by a configurable random seed.

Policy attributes include:

- `policy_id`
- `issue_age`
- `sum_assured`
- `coverage_years`
- `issue_year`
- `portfolio_id`

The projection expands policies into policy-year rows. Each row represents a contract in a projection year, with current age, coverage status, mortality, lapse, and survival information.

Mortality can be read from a mortality table when configured. The default mortality input uses a 1958 CSO mortality table. If a table is not used, the engine applies fallback mortality logic based on issue age and configured mortality factors. Mortality shocks can be applied for scenario testing.

Lapse assumptions are modeled through a configurable lapse curve, including an initial lapse rate and decay. Lapse shocks can be applied in scenario runs.

The survival ratio is an opening-of-period survival measure. It is used to scale in-force exposures and cashflows consistently across projection years. In-force logic is based on whether the projection year falls within the policy coverage period.

## 4. Cashflow Methodology

The cashflow layer calculates insurance inflows and outflows at policy-year level.

Inflows include:

- Gross premium inflows
- Reinsurance recoveries, where applicable

Outflows include:

- Death benefit outflows
- Surrender benefits, where applicable
- Operating expenses
- Acquisition, administration, maintenance, and collection expenses where configured
- Reinsurance ceding premiums, where applicable
- Counterparty default cost, where applicable

The layer also calculates:

- Total inflows
- Total outflows
- Net cashflow
- Present value cashflow columns used by BEL and reconciliation tests

The assumptions are intentionally illustrative and are not calibrated to insurer experience data. A future extension would include mortality, lapse, expense, and premium calibration using real or publicly documented experience studies.

## 5. Discounting and Timing Convention

The engine applies an explicit timing convention:

- Beginning-of-year cashflows use `discount_factor_opening`.
- End-of-year cashflows use `discount_factor`.

Premiums and reinsurance ceding premiums are treated as beginning-of-year cashflows and discounted with the opening discount factor.

Claims, expenses, surrender benefits, reinsurance recoveries, and counterparty default costs are treated as end-of-year cashflows and discounted with the closing discount factor.

This timing convention is important because BEL reconciliation depends on comparing cashflows on a consistent present value basis.

## 6. BEL Methodology

The BEL uses a liability-positive convention:

```text
BEL = PV(outflows) - PV(inflows)
```

Interpretation:

- `BEL > 0`: liability-like position, where present value outflows exceed present value inflows.
- `BEL < 0`: asset-like position, where present value inflows exceed present value outflows.

The engine calculates row-level policy-year present values and aggregates them to policy level as summed policy-year PV totals. The policy-level reconciliation is:

```text
bel_per_policy = pv_bel_outflows - pv_bel_inflows
```

The BEL output includes a transparent per-policy breakdown:

- `bel_per_policy`
- `pv_bel_outflows`
- `pv_bel_inflows`
- `pv_claims`
- `pv_surrender_benefits`
- `pv_expenses`
- `pv_reinsurance_ceding`
- `pv_reinsurance_recovery`
- `pv_counterparty_default_cost`
- `pv_premiums`
- `pv_death_benefits`
- `bel_sign_explanation`

This design makes the BEL result explainable and testable without claiming full IFRS 17 production compliance.

## 7. Risk Adjustment Methodology

The RA methodology is simplified and portfolio-grade. It is intended to demonstrate actuarial engineering logic, not to replace a production IFRS 17 RA framework.

The implemented approach uses stochastic scenario-style variability around key liability cashflow assumptions. Policy-level present values are simulated across risk scenarios, an expected present value and tail present value are compared at the configured confidence level, and the excess is scaled by the configured cost-of-capital ratio.

In simplified form:

```text
RA = max(tail PV - expected PV, 0) * cost-of-capital ratio
```

The RA is combined with BEL in the CSM calculation. It should be interpreted as an illustrative risk adjustment, not as a calibrated production measure.

## 8. CSM Methodology

The initial CSM logic follows the simplified relationship:

```text
initial_csm = max(-(BEL + RA), 0)
onerous_loss = max(BEL + RA, 0)
```

BEL is already net of premium inflows, so premiums are not subtracted again in the CSM calculation.

Interpretation:

- Profitable policies or groups produce positive CSM and no immediate onerous loss.
- Onerous policies or groups produce an immediate loss and zero initial CSM.

The project includes simplified CSM release and roll-forward logic where implemented, including coverage-unit style release mechanics. These are educational approximations and do not represent a complete production IFRS 17 CSM subledger.

## 9. Grouping Methodology

The grouping layer implements simplified IFRS 17-style grouping.

Grouping considers:

- Business nature / portfolio anchor
- Annual cohort
- Risk characteristics such as mortality, lapse, and reinsurance buckets
- Profitability or onerous status

Grouping matters under IFRS 17 because measurement and loss recognition are generally assessed at group level. This project keeps grouping transparent and challengeable, while simplifying the full interpretation and operational requirements of IFRS 17 grouping.

## 10. Scenario Methodology

The engine includes deterministic scenario runs for sensitivity analysis:

- `mortality_up_10`
- `lapse_up_20`
- `expense_up_15`
- `discount_down_100bps`

Scenarios are used to understand directional sensitivity rather than to provide a full capital or regulatory stress framework.

Scenario outputs are separated from the base run. Base BEL diagnostics are captured explicitly before scenario execution and passed to the output / audit layer. Scenario diagnostics are disabled in the main audit flow to avoid overwriting the base diagnostic snapshot.

## 11. Diagnostics and Audit Methodology

The project emphasizes auditability and model governance.

Diagnostics and audit outputs include:

- BEL diagnostic summary
- `audit_report.json`
- `bel_diagnostics.json`
- `assumption_snapshot.json`
- Deterministic assumption hash
- Row counts by output table
- Reconciliation totals
- Base BEL diagnostics captured explicitly and passed to the output / audit layer

These outputs help reviewers trace assumptions, understand key totals, and challenge model behavior.

## 12. Testing and Validation

The repository includes automated tests and quality gates.

Validation coverage includes:

- Pytest-based validation
- BEL reconciliation tests
- Discount timing tests
- CSM correctness tests
- Diagnostics enabled / disabled tests
- Sample data validation tests
- CI quality gates

Current test coverage is 79%. The stated coverage target is 90%+.

The tests validate key mechanics, but they do not replace actuarial model validation by qualified professionals.

## 13. Limitations

This project is intentionally scoped as a simplified IFRS 17 principles-aligned engine.

Key limitations:

- It is not production-ready.
- It is not suitable for regulatory reporting.
- It uses synthetic or sample data by default.
- Assumptions are illustrative and are not calibrated to insurer experience data.
- The default mortality input uses a 1958 CSO mortality table, but this should not be interpreted as real insurer calibration.
- RA methodology is simplified.
- CSM treatment is simplified.
- Full transition mechanics are not implemented unless explicitly present in the codebase.
- PAA, VFA, and GMM distinctions may be simplified.
- Reinsurance held accounting may be simplified.

These limitations are scope boundaries, not defects. They keep the project understandable, testable, and challengeable as a portfolio-grade actuarial engineering project.

## 14. Future Improvements

Potential improvements include:

- Stronger coverage-unit methodology
- Assumption unlocking
- Transition approach support
- Cohort-level CSM
- Reinsurance held measurement
- Richer RA methodology, including confidence-level and cost-of-capital alternatives
- Richer scenario framework
- Dashboard or interactive demo
- Mortality, lapse, expense, and premium calibration using real or publicly documented experience studies
- Expanded test coverage toward 90%+
