from __future__ import annotations

import json

import numpy as np

from engine.audit import build_audit_report, config_snapshot, snapshot_hash
from engine.bel import calculate_bel
from engine.cashflows import calculate_cashflows
from engine.csm import calculate_csm_release, calculate_initial_csm
from engine.curves import create_discount_curve
from engine.grouping import assign_ifrs17_groups
from engine.outputs import save_outputs
from engine.projection import create_master_data, create_projection_table


def _projected_cashflows(config, mortality_table):
    master = create_master_data(config)
    projection = create_projection_table(master, config, mortality_table)
    curve = create_discount_curve(config)
    projection = projection.merge(
        curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year"),
        on="Year",
        how="left",
        validate="m:1",
    )
    return master, calculate_cashflows(projection, config)


def test_survival_ratio_is_opening_survival(config_small, mortality_table):
    _, projection = _projected_cashflows(config_small, mortality_table)
    sample = projection[projection["policy_id"] == projection["policy_id"].iloc[0]].sort_values("Year")

    expected_opening = sample["survival_multiplier"].shift(1).fillna(1.0).cumprod()

    assert np.allclose(sample["survival_ratio"], expected_opening, atol=1e-7)
    assert sample["survival_ratio"].iloc[0] == 1.0
    assert sample["survival_ratio"].is_monotonic_decreasing


def test_premium_and_claim_discount_timing(config_small, mortality_table):
    _, projection = _projected_cashflows(config_small, mortality_table)

    expected_premium_pv = projection["Gross_Premium_Inflow"] * projection["discount_factor_opening"]
    expected_claim_pv = projection["Death_Benefits"] * projection["discount_factor"]

    assert np.allclose(projection["PV_Gross_Premium_Inflow"], expected_premium_pv, atol=1e-5)
    assert np.allclose(projection["PV_Death_Benefits"], expected_claim_pv, atol=1e-5)


def test_bel_reconciles_to_adjusted_liability_cashflows(config_small, mortality_table):
    _, projection = _projected_cashflows(config_small, mortality_table)
    bel = calculate_bel(projection, config_small)

    re_rate = float(getattr(config_small, "reinsurance_cost_rate", 0.0) or 0.0)
    pd_default = float(getattr(config_small, "counterparty_pd", 0.0) or 0.0)
    lgd = float(getattr(config_small, "counterparty_lgd", 0.0) or 0.0)
    in_force = (projection["Year"] <= projection["coverage_years"]).astype(float)

    adjusted_claims = in_force * projection["survival_ratio"] * projection["adjusted_qx"] * projection["sum_assured"]
    adjusted_surrender = projection["Surrender_Benefit"].copy()
    re_ceding = projection["Gross_Premium_Inflow"] * re_rate
    re_recovery = adjusted_claims * re_rate
    default_cost = re_recovery * pd_default * lgd

    expected_row_bel = (
        (
            adjusted_claims
            + adjusted_surrender
            + projection["Operating_Expenses"]
            + default_cost
        )
        * projection["discount_factor"]
        + re_ceding * projection["discount_factor_opening"]
        - projection["Gross_Premium_Inflow"] * projection["discount_factor_opening"]
        - re_recovery * projection["discount_factor"]
    )

    expected = expected_row_bel.groupby(projection["policy_id"]).sum()
    actual = bel.set_index("policy_id")["bel_per_policy"]

    assert np.allclose(actual.sort_index(), expected.sort_index(), atol=1e-3)


def test_csm_release_allocates_full_opening_csm_over_coverage(config_small, mortality_table):
    _, projection = _projected_cashflows(config_small, mortality_table)
    opening = projection[["policy_id"]].drop_duplicates().assign(initial_csm=100.0)

    release = calculate_csm_release(projection, opening, config_small)
    total_release = release.groupby("policy_id")["csm_release"].sum()

    assert np.allclose(total_release, 100.0, atol=1e-5)
    assert (release["csm_release"] >= 0).all()


def test_mortality_shock_increases_projected_qx(config_small, mortality_table):
    shocked = config_small.model_copy(update={"mortality_shock_multiplier": 1.10})

    _, base = _projected_cashflows(config_small, mortality_table)
    _, stress = _projected_cashflows(shocked, mortality_table)

    merged = base[["policy_id", "Year", "qx"]].merge(
        stress[["policy_id", "Year", "qx"]],
        on=["policy_id", "Year"],
        suffixes=("_base", "_stress"),
    )

    assert (merged["qx_stress"] >= merged["qx_base"]).all()
    assert (merged["qx_stress"] > merged["qx_base"]).any()


def test_audit_snapshot_is_deterministic_and_saved(tmp_path, config_small, mortality_table):
    master, projection = _projected_cashflows(config_small, mortality_table)
    bel = calculate_bel(projection, config_small)
    ra = bel[["policy_id"]].assign(ra_per_policy=0.0)
    csm = calculate_initial_csm(bel, ra, config_small, projection=projection)

    snapshot = config_snapshot(config_small)
    assert snapshot_hash(snapshot) == snapshot_hash(config_snapshot(config_small))

    report = build_audit_report(
        config=config_small,
        projection=projection,
        master=master,
        bel_result=bel,
        ra_result=ra,
        csm_result=csm,
        scenario_results=None,
        group_result=None,
    )
    assert report["assumption_hash"] == snapshot_hash(snapshot)
    assert report["row_counts"]["projection"]["rows"] == len(projection)

    save_outputs(
        projection=projection.head(5),
        bel_result=bel.head(5),
        ra_result=ra.head(5),
        csm_result=csm.head(5),
        scenario_results=None,
        output_dir=str(tmp_path),
        master=master.head(5),
        excel_output=False,
        config=config_small,
    )

    saved_snapshot = json.loads((tmp_path / "assumption_snapshot.json").read_text(encoding="utf-8"))
    saved_report = json.loads((tmp_path / "audit_report.json").read_text(encoding="utf-8"))

    assert saved_snapshot == snapshot
    assert saved_report["assumption_hash"] == snapshot_hash(snapshot)
    assert saved_report["run_id"]
    assert saved_report["methodology_version"] == snapshot["methodology_version"]
    assert (tmp_path / "run_registry.csv").exists()


def test_grouping_includes_cohort_portfolio_and_profitability(config_small, mortality_table):
    master, projection = _projected_cashflows(config_small, mortality_table)
    bel = calculate_bel(projection, config_small)
    ra = bel[["policy_id"]].assign(ra_per_policy=0.0)
    csm = calculate_initial_csm(bel, ra, config_small, projection=projection).rename(
        columns={"initial_csm": "csm_opening"}
    )
    csm["csm_closing"] = csm["csm_opening"]
    csm["csm_closing_raw"] = csm["csm_closing"]

    groups = assign_ifrs17_groups(csm, projection, config_small)

    required = {
        "portfolio_group",
        "annual_cohort",
        "profitability_bucket",
        "risk_group",
        "group_id",
        "n_policies",
    }
    assert required.issubset(groups.columns)
    assert int(groups["n_policies"].sum()) == len(master)
    assert set(groups["annual_cohort"]) == {str(config_small.issue_year)}
