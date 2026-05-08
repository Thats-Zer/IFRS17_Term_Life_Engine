# IFRS 17 Term Life Engine

## Overview
This project is a modular Python valuation engine for **term-life insurance**, designed around core IFRS 17 concepts. It produces:

- **Projection (Policy × Year)**: age-year grid, mortality, lapse, and survival rates
- **Cashflows**: premium inflows, claim/expense outflows, net cashflows
- **Discounting**: discount curve and discounted cashflows
- **BEL (Best Estimate Liability)**
- **RA (Risk Adjustment)** (as implemented in the model)
- **CSM (Contractual Service Margin)**: initial CSM and roll-forward
- **IFRS 17 Grouping & Onerous Testing**
- **Scenario Analysis**: mortality up, lapse up, expense up, discount-rate shock, etc.

> Note: This repository is intended for **academic/portfolio** use. Production use would require additional validation, calibration, governance, and audit trail capabilities.

## Repository Structure
- `config/` : model parameters (`config.json`)
- `data/` : sample mortality table
- `engine/` : calculation modules (projection, cashflows, bel, ra, csm, grouping, scenarios, outputs)
- `model/` : Pydantic configuration model
- `outputs/` : generated outputs (CSV/Excel)

## Installation
Windows PowerShell:

```powershell
cd "C:\Users\sevva\Desktop\BUSEFERSON\IFRS17_Term_Life_Engine"
python -m pip install -r requirements
```

## Run
```powershell
python main.py
```

## Outputs
Generated under `outputs/`, typically:
- `master_results.csv`
- `projection_results.csv`
- `bel_results.csv`
- `ra_results.csv`
- `csm_results.csv`
- `scenario_results.csv`
- `ifrs17_term_life_projection.xlsx` (large tables may be exported as preview/summary due to Excel row limits)

## Tests
```powershell
python -m pytest -q
```

## Tech Stack
- Python 3.11+
- Pandas / NumPy
- Pydantic

## License
See `LICENSE`.