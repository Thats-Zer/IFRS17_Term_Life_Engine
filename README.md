# IFRS 17 Term Life Valuation Engine

A modular Python valuation engine for **term-life insurance** built as an actuarial science portfolio project. The engine demonstrates the main IFRS 17 measurement flow: policy-level projection, cashflow modelling, discounting, BEL, Risk Adjustment, CSM roll-forward, onerous contract testing, IFRS 17-style grouping, scenario analysis, and audit outputs.

This project is designed to show actuarial modelling, Python engineering, and IFRS 17 awareness in a clear, interview-ready way.

> Academic scope: this is an educational and CV/portfolio project. It is not a production IFRS 17 system. A production model would require formal methodology approval, assumption governance, calibration, controls, reconciliations, data lineage, and independent validation.

## What It Does

- Builds synthetic term-life policy data.
- Projects each policy by year.
- Applies mortality, lapse, survival, expenses, premium, reinsurance, and counterparty risk assumptions.
- Calculates present value cashflows using separate opening and closing discount factors.
- Calculates **BEL** using a liability-positive convention.
- Calculates a simplified stochastic **Risk Adjustment**.
- Calculates initial **CSM**, onerous loss, CSM release, finance cost, and closing CSM.
- Assigns IFRS 17-style groups by portfolio, annual cohort, profitability bucket, and risk group.
- Runs stress scenarios such as mortality, lapse, expense, and discount-rate shocks.
- Writes CSV, Excel, audit report, assumption snapshot, and run registry outputs.
- Includes automated tests for calculation identities and actuarial invariants.

## Description

**IFRS 17 Term Life Valuation Engine**  
Built a modular Python engine for term-life insurance valuation under simplified IFRS 17 logic, including policy-level projection, mortality/lapse modelling, cashflow generation, BEL, stochastic Risk Adjustment, CSM roll-forward, onerous contract testing, IFRS 17-style grouping, scenario analysis, audit snapshots, and automated validation tests.

## Actuarial Logic

The engine uses the following simplified measurement structure:

- **Projection:** policy-year grid with current age, in-force status, mortality, lapse, and survival.
- **Cashflows:** premiums, death benefits, surrender benefits, operating expenses, reinsurance ceding/recovery, and counterparty default cost.
- **Discounting:** opening factor for premium-like flows and closing factor for claim/expense-like flows.
- **BEL:** liability-positive present value of outflows minus inflows.
- **RA:** simplified stochastic confidence-level approach for non-financial risk.
- **CSM:** `max(-(BEL + RA), 0)` because BEL already includes premium inflows.
- **Onerous loss:** `max(BEL + RA, 0)`.
- **Grouping:** portfolio, annual cohort, profitability bucket, and risk characteristics.

Detailed formula documentation is available in:

- `Formulas/To_Inform.txt`
- `Formulas/Bilgilendirme.txt`
- `docs/ACTUARIAL_METHODOLOGY_VALIDATION_REPORT.md`

## Repository Structure

```text
config/      Model assumptions and run configuration
data/        Sample mortality table
engine/      Core calculation modules
model/       Pydantic configuration model
tests/       Automated validation and regression tests
Formulas/    Formula and methodology notes
outputs/     Generated run outputs, ignored by git
main.py      End-to-end engine runner
```

## Main Modules

```text
engine/projection.py   Master data and policy-year projection
engine/curves.py       Discount and lapse curves
engine/cashflows.py    Premiums, claims, expenses, reinsurance, PV cashflows
engine/bel.py          Best Estimate Liability
engine/ra.py           Risk Adjustment
engine/csm.py          CSM calculation and roll-forward
engine/grouping.py     IFRS 17-style grouping and onerous classification
engine/scenarios.py    Scenario analysis
engine/outputs.py      CSV, Excel, audit, and registry outputs
engine/audit.py        Assumption snapshot, audit report, run metadata
```

## Installation

Windows PowerShell:

```powershell
git clone https://github.com/Thats-Zer/IFRS17_Term_Life_Engine.git
cd IFRS17_Term_Life_Engine
python -m pip install -r requirements
```

## Run

```powershell
python main.py
```

The default configuration is stored in:

```text
config/config.json
```

## Outputs

Running the engine writes files under `outputs/`, including:

```text
master_results.csv
projection_results.csv
bel_results.csv
ra_results.csv
csm_results.csv
group_results.csv
scenario_results.csv
ifrs17_term_life_projection.xlsx
assumption_snapshot.json
audit_report.json
run_registry.csv
```

Generated outputs are ignored by git so the repository stays focused on source code, tests, assumptions, and documentation.

## Tests

```powershell
python -m pytest -q
```

The test suite includes:

- import and smoke tests
- projection and discount-curve checks
- cashflow timing checks
- BEL reconciliation checks
- CSM formula checks
- CSM release allocation checks
- scenario shock behavior checks
- grouping checks
- audit snapshot and run registry checks

## Example CV Description

**IFRS 17 Term Life Valuation Engine**  
Built a modular Python engine for term-life insurance valuation under simplified IFRS 17 logic, including policy-level projection, mortality/lapse modelling, cashflow generation, BEL, stochastic Risk Adjustment, CSM roll-forward, onerous contract testing, IFRS 17-style grouping, scenario analysis, audit snapshots, and automated validation tests.

## Tech Stack

- Python 3.11+
- pandas
- NumPy
- Pydantic
- pytest
- openpyxl

## Limitations

This project intentionally uses simplified assumptions and synthetic data. It does not replace a production IFRS 17 platform. In particular:

- RA and CSM methodologies are educational approximations.
- Mortality, lapse, expense, and reinsurance assumptions are not production-calibrated.
- Grouping is IFRS 17-style but based on synthetic portfolio data.
- Governance and audit outputs are lightweight metadata, not a full approval workflow.
- Financial statement disclosures and formal actuarial validation reports are outside the current scope.

## License

See `LICENSE`.
