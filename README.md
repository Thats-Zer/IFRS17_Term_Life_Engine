# IFRS 17 Term Life Valuation Engine

[![CI](https://github.com/Thats-Zer/IFRS17_Term_Life_Engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Thats-Zer/IFRS17_Term_Life_Engine/actions/workflows/ci.yml)

**A portfolio-grade IFRS 17 Term Life valuation engine built to be inspected, challenged, tested, and improved.**

This is a Python-based modular actuarial valuation engine for Term Life insurance under a simplified IFRS 17 framework. It covers projection, cashflows, BEL, RA, CSM, grouping, scenarios, and outputs/audit.

The project is a portfolio-grade CV project. It is intended to demonstrate actuarial engineering, model governance awareness, auditability, and testable Python design. It is not a production IFRS 17 system and is not a regulatory reporting tool.

## What This Project Is

- A portfolio-grade actuarial engineering project
- A simplified IFRS 17 Term Life valuation engine
- A modular Python valuation framework
- A learning-oriented and challengeable model
- A demonstration of model governance and auditability

## What This Project Is Not

- Not a production IFRS 17 system
- Not a regulatory reporting tool
- Not official accounting or actuarial advice
- Not a replacement for company-grade IFRS 17 models
- Not calibrated to real company data by default

## Quickstart

Windows PowerShell:

```powershell
git clone https://github.com/Thats-Zer/IFRS17_Term_Life_Engine.git
cd IFRS17_Term_Life_Engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run quality checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check scripts tests main.py engine model
.\.venv\Scripts\python.exe -m black --check scripts tests main.py engine model
.\.venv\Scripts\python.exe -m mypy engine model main.py
```

## Architecture

The project follows a layered valuation engine design. Each stage produces structured tabular outputs that can be inspected, reconciled, tested, and challenged.

```mermaid
flowchart LR
    A[Config / Assumptions] --> B[Projection]
    B --> C[Cashflows]
    C --> D[BEL]
    D --> E[RA]
    D --> F[CSM]
    E --> F
    F --> G[Grouping]
    G --> H[Outputs / Audit]
    C --> I[Scenarios]
    I --> H
```

See [`docs/architecture.md`](docs/architecture.md) for detailed architecture notes.

## Technical Highlights

- **Pydantic config validation** for assumptions and model settings
- **Pandas / NumPy** calculation layer for projection and valuation tables
- **pytest** validation suite for core mechanics and regression checks
- **GitHub Actions CI/CD** for automated quality gates
- **Ruff / Black / Mypy** for linting, formatting, and static type checks
- **Current coverage: 69%**, with a documented target of **90%+**
- **Benchmark tooling** through `scripts/benchmark_engine.py`
- **Sample data validation** for optional external policy input
- **Audit JSON outputs** including assumption snapshots, audit reports, and run metadata
- **BEL diagnostics** for explainability and reconciliation review

## BEL Diagnostics and Audit Outputs

BEL uses a liability-positive convention:

```text
BEL = PV(outflows) - PV(inflows)
```

The BEL output includes a per-policy breakdown of present value outflows and inflows, including claims, surrender benefits, expenses, reinsurance ceding, reinsurance recovery, counterparty default cost, premiums, and death benefits.

The core reconciliation is:

```text
bel_per_policy = pv_bel_outflows - pv_bel_inflows
```

The engine writes audit-oriented JSON outputs:

- `bel_diagnostics.json`: BEL diagnostic summary for reviewer inspection
- `audit_report.json`: assumption hash, row counts, reconciliation totals, diagnostics, and run metadata

Base BEL diagnostics are captured explicitly after the base BEL calculation and passed to the output layer. Scenario runs disable diagnostics by default so the base diagnostic summary is protected from scenario overwrite risk.

## Sample Data and Data Lineage

Sample synthetic data is provided under `data/sample`:

- `data/sample/sample_policies.csv`
- `data/sample/sample_mortality_table.csv`
- `data/sample/sample_config.json`

The sample dataset is synthetic and designed for inspection and reproducibility. The engine can optionally load external policy input through `sample_policy_path` in the config.

Input validation checks required fields, unique policy IDs, non-negative sum assured, valid issue ages, positive coverage years, and missing values.

Data lineage is covered in [`docs/methodology.md`](docs/methodology.md) and [`docs/architecture.md`](docs/architecture.md).

## Performance Benchmark

An optional benchmark script is available:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_engine.py --policies 10000
```

Benchmarks are machine-dependent and should be interpreted as local performance observations, not certified production performance.

| Policies | Projection Years | Runtime | Peak Memory | Notes |
|----------|------------------|---------|-------------|-------|
| 10,000 | TBD | TBD | TBD | Local benchmark |
| 50,000 | TBD | TBD | TBD | Local benchmark |
| 100,000 | TBD | TBD | TBD | Optional large run |

## Challenge This Project

This project is intentionally inspectable and challengeable. Reviewers are invited to question the model design and implementation, especially:

- BEL convention
- Timing assumptions
- RA methodology
- CSM treatment
- Grouping logic
- Scenario assumptions
- Diagnostics
- Tests
- Architecture

The goal is not to claim production-level IFRS 17 compliance. The goal is to make the actuarial logic and engineering choices visible enough to be reviewed, debated, and improved.

## Limitations

See [`docs/model_limitations.md`](docs/model_limitations.md) for the full limitations statement.

Key limitations:

- Simplified IFRS 17 framework
- Not production-ready
- Not suitable for regulatory reporting
- Synthetic/sample data by default
- Illustrative assumptions unless replaced
- Simplified RA, CSM, grouping, and reinsurance treatment
- Full transition mechanics are not implemented unless explicitly present
- PAA, VFA, and GMM distinctions may be simplified

## Suggested CV Description

**English:**

Developed a portfolio-grade IFRS 17 Term Life valuation engine in Python, designed as a transparent and challengeable actuarial engineering project with modular BEL/RA/CSM calculations, scenario analysis, diagnostics, reconciliation checks, and audit-ready JSON outputs.

**Turkish:**

Python ile portfolio-grade bir IFRS 17 Term Life valuation engine geliştirdim. Proje; BEL/RA/CSM hesaplamaları, senaryo analizleri, reconciliation kontrolleri, diagnostic raporlar ve audit-ready JSON çıktılarıyla incelenebilir ve geliştirilebilir bir aktüeryal mühendislik çalışması olarak tasarlandı.

## Roadmap

- Coverage toward 90%+
- Streamlit or notebook demo
- Richer coverage units
- Assumption unlocking
- Transition approach
- Expanded RA methodology
- Benchmark results
- Deeper data lineage documentation

## Documentation

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/methodology.md`](docs/methodology.md)
- [`docs/model_limitations.md`](docs/model_limitations.md)
- [`docs/coverage_plan.md`](docs/coverage_plan.md)

## License

See [`LICENSE`](LICENSE).
