# IFRS 17 Term Life Valuation Engine

**A portfolio-grade IFRS 17 Term Life valuation engine built to be inspected, challenged, tested, and improved.**

A modular Python valuation engine for **term-life insurance** built as an actuarial science portfolio project. The engine demonstrates the main IFRS 17 measurement flow: policy-level projection, cashflow modelling, discounting, BEL, Risk Adjustment, CSM roll-forward, onerous contract testing, IFRS 17-style grouping, scenario analysis, and audit outputs.

This project is designed to show actuarial modelling, Python engineering, and IFRS 17 awareness in a clear, interview-ready way.

> Academic scope: this is an educational and CV/portfolio project. It is not a production IFRS 17 system. A production model would require formal methodology approval, assumption governance, calibration, controls, reconciliations, data lineage, and independent validation.

## Project Overview

This project is a Python-based modular actuarial valuation engine focused on **Term Life** portfolios under a **simplified IFRS 17 framework**. It calculates projection tables, cashflows, BEL, RA, CSM, grouping outputs, scenario results, and audit outputs. The architecture emphasizes **modularity, traceability, testability, explainability, and auditability**.

It is primarily a **CV / portfolio** project intended to demonstrate IFRS 17 reasoning, actuarial modeling, software engineering discipline, and model governance awareness. It is intentionally designed to be **reviewed, challenged, tested, and improved** by others.

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
- Writes CSV, Excel, audit report, assumption snapshot, BEL diagnostics, and run registry outputs.
- Includes automated tests for calculation identities and actuarial invariants.

## What This Project Is

- A portfolio-grade actuarial engineering project
- A simplified IFRS 17 Term Life valuation engine
- A modular Python-based valuation framework
- A learning-oriented and challengeable model
- A demonstration of BEL, RA, CSM, grouping, scenarios, diagnostics, reconciliation and audit outputs
- A project intended to show actuarial reasoning, technical implementation, and model governance awareness

## What This Project Is Not

- It is not a production IFRS 17 system
- It is not a regulatory reporting tool
- It is not official accounting or actuarial advice
- It is not a replacement for company-grade IFRS 17 models
- It is not calibrated to real company experience data unless explicitly extended

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

- `FORMULAS/To_Inform.txt`
- `FORMULAS/Bilgilendirme.txt`
- `DOCUMENTS/ACTUARIAL_METHODOLOGY_VALIDATION_REPORT.md`

## Challenge This Project

This project is intentionally designed to be inspectable and challengeable. Reviewers are encouraged to question the assumptions, formulas, architecture, and outputs. In particular, challenge:

- BEL sign convention
- Cash flow timing assumptions
- Premium, claims, expense and reinsurance treatment
- Risk Adjustment methodology
- CSM treatment
- IFRS 17 grouping logic
- Scenario assumptions
- Diagnostic and reconciliation outputs
- Model governance choices
- Test coverage
- Code architecture and maintainability

The goal of this repository is not to claim production-level IFRS 17 compliance, but to demonstrate actuarial reasoning, model governance awareness, and software engineering discipline in a transparent way.

## Repository Structure

```text
config/      Model assumptions and run configuration
data/        Sample mortality table
DOCUMENTS/   Methodology and validation report
engine/      Core calculation modules
FORMULAS/    Formula and methodology notes
model/       Pydantic configuration model
tests/       Automated validation and regression tests
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

## Technical Highlights

- **Modular workflow:** assumptions/config → projection → cashflows → BEL → RA → CSM → grouping → scenarios → outputs/audit
- **Pydantic** configuration validation
- **Pandas / NumPy** calculation layer
- **pytest** validation tests
- **logging** and audit trail
- **CSV, Excel and JSON outputs**
- **deterministic assumption snapshot / hash** for audit traceability
- **scenario analysis** with configurable shocks
- **optional BEL diagnostics** for explainability

### BEL Highlights

- **Liability-positive convention:** BEL = PV(outflows) - PV(inflows)
- **Per-policy breakdown:**
	- bel_per_policy
	- pv_bel_outflows
	- pv_bel_inflows
	- pv_claims
	- pv_surrender_benefits
	- pv_expenses
	- pv_reinsurance_ceding
	- pv_reinsurance_recovery
	- pv_counterparty_default_cost
	- pv_premiums
	- pv_death_benefits
	- bel_sign_explanation
- **Diagnostics:** build_bel_diagnostic_summary(), _report_bel_diagnostics(), get_last_bel_diagnostic_summary()
- **Audit JSON outputs:** audit_report.json, bel_diagnostics.json
- **Governance improvement:** Base BEL diagnostics are captured explicitly and protected from scenario overwrite risk
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
bel_diagnostics.json
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
- diagnostics disabled behavior
- base diagnostics ownership under scenarios

## Diagnostics and Governance

- Diagnostics are optional and controlled by `enable_bel_diagnostics` in `config.json`.
- The BEL diagnostic summary is attached to `audit_report.json` as `bel_diagnostics`.
- A standalone `bel_diagnostics.json` is also written for audit workflows.
- Base-run diagnostics are captured immediately after the base `calculate_bel()` call and
	passed explicitly to the output layer to avoid scenario overwrite risk.
- Scenario runs disable diagnostics by default to prevent global-state conflicts.

## Example CV Description

**IFRS 17 Term Life Valuation Engine**  
Built a modular Python engine for term-life insurance valuation under simplified IFRS 17 logic, including policy-level projection, mortality/lapse modelling, cashflow generation, BEL, stochastic Risk Adjustment, CSM roll-forward, onerous contract testing, IFRS 17-style grouping, scenario analysis, audit snapshots, and automated validation tests.

## Suggested CV / LinkedIn Description

**English:**
Developed a portfolio-grade IFRS 17 Term Life valuation engine in Python, designed as a transparent and challengeable actuarial engineering project with modular BEL/RA/CSM calculations, scenario analysis, diagnostics, reconciliation checks, and audit-ready JSON outputs.

**Turkish:**
Python ile portfolio-grade bir IFRS 17 Term Life valuation engine geliştirdim. Proje; BEL/RA/CSM hesaplamaları, senaryo analizleri, reconciliation kontrolleri, diagnostic raporlar ve audit-ready JSON çıktılarıyla incelenebilir ve geliştirilebilir bir aktüeryal mühendislik çalışması olarak tasarlandı.

## Tech Stack

- Python 3.11+
- pandas
- NumPy
- Pydantic
- pytest
- openpyxl

## Limitations

This project intentionally uses simplified assumptions and synthetic data. It does not replace a production IFRS 17 platform. In particular:

- The model uses a simplified IFRS 17 framework.
- It is not calibrated to real insurer data by default.
- Mortality, lapse, expense, and scenario assumptions are illustrative unless replaced by real assumptions.
- RA methodology may be simplified.
- CSM treatment is educational / portfolio-grade and may not cover all production IFRS 17 complexities.
- Reinsurance held accounting is simplified if applicable.
- Coverage units, unlocking, transition, and VFA/PAA/GMM distinctions may require extension depending on use case.
- Outputs are for learning, demonstration, and portfolio review purposes.

## License

See `LICENSE`.
