from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import engine.scenarios as scenarios_module
from engine.csm import (
    calculate_assumption_changes,
    calculate_csm_rollforward,
    calculate_finance_cost,
    calculate_initial_csm,
)
from engine.outputs import save_outputs
from engine.scenarios import apply_scenario, run_scenarios, run_single_scenario
from model.config_model import ConfigModel


def _small_config(**updates):
    base = ConfigModel(
        n_policies=2,
        projection_years=2,
        coverage_years=2,
        random_seed=7,
        n_risk_scenarios=5,
        run_scenarios=False,
        excel_output=False,
        enable_bel_diagnostics=True,
    )
    return base.model_copy(update=updates)


def _bel_result() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "policy_id": [1, 2],
            "bel_per_policy": [-100.0, 80.0],
            "pv_premiums": [300.0, 150.0],
            "pv_death_benefits": [180.0, 200.0],
            "pv_bel_outflows": [220.0, 230.0],
            "pv_bel_inflows": [320.0, 150.0],
        }
    )


def _ra_result() -> pd.DataFrame:
    return pd.DataFrame({"policy_id": [1, 2], "ra_per_policy": [10.0, 5.0]})


def _projection() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "policy_id": [1, 1, 2, 2],
            "Year": [1, 2, 1, 2],
            "coverage_years": [2, 2, 2, 2],
            "in_force": [True, True, True, True],
            "survival_ratio": [1.0, 0.95, 1.0, 0.90],
            "lapse_rate": [0.05, 0.04, 0.03, 0.02],
            "qx": [0.001, 0.002, 0.003, 0.004],
            "sum_assured": [10000.0, 10000.0, 20000.0, 20000.0],
            "discount_factor": [0.95, 0.90, 0.95, 0.90],
            "PV_Gross_Premium_Inflow": [100.0, 95.0, 120.0, 110.0],
            "PV_Death_Benefits": [10.0, 12.0, 20.0, 22.0],
            "Net_Premium_Inflow": [105.0, 100.0, 130.0, 125.0],
            "Net_Cash_Flow": [80.0, 75.0, 90.0, 85.0],
        }
    )


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [35, 45],
            "sum_assured": [10000.0, 20000.0],
            "coverage_years": [2, 2],
        }
    )


def _csm_result() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "policy_id": [1, 2],
            "csm_opening": [90.0, 0.0],
            "csm_closing": [80.0, 0.0],
            "onerous_loss": [0.0, 85.0],
        }
    )


def test_apply_scenario_returns_updated_copy_without_mutating_base():
    config = _small_config()

    shocked = apply_scenario(config, {"mortality_shock_multiplier": 1.2})

    assert shocked.mortality_shock_multiplier == 1.2
    assert config.mortality_shock_multiplier == 1.0


def test_run_scenarios_returns_sorted_successful_results(monkeypatch):
    config = _small_config(scenario_max_workers=1)

    def fake_run_single_scenario(name, scenario_cfg, base_config, mortality_table):
        if name == "failed":
            return None
        return {
            "scenario": name,
            "n_policies": 2,
            "Total_BEL": float(len(scenario_cfg)),
            "Total_RA": 1.0,
            "Total_CSM_Opening": 2.0,
            "Total_CSM_Closing": 3.0,
            "Onerous_Count": 0,
            "Onerous_Loss": 0.0,
        }

    monkeypatch.setattr(scenarios_module, "run_single_scenario", fake_run_single_scenario)

    result = run_scenarios(
        config,
        {"zeta": {"discount_rate_shift": -0.01}, "alpha": {}, "failed": {}},
        pd.DataFrame(),
    )

    assert result["scenario"].tolist() == ["alpha", "zeta"]


def test_run_scenarios_returns_empty_schema_when_all_scenarios_fail(monkeypatch):
    config = _small_config(scenario_max_workers=1)
    monkeypatch.setattr(scenarios_module, "run_single_scenario", lambda *args: None)

    result = run_scenarios(config, {"failed": {}}, pd.DataFrame())

    assert result.empty
    assert result.columns.tolist() == [
        "scenario",
        "n_policies",
        "Total_BEL",
        "Total_RA",
        "Total_CSM_Opening",
        "Total_CSM_Closing",
        "Onerous_Count",
        "Onerous_Loss",
    ]


def test_run_single_scenario_small_config_returns_summary(mortality_table):
    config = _small_config()

    result = run_single_scenario("base", {}, config, mortality_table)

    assert result is not None
    assert result["scenario"] == "base"
    assert result["n_policies"] == 2
    assert {"Total_BEL", "Total_RA", "Total_CSM_Opening", "Total_CSM_Closing"}.issubset(result)


def test_run_single_scenario_returns_none_on_failure(monkeypatch, mortality_table):
    config = _small_config()

    def raise_error(config):
        raise ValueError("boom")

    monkeypatch.setattr(scenarios_module, "create_master_data", raise_error)

    assert run_single_scenario("bad", {}, config, mortality_table) is None


def test_initial_csm_raises_for_missing_required_columns():
    config = _small_config()

    with pytest.raises(ValueError, match="bel_per_policy"):
        calculate_initial_csm(pd.DataFrame({"policy_id": [1]}), _ra_result(), config)

    with pytest.raises(ValueError, match="ra_per_policy"):
        calculate_initial_csm(_bel_result(), pd.DataFrame({"policy_id": [1]}), config)


def test_initial_csm_backfills_reporting_columns_from_projection():
    config = _small_config()
    bel = pd.DataFrame({"policy_id": [1], "bel_per_policy": [-50.0]})
    ra = pd.DataFrame({"policy_id": [1], "ra_per_policy": [5.0]})
    projection = _projection()[_projection()["policy_id"] == 1]

    result = calculate_initial_csm(bel, ra, config, projection=projection)

    assert result.loc[0, "initial_csm"] == pytest.approx(45.0)
    assert result.loc[0, "pv_premiums"] == pytest.approx(195.0)
    assert result.loc[0, "pv_death_benefits"] == pytest.approx(22.0)


def test_assumption_changes_first_period_and_prior_assumption_paths():
    config = _small_config(discount_rate=0.04)
    projection = _projection()

    first_period = calculate_assumption_changes(projection, config)
    assert first_period["unlock_gain_loss"].eq(0.0).all()

    unlocked = calculate_assumption_changes(
        projection,
        config,
        {
            "expected_qx": 0.001,
            "expected_lapse": 0.02,
            "prior_discount_rate": 0.03,
        },
    )

    assert len(unlocked) == 2
    assert unlocked["unlock_gain_loss"].notna().all()


def test_finance_cost_uses_prior_year_rate_when_supplied():
    opening = pd.DataFrame({"policy_id": [1, 2], "csm_opening": [100.0, 50.0]})

    result = calculate_finance_cost(opening, _small_config(), prior_year_rate=0.03)

    assert result["finance_cost"].tolist() == pytest.approx([3.0, 1.5])


def test_csm_rollforward_raises_when_reporting_year_has_no_release():
    config = _small_config(reporting_year=99)

    with pytest.raises(ValueError, match="reporting_year"):
        calculate_csm_rollforward(_bel_result(), _ra_result(), _projection(), config)


def test_save_outputs_writes_csv_and_audit_json(tmp_path: Path):
    config = _small_config()
    projection = _projection()
    master = _master()
    csm = _csm_result()
    diagnostics = {"total_bel": np.float32(-20.0), "top_policies": [{"policy_id": np.int64(1)}]}

    save_outputs(
        projection=projection,
        bel_result=_bel_result(),
        ra_result=_ra_result(),
        csm_result=csm,
        scenario_results=pd.DataFrame({"scenario": ["base"], "Total_BEL": [-20.0]}),
        output_dir=str(tmp_path),
        master=master,
        excel_output=False,
        group_result=pd.DataFrame({"group_id": ["g1"], "csm_opening": [90.0]}),
        config=config,
        bel_diagnostics=diagnostics,
    )

    assert (tmp_path / "projection_results.csv").exists()
    assert (tmp_path / "audit_report.json").exists()
    assert (tmp_path / "bel_diagnostics.json").exists()
    assert (tmp_path / "run_registry.csv").exists()

    audit = json.loads((tmp_path / "audit_report.json").read_text(encoding="utf-8"))
    bel_diagnostics = json.loads((tmp_path / "bel_diagnostics.json").read_text(encoding="utf-8"))

    assert audit["row_counts"]["projection"]["rows"] == len(projection)
    assert audit["bel_diagnostics"]["total_bel"] == pytest.approx(-20.0)
    assert bel_diagnostics["top_policies"][0]["policy_id"] == 1


def test_save_outputs_without_disclosure_package_writes_no_disclosure_files(tmp_path: Path):
    save_outputs(
        projection=_projection(),
        bel_result=_bel_result(),
        ra_result=_ra_result(),
        csm_result=_csm_result(),
        scenario_results=pd.DataFrame({"scenario": ["base"], "Total_BEL": [-20.0]}),
        output_dir=str(tmp_path),
        master=_master(),
        excel_output=False,
        group_result=pd.DataFrame({"group_id": ["g1"], "csm_opening": [90.0]}),
        disclosure_package=None,
    )

    assert (tmp_path / "projection_results.csv").exists()
    assert list(tmp_path.glob("disclosure_*.csv")) == []


def test_save_outputs_empty_disclosure_package_writes_no_disclosure_files(tmp_path: Path):
    save_outputs(
        projection=_projection(),
        bel_result=_bel_result(),
        ra_result=_ra_result(),
        csm_result=_csm_result(),
        scenario_results=pd.DataFrame({"scenario": ["base"], "Total_BEL": [-20.0]}),
        output_dir=str(tmp_path),
        master=_master(),
        excel_output=False,
        group_result=pd.DataFrame({"group_id": ["g1"], "csm_opening": [90.0]}),
        disclosure_package={},
    )

    assert (tmp_path / "projection_results.csv").exists()
    assert list(tmp_path.glob("disclosure_*.csv")) == []


def test_save_outputs_with_disclosure_package_writes_csv(tmp_path: Path):
    disclosure = {"summary": pd.DataFrame({"metric": ["bel"], "value": [-20.0]})}

    save_outputs(
        projection=_projection(),
        bel_result=_bel_result(),
        ra_result=_ra_result(),
        csm_result=_csm_result(),
        scenario_results=pd.DataFrame({"scenario": ["base"], "Total_BEL": [-20.0]}),
        output_dir=str(tmp_path),
        master=_master(),
        excel_output=False,
        group_result=pd.DataFrame({"group_id": ["g1"], "csm_opening": [90.0]}),
        disclosure_package=disclosure,
    )

    assert (tmp_path / "disclosure_summary.csv").exists()


def test_save_outputs_with_disclosure_package_writes_excel_sheets(tmp_path: Path):
    excel_path = tmp_path / "outputs.xlsx"
    long_name = "very_long_disclosure_sheet_name_exceeding_excel_limit"
    disclosure = {long_name: pd.DataFrame({"metric": ["bel"], "value": [-20.0]})}

    save_outputs(
        projection=_projection(),
        bel_result=_bel_result(),
        ra_result=_ra_result(),
        csm_result=_csm_result(),
        scenario_results=pd.DataFrame({"scenario": ["base"], "Total_BEL": [-20.0]}),
        output_dir=str(tmp_path),
        master=_master(),
        excel_output=True,
        excel_path=str(excel_path),
        group_result=pd.DataFrame({"group_id": ["g1"], "csm_opening": [90.0]}),
        disclosure_package=disclosure,
    )

    with pd.ExcelFile(excel_path) as workbook:
        disclosure_sheets = [sheet for sheet in workbook.sheet_names if sheet.startswith("disc_")]

    assert disclosure_sheets
    assert all(len(sheet) <= 31 for sheet in disclosure_sheets)


def test_save_outputs_requires_projection_and_master(tmp_path: Path):
    config = _small_config()
    projection = _projection()
    master = pd.DataFrame({"policy_id": [1]})

    with pytest.raises(ValueError, match="projection is required"):
        save_outputs(
            projection=None,
            bel_result=None,
            ra_result=None,
            csm_result=None,
            scenario_results=None,
            output_dir=str(tmp_path),
            master=master,
            excel_output=False,
            config=config,
        )

    with pytest.raises(ValueError, match="master is required"):
        save_outputs(
            projection=projection,
            bel_result=None,
            ra_result=None,
            csm_result=None,
            scenario_results=None,
            output_dir=str(tmp_path),
            master=None,
            excel_output=False,
            config=config,
        )
