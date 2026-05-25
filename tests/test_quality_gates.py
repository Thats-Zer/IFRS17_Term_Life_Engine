from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from engine.bel import calculate_bel
from engine.csm import calculate_initial_csm
from engine.outputs import save_outputs
from model.config_model import ConfigModel


def _minimal_projection() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "policy_id": [1, 2],
            "Year": [1, 1],
            "coverage_years": [1, 1],
            "discount_factor": [0.95, 0.95],
            "discount_factor_opening": [0.97, 0.97],
            "Gross_Premium_Inflow": [100.0, 200.0],
            "Death_Benefits": [150.0, 50.0],
            "Surrender_Benefit": [0.0, 0.0],
            "Operating_Expenses": [10.0, 10.0],
            "Reinsurance_Ceding": [5.0, 5.0],
            "Reinsurance_Recovery": [0.0, 0.0],
            "Counterparty_Default_Cost": [0.0, 0.0],
        }
    )


def test_bel_reconciliation_identity():
    projection = _minimal_projection()
    bel = calculate_bel(projection, ConfigModel())
    diff = bel["pv_bel_outflows"] - bel["pv_bel_inflows"]
    assert np.allclose(bel["bel_per_policy"], diff, atol=1e-6)


def test_bel_sign_explanation_matches_sign():
    projection = _minimal_projection()
    bel = calculate_bel(projection, ConfigModel())
    positive = bel["bel_per_policy"] > 0
    assert (
        bel.loc[positive, "bel_sign_explanation"] == "Liability: PV outflows exceed PV inflows"
    ).all()
    assert (
        bel.loc[~positive, "bel_sign_explanation"] == "Asset-like: PV inflows exceed PV outflows"
    ).all()


def test_discount_timing_reinsurance_and_premiums():
    projection = _minimal_projection()
    bel = calculate_bel(projection, ConfigModel())

    expected_premiums = projection["Gross_Premium_Inflow"] * projection["discount_factor_opening"]
    expected_ceding = projection["Reinsurance_Ceding"] * projection["discount_factor_opening"]
    expected_claims = projection["Death_Benefits"] * projection["discount_factor"]

    assert np.allclose(bel["pv_premiums"], expected_premiums, atol=1e-6)
    assert np.allclose(bel["pv_reinsurance_ceding"], expected_ceding, atol=1e-6)
    assert np.allclose(bel["pv_claims"], expected_claims, atol=1e-6)


def test_csm_formula_matches_bel_ra():
    projection = _minimal_projection()
    bel = calculate_bel(projection, ConfigModel())
    ra = bel[["policy_id"]].assign(ra_per_policy=5.0)

    csm = calculate_initial_csm(bel, ra, ConfigModel(), projection=projection)
    total = bel["bel_per_policy"] + 5.0
    expected_csm = np.maximum(-total, 0.0)
    expected_loss = np.maximum(total, 0.0)

    merged = csm.merge(bel[["policy_id", "bel_per_policy"]], on="policy_id")
    assert np.allclose(merged["initial_csm"], expected_csm, atol=1e-6)
    assert np.allclose(merged["onerous_loss"], expected_loss, atol=1e-6)


def test_config_validation_invalid_rates():
    with pytest.raises(ValidationError):
        ConfigModel(discount_rate=-0.01)


def test_audit_outputs_exist_and_safe(tmp_path):
    projection = _minimal_projection()
    bel = calculate_bel(projection, ConfigModel())
    ra = bel[["policy_id"]].assign(ra_per_policy=0.0)
    csm = calculate_initial_csm(bel, ra, ConfigModel(), projection=projection)

    save_outputs(
        projection=projection,
        bel_result=bel,
        ra_result=ra,
        csm_result=csm,
        scenario_results=None,
        output_dir=str(tmp_path),
        master=projection[["policy_id"]].drop_duplicates(),
        excel_output=False,
        config=ConfigModel(enable_bel_diagnostics=False),
        bel_diagnostics=None,
    )

    report = json.loads((Path(tmp_path) / "audit_report.json").read_text(encoding="utf-8"))
    assert "row_counts" in report
    assert "reconciliation_totals" in report
    assert (Path(tmp_path) / "bel_diagnostics.json").exists()
