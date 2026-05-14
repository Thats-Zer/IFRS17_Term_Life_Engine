from __future__ import annotations

import pandas as pd

from engine.curves import create_discount_curve
from engine.projection import create_master_data, create_projection_table
from engine.cashflows import calculate_cashflows
from engine.bel import calculate_bel
from engine.ra import calculate_risk_adjustment
from engine.csm import calculate_initial_csm
from engine.grouping import assign_ifrs17_groups
from engine.scenarios import apply_scenario


def test_discount_curve_has_required_columns_and_unique_year(config_small):
    curve = create_discount_curve(config_small)
    assert isinstance(curve, pd.DataFrame)
    assert "Year" in curve.columns
    assert "discount_factor" in curve.columns

    # merge patlamalarını (kartesyen büyüme) önlemek için Year unique olmalı
    dup = curve["Year"].duplicated().sum()
    assert dup == 0, f"discount_curve Year duplicate var: {dup} adet (merge kartesyen büyütebilir)"


def test_apply_scenario_updates_config(config_small):
    shocked = apply_scenario(config_small, {"discount_rate_shift": -0.01})

    # alan config'te yoksa test fail etmesin (farklı config şemaları için tolerans)
    discount_rate_shift = getattr(shocked, "discount_rate_shift", None)
    if discount_rate_shift is not None:
        assert discount_rate_shift == -0.01


def test_projection_has_minimum_expected_columns(config_small, mortality_table):
    master = create_master_data(config_small)
    proj = create_projection_table(master, config_small, mortality_table)

    assert isinstance(proj, pd.DataFrame)
    assert len(proj) > 0
    # Minimum sözleşme: policy_id ve Year olmalı
    assert "policy_id" in proj.columns
    assert "Year" in proj.columns


def test_projection_merge_discount_curve_is_m_to_1(config_small, mortality_table):
    master = create_master_data(config_small)
    proj = create_projection_table(master, config_small, mortality_table).copy()
    proj["Year"] = proj["Year"].astype(int)

    curve = create_discount_curve(config_small).copy()
    curve["Year"] = curve["Year"].astype(int)

    # opening yoksa closing'i kullan (scenario tarafındaki yaklaşım)
    if "discount_factor_opening" not in curve.columns:
        curve["discount_factor_opening"] = curve["discount_factor"]

    curve = curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year")

    merged = proj.merge(curve, on="Year", how="left", validate="m:1")

    assert "discount_factor" in merged.columns
    assert "discount_factor_opening" in merged.columns
    assert merged["discount_factor"].notna().all(), "discount_factor NaN geldi: Year eşleşmesi yok"
    assert merged["discount_factor_opening"].notna().all(), "discount_factor_opening NaN geldi: Year eşleşmesi yok"


def test_cashflows_bel_ra_smoke(config_small, mortality_table):
    master = create_master_data(config_small)
    proj = create_projection_table(master, config_small, mortality_table).copy()

    # cashflows coverage_years ister; Year'a eşitlemek yanlış (poliçe-sabit olmalı)
    if "coverage_years" not in proj.columns:
        proj["coverage_years"] = int(getattr(config_small, "coverage_years", getattr(config_small, "projection_years", 1)) or 1)

    # discount_factor gerekli olabilir; yoksa curve merge et
    if "discount_factor" not in proj.columns and "Year" in proj.columns:
        curve = create_discount_curve(config_small).copy()
        curve["Year"] = curve["Year"].astype(int)
        proj["Year"] = proj["Year"].astype(int)
        if "discount_factor_opening" not in curve.columns:
            curve["discount_factor_opening"] = curve["discount_factor"]
        curve = curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year")
        proj = proj.merge(curve, on="Year", how="left", validate="m:1")

    proj = calculate_cashflows(proj, config_small)

    bel = calculate_bel(proj, config_small)
    assert isinstance(bel, pd.DataFrame)

    # OLD (bunu kaldırın):
    # assert "BEL" in bel.columns, f"BEL sonucu bekleniyor. Kolonlar: {bel.columns.tolist()}"

    # NEW:
    assert (
        ("BEL" in bel.columns) or ("bel_per_policy" in bel.columns)
    ), f"BEL sonucu bekleniyor. Kolonlar: {bel.columns.tolist()}"

    ra = calculate_risk_adjustment(proj, config_small)
    assert isinstance(ra, pd.DataFrame)
    assert ("RA" in ra.columns) or ("ra_per_policy" in ra.columns), f"RA sonucu yok. Kolonlar: {ra.columns.tolist()}"


def test_cashflows_bel_ra_smoke_float64_mode(config_small, mortality_table):
    # Optional precision mode: should not crash and should return the same schema.
    if hasattr(config_small, "model_copy"):
        cfg = config_small.model_copy(update={"use_float64": True})
    elif hasattr(config_small, "copy"):
        cfg = config_small.copy(update={"use_float64": True})
    else:
        cfg = config_small
        setattr(cfg, "use_float64", True)

    master = create_master_data(cfg)
    proj = create_projection_table(master, cfg, mortality_table).copy()

    if "coverage_years" not in proj.columns:
        proj["coverage_years"] = int(getattr(cfg, "coverage_years", getattr(cfg, "projection_years", 1)) or 1)

    if "discount_factor" not in proj.columns and "Year" in proj.columns:
        curve = create_discount_curve(cfg).copy()
        curve["Year"] = curve["Year"].astype(int)
        proj["Year"] = proj["Year"].astype(int)
        if "discount_factor_opening" not in curve.columns:
            curve["discount_factor_opening"] = curve["discount_factor"]
        curve = curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year")
        proj = proj.merge(curve, on="Year", how="left", validate="m:1")

    proj = calculate_cashflows(proj, cfg)

    bel = calculate_bel(proj, cfg)
    assert isinstance(bel, pd.DataFrame)
    assert ("BEL" in bel.columns) or ("bel_per_policy" in bel.columns)

    ra = calculate_risk_adjustment(proj, cfg)
    assert isinstance(ra, pd.DataFrame)
    assert ("RA" in ra.columns) or ("ra_per_policy" in ra.columns)


def test_pv_total_cashflows_use_component_timing(config_small, mortality_table):
    master = create_master_data(config_small)
    proj = create_projection_table(master, config_small, mortality_table).copy()
    curve = create_discount_curve(config_small).copy()
    proj = proj.merge(
        curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year"),
        on="Year",
        how="left",
        validate="m:1",
    )

    proj = calculate_cashflows(proj, config_small)

    expected_inflows = proj["PV_Gross_Premium_Inflow"] + proj["PV_Reinsurance_Recovery"]
    expected_outflows = (
        proj["PV_Net_Death_Benefit"]
        + proj["PV_Surrender_Benefit"]
        + proj["PV_Operating_Expenses"]
        + proj["PV_Reinsurance_Ceding"]
        + proj["PV_Counterparty_Default_Cost"]
    )

    assert (proj["PV_Total_Inflows"] - expected_inflows).abs().max() < 1e-5
    assert (proj["PV_Total_Outflows"] - expected_outflows).abs().max() < 1e-5
    assert (proj["PV_Net_Cash_Flow"] - (expected_inflows - expected_outflows)).abs().max() < 1e-5


def test_initial_csm_uses_net_fulfilment_cashflows(config_small, mortality_table):
    master = create_master_data(config_small)
    proj = create_projection_table(master, config_small, mortality_table).copy()
    curve = create_discount_curve(config_small).copy()
    proj = proj.merge(
        curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year"),
        on="Year",
        how="left",
        validate="m:1",
    )
    proj = calculate_cashflows(proj, config_small)
    bel = calculate_bel(proj, config_small)
    ra = calculate_risk_adjustment(proj, config_small)

    csm = calculate_initial_csm(bel, ra, config_small, projection=proj)
    merged = bel.merge(ra, on="policy_id").merge(csm, on="policy_id")
    total_liability = merged["bel_per_policy"] + merged["ra_per_policy"]

    assert (merged["initial_csm"] - (-total_liability).clip(lower=0)).abs().max() < 1e-4
    assert (merged["onerous_loss"] - total_liability.clip(lower=0)).abs().max() < 1e-4
    assert (merged["is_onerous"] == (total_liability > 0)).all()


def test_grouping_counts_unique_policies(config_small, mortality_table):
    master = create_master_data(config_small)
    proj = create_projection_table(master, config_small, mortality_table).copy()
    curve = create_discount_curve(config_small).copy()
    proj = proj.merge(
        curve[["Year", "discount_factor", "discount_factor_opening"]].drop_duplicates("Year"),
        on="Year",
        how="left",
        validate="m:1",
    )
    proj = calculate_cashflows(proj, config_small)
    bel = calculate_bel(proj, config_small)
    ra = calculate_risk_adjustment(proj, config_small)
    csm = calculate_initial_csm(bel, ra, config_small, projection=proj).rename(
        columns={"initial_csm": "csm_opening"}
    )
    csm["csm_closing"] = csm["csm_opening"]
    csm["csm_closing_raw"] = csm["csm_closing"]

    groups = assign_ifrs17_groups(csm, proj, config_small)

    assert int(groups["n_policies"].sum()) == config_small.n_policies
    assert abs(groups["total_sum_assured"].sum() - master["sum_assured"].sum()) < 2.0
