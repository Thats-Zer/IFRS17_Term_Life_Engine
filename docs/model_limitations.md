# Model Limitations

## 1. Scope Boundary

This repository is a portfolio-grade, learning-oriented, challengeable IFRS 17 Term Life valuation engine.

It is not:

- A production IFRS 17 system
- A regulatory reporting tool
- Official actuarial advice
- Official accounting advice

It is designed for learning, demonstration, portfolio review, technical challenge, and model governance discussion.

## 2. Data Limitations

The model uses synthetic or sample data by default. It is not calibrated to real insurer experience data unless extended by the user.

The default mortality input uses a 1958 CSO mortality table. This is an illustrative public-style assumption input for demonstration and should not be interpreted as calibration to a real insurer portfolio.

The following assumptions are illustrative unless replaced with calibrated inputs:

- Mortality
- Lapse
- Expenses
- Premiums
- Reinsurance terms
- Counterparty default parameters

## 3. Methodology Limitations

The methodology is simplified and IFRS 17 principles-aligned rather than fully IFRS 17 compliant.

Known methodological boundaries include:

- Simplified IFRS 17 framework
- Simplified Risk Adjustment methodology
- Simplified CSM roll-forward
- Simplified grouping logic
- Simplified reinsurance treatment where applicable
- Limited or no full transition mechanics unless explicitly implemented
- PAA, VFA, and GMM distinctions may not be fully implemented

These choices are intentional so the model remains reviewable and technically challengeable.

### 3.1 Additional Methodology Limitations Based on Reviewer Feedback

The current version is intentionally simplified and does not aim to represent a full production IFRS 17 implementation. Based on reviewer and practitioner feedback, the following areas are acknowledged as important methodology limitations and future improvement points:

- CSM roll-forward: The current CSM treatment is simplified and does not yet fully model the movement from opening CSM to closing CSM across valuation periods.
- Group-level CSM / loss component classification: CSM and loss component classification should be determined at IFRS 17 group level. The current implementation may still use simplified policy-level logic in some areas for educational transparency.
- Valuation year structure: The model requires a clearer distinction between valuation year, calendar year, policy year, issue year, and portfolio state.
- Locked-in rates for CSM: The treatment of discount rates is simplified. A more complete IFRS 17 model should handle locked-in rates for CSM measurement where applicable.
- Experience and assumption variance: Experience variance, assumption variance, model point updates, and projection reruns are not yet separated in a fully production-like way.
- Coverage units and CSM release: Coverage unit methodology and CSM release mechanics are simplified and require further development.
- Grouping policy: Grouping is currently implemented as an educational demonstration and does not represent a fully governed insurer grouping policy.

These limitations are documented intentionally. The purpose of this project is to make the actuarial logic visible, reviewable, and challengeable, rather than to claim production-level IFRS 17 compliance.

## 4. Operational Limitations

The engine is not performance-certified for production use.

Operational boundaries include:

- Benchmarks are machine-dependent.
- Diagnostics can be disabled for larger runs.
- Excel output may be limited by row constraints.
- Runtime behavior depends on the local Python environment and installed dependencies.

## 5. Validation Limitations

Coverage is tracked with pytest-cov. The target is 90%+.

The automated tests validate key mechanics, including projection, discount timing, BEL reconciliation, CSM logic, diagnostics, sample data handling, and quality gates.

The engine writes a structured data validation report for review, but this report is not a substitute for insurer-grade data governance, independent actuarial validation, or regulatory reporting controls.

The tests do not replace full actuarial model validation by qualified professionals.

## 6. Intended Use

The intended uses are:

- CV / portfolio project
- Educational review
- Technical challenge
- Model governance demonstration
- Actuarial engineering showcase

The project is intended to invite questions and scrutiny, not to assert production readiness.

## 7. Future Hardening

Future hardening could include:

- Real calibration data
- Stronger experience studies
- Expanded RA methodology
- More robust coverage-unit methodology
- Assumption unlocking
- IFRS 17 transition mechanics
- Richer governance documentation
- Expanded tests and CI coverage gates
