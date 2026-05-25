from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# INITIAL CSM CALCULATION
# ==================================================


def calculate_initial_csm(
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame,
    config: ModelConfig,
    projection: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    IFRS 17 Initial Contractual Service Margin (CSM) hesapla.

    CSM Sign Convention:
    - BEL is "liability-positive" and net of premium inflows (from calculate_bel):
        BEL = PV(Outflows) - PV(Inflows)

    - Therefore, CSM formula does NOT subtract premiums again:
        Initial CSM = max(-(BEL + RA), 0)
        Onerous Loss = max(BEL + RA, 0)

    - If (BEL + RA) > 0: CSM = 0 and Onerous Loss > 0 (bad contract)
    - If (BEL + RA) < 0: CSM > 0 and Onerous Loss = 0 (profitable contract)
    - If (BEL + RA) = 0: CSM = 0 and Onerous Loss = 0 (break-even)

    Input columns from BEL result (new refactored calculate_bel):
    - policy_id
    - bel_per_policy (required)
    - pv_premiums (optional, for reporting)
    - pv_claims / pv_death_benefits (optional, for reporting)

    Input columns from RA result:
    - policy_id
    - ra_per_policy

    Output columns:
    - policy_id
    - initial_csm
    - is_onerous
    - onerous_loss
    - pv_premiums (if present in input)
    - pv_death_benefits (if present in input)

    Args:
        bel_result: BEL per policy from calculate_bel()
        ra_result: RA per policy from calculate_risk_adjustment()
        config: ModelConfig
        projection: Optional projection (for backward compatibility, not used with new BEL)

    Returns:
        pd.DataFrame: policy_id, initial_csm, is_onerous, onerous_loss, pv_premiums, pv_death_benefits
    """

    float_dtype = np.float64 if bool(getattr(config, "use_float64", False)) else np.float32
    bel_result = bel_result.copy()

    if "bel_per_policy" not in bel_result.columns:
        raise ValueError("BEL result must contain 'bel_per_policy' column")

    # ==================================================
    # PRESERVE REPORTING COLUMNS FROM BEL
    # ==================================================

    # New refactored calculate_bel() now provides these:
    #   - pv_premiums: Total present value of premiums (already in bel_per_policy via inflows)
    #   - pv_claims / pv_death_benefits: Total PV of claims (for transparency)
    #   - pv_bel_outflows, pv_bel_inflows: Full BEL breakdown

    reporting_cols = ["pv_premiums", "pv_death_benefits", "pv_bel_outflows", "pv_bel_inflows"]
    for col in reporting_cols:
        if col not in bel_result.columns:
            # If running with old-style BEL, try to extract from projection if provided
            if projection is not None and col == "pv_premiums":
                if "PV_Gross_Premium_Inflow" in projection.columns:
                    pv_premiums_agg = (
                        projection.groupby("policy_id", sort=False, as_index=False)[
                            "PV_Gross_Premium_Inflow"
                        ]
                        .sum()
                        .rename(columns={"PV_Gross_Premium_Inflow": "pv_premiums"})
                    )
                    bel_result = bel_result.merge(pv_premiums_agg, on="policy_id", how="left")
            elif projection is not None and col == "pv_death_benefits":
                if "PV_Death_Benefits" in projection.columns:
                    pv_claims_agg = (
                        projection.groupby("policy_id", sort=False, as_index=False)[
                            "PV_Death_Benefits"
                        ]
                        .sum()
                        .rename(columns={"PV_Death_Benefits": "pv_death_benefits"})
                    )
                    bel_result = bel_result.merge(pv_claims_agg, on="policy_id", how="left")

    # ==================================================
    # MERGE BEL AND RA
    # ==================================================

    if "ra_per_policy" not in ra_result.columns:
        raise ValueError("RA result must contain 'ra_per_policy' column")

    csm_data = bel_result.merge(
        ra_result[["policy_id", "ra_per_policy"]], on="policy_id", how="left"
    )
    csm_data["ra_per_policy"] = csm_data["ra_per_policy"].fillna(0).astype(float_dtype)

    # ==================================================
    # CSM CALCULATION (LIABILITY-POSITIVE BEL CONVENTION)
    # ==================================================

    # Total liability = BEL (already net of premiums) + RA
    csm_data["total_liability"] = (
        csm_data["bel_per_policy"].astype(float_dtype)
        + csm_data["ra_per_policy"].astype(float_dtype)
    ).astype(float_dtype)

    # BEL is liability-positive and ALREADY net of premium inflows.
    # Therefore: If total_liability < 0 => surplus exists => CSM > 0
    #            If total_liability > 0 => deficit exists => CSM = 0, Onerous Loss > 0

    csm_data["initial_csm_raw"] = (-csm_data["total_liability"]).astype(float_dtype)

    # ==================================================
    # ONEROUS CONTRACT CLASSIFICATION
    # ==================================================

    # Onerous: when fulfilment cashflows (BEL) + risk adjustment > 0
    csm_data["is_onerous"] = (csm_data["total_liability"] > 0).astype(bool)

    # Onerous loss is the positive part of the total liability (loss amount)
    # For profitable contracts, this is zero
    csm_data["onerous_loss"] = (np.maximum(csm_data["total_liability"], 0)).astype(float_dtype)

    # CSM is never negative under IFRS 17; clip at zero
    csm_data["initial_csm"] = (csm_data["initial_csm_raw"].clip(lower=0)).astype(float_dtype)

    # ==================================================
    # DIAGNOSTICS & LOGGING
    # ==================================================

    onerous_count = int(csm_data["is_onerous"].sum())
    profitable_count = int((~csm_data["is_onerous"]).sum())
    onerous_loss_total = float(csm_data["onerous_loss"].sum())
    csm_total = float(csm_data["initial_csm"].sum())

    if onerous_count > 0:
        logger.warning(
            "⚠ %d onerous poliçe(s) detected; Total onerous loss: %s",
            onerous_count,
            f"{onerous_loss_total:,.2f}",
        )

    logger.info(
        "✓ Initial CSM hesaplandı: Profitable=%d, Onerous=%d, Total CSM=%s, Total Onerous Loss=%s",
        profitable_count,
        onerous_count,
        f"{csm_total:,.2f}",
        f"{onerous_loss_total:,.2f}",
    )

    # ==================================================
    # OUTPUT COLUMNS
    # ==================================================

    # Preserve all relevant reporting columns for downstream use
    output_cols = ["policy_id", "initial_csm", "is_onerous", "onerous_loss"]
    optional_cols = ["pv_premiums", "pv_death_benefits", "pv_bel_outflows", "pv_bel_inflows"]

    for col in optional_cols:
        if col in csm_data.columns:
            output_cols.append(col)

    return csm_data[output_cols]


# ==================================================
# ASSUMPTION CHANGES & UNLOCKING
# ==================================================


def calculate_assumption_changes(
    projection: pd.DataFrame, config: ModelConfig, prior_assumptions: Optional[dict] = None
) -> pd.DataFrame:
    """
    Assumption değişikliklerini (unlocking) hesapla.

    IFRS17 Unlocking:
    - Her reporting period'da assumptions update edilir
    - BEL, RA recalculate edilir
    - Değişim CSM'e taşınır (gain/loss)

    Assumption Değişiklikleri:
    1. Mortalite: Actual experience vs beklenen
    2. Lapse: Actual surrender vs beklenen
    3. Expense: Actual cost vs beklenen
    4. Discount Rate: Market yield curve değişimi

    Unlock Logic:
    - ΔBELnew = BELnew - BELold
    - ΔRAnew = RAnew - RAold
    - Unlock adjustment = -(ΔBELnew + ΔRAnew)

    Args:
        projection: Projection tablosu
        config: ModelConfig
        prior_assumptions: Önceki dönem assumptions

    Returns:
        pd.DataFrame: policy_id, unlock_gain_loss
    """

    if prior_assumptions is None:
        # First period: no prior assumptions.
        logger.info("✓ İlk dönem, no unlocking")
        return projection[["policy_id"]].drop_duplicates().assign(unlock_gain_loss=0.0)

    # ==================================================
    # MORTALITY EXPERIENCE ANALYSIS
    # ==================================================

    projection["mortality_experience"] = projection["qx"] - prior_assumptions.get(
        "expected_qx", projection["qx"]
    )

    # Experience gain/loss
    projection["mortality_experience_gain"] = (
        -projection["mortality_experience"]
        * projection["sum_assured"]
        * projection["survival_ratio"]
        * projection["discount_factor"]
    )

    # ==================================================
    # LAPSE EXPERIENCE ANALYSIS
    # ==================================================

    projection["lapse_experience"] = projection["lapse_rate"] - prior_assumptions.get(
        "expected_lapse", projection["lapse_rate"]
    )

    projection["lapse_experience_gain"] = (
        projection["lapse_experience"]
        * projection["Net_Premium_Inflow"]
        * projection["discount_factor"]
    )

    # ==================================================
    # DISCOUNT RATE CHANGE (INTEREST RATE EFFECT)
    # ==================================================

    rate_change_effect = None
    if "prior_discount_rate" in prior_assumptions:
        prior_rate = float(prior_assumptions["prior_discount_rate"])
        current_rate = float(config.discount_rate)

        # PV recalculation with new vs prior rate (simple flat-rate curve assumption)
        # ΔPV_t = CF_t * (v_new^t - v_old^t)
        if "Net_Cash_Flow" in projection.columns and "Year" in projection.columns:
            v_new = 1.0 / (1.0 + current_rate)
            v_old = 1.0 / (1.0 + prior_rate)
            t = projection["Year"].astype(np.int32)
            rate_change_effect = projection["Net_Cash_Flow"] * ((v_new**t) - (v_old**t))

    # ==================================================
    # TOTAL UNLOCK ADJUSTMENT
    # ==================================================

    unlock_adjustments = projection.groupby("policy_id", sort=False, as_index=False).agg(
        {"mortality_experience_gain": "sum", "lapse_experience_gain": "sum"}
    )

    if rate_change_effect is not None:
        rate_change_effect_agg = (
            projection.assign(rate_change_effect=rate_change_effect)
            .groupby("policy_id", sort=False, as_index=False)["rate_change_effect"]
            .sum()
        )
        unlock_adjustments = unlock_adjustments.merge(
            rate_change_effect_agg, on="policy_id", how="left"
        )
    else:
        unlock_adjustments["rate_change_effect"] = 0.0

    unlock_adjustments["unlock_gain_loss"] = (
        unlock_adjustments["mortality_experience_gain"]
        + unlock_adjustments["lapse_experience_gain"]
        + unlock_adjustments["rate_change_effect"]
    ).astype(np.float32)

    logger.info(
        f"✓ Assumption changes calculated: "
        f"Total unlock={unlock_adjustments['unlock_gain_loss'].sum():,.2f}"
    )

    return unlock_adjustments[["policy_id", "unlock_gain_loss"]]


# ==================================================
# FINANCE COST CALCULATION
# ==================================================


def calculate_finance_cost(
    opening_liability: pd.DataFrame, config: ModelConfig, prior_year_rate: Optional[float] = None
) -> pd.DataFrame:
    """
    CSM accretion interest hesapla.

    Bu fonksiyon toplam insurance finance expense değil, yalnızca CSM üzerine
    locked-in/current flat rate ile faiz işletme adımını üretir.

    Formula:
    CSM_Finance_Cost = CSM_Opening × accretion_rate

    Args:
        opening_liability: Opening balance (BEL, RA, CSM)
        config: ModelConfig
        prior_year_rate: Önceki yıl iskonto oranı

    Returns:
        pd.DataFrame: policy_id, finance_cost
    """

    opening_liability = opening_liability.copy()

    accretion_rate = float(prior_year_rate if prior_year_rate is not None else config.discount_rate)

    # ==================================================
    # FINANCE COST = CSM * ACCRETION RATE
    # ==================================================

    opening_liability["finance_cost"] = (
        opening_liability.get("csm_opening", 0.0) * accretion_rate
    ).astype(np.float32)

    logger.info(
        f"✓ Finance cost calculated: "
        f"Accretion rate={accretion_rate*100:+.2f}%, "
        f"Total FC={opening_liability['finance_cost'].sum():,.2f}"
    )

    return opening_liability[["policy_id", "finance_cost"]]


# ==================================================
# CSM RELEASE CALCULATION
# ==================================================


def calculate_csm_release(
    projection: pd.DataFrame, opening_csm: pd.DataFrame, config: ModelConfig
) -> pd.DataFrame:
    """
    Yıllık CSM Release (teminat hizmeti kaydedilmesi) hesapla.

    CSM Release Formula:
    CSM_Release_t = Opening_CSM × (Services_Provided_t / Total_Services)

    Services Definition:
    - Term Life'da: teminat süresi
    - Services_Provided = 1 yıl
    - Total_Services = coverage_years

    CSM_Release = Opening_CSM / Remaining_Coverage_Period

    Edge Cases:
    1. Lapse: Poliçe iptali halinde, kalan CSM yazılır (full release)
    2. Early Surrender: Reserve dönmesi öncesinde CSM sıfırlanır
    3. Maturity: Son yıl, kalan CSM tamamen release edilir

    Args:
        projection: Projection tablosu
        opening_csm: Opening CSM per policy
        config: ModelConfig

    Returns:
        pd.DataFrame: year, policy_id, csm_release
    """

    # ==================================================
    # MERGE OPENING CSM
    # ==================================================

    projection = projection.merge(
        opening_csm[["policy_id", "initial_csm"]].rename(columns={"initial_csm": "opening_csm"}),
        on="policy_id",
        how="left",
    )

    # ==================================================
    # COVERAGE-UNITS BASED RELEASE (avoid double counting)
    # ==================================================
    # Coverage units proxy (term-life): in-force at period start.
    # Expected in-force weight = survival_ratio * (1 - lapse_rate)
    # Release each period proportionally: opening_csm * units_t / sum(units)

    if "coverage_years" not in projection.columns:
        projection["coverage_years"] = int(
            getattr(config, "coverage_years", getattr(config, "projection_years", 1)) or 1
        )

    if "in_force" in projection.columns:
        in_force = projection["in_force"].astype(np.float32)
    else:
        in_force = (projection["Year"] <= projection["coverage_years"]).astype(np.float32)

    projection["coverage_units"] = (
        in_force * projection.get("survival_ratio", 1.0) * (1 - projection.get("lapse_rate", 0.0))
    ).astype(np.float32)

    total_units = (
        projection.groupby("policy_id", sort=False)["coverage_units"]
        .transform("sum")
        .replace(0, np.nan)
    )
    projection["csm_release"] = (
        (projection["opening_csm"] * (projection["coverage_units"] / total_units))
        .fillna(0.0)
        .astype(np.float32)
    )

    logger.debug("✓ CSM release hesaplandı")

    return projection[["policy_id", "Year", "csm_release"]]


# ==================================================
# CSM ROLLFORWARD
# ==================================================


def calculate_csm_rollforward(
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame,
    projection: pd.DataFrame,
    config: ModelConfig,
    prior_assumptions: Optional[dict] = None,
) -> pd.DataFrame:
    """
    CSM Rollforward (açılış -> kapanış) hesapla - TAM FORMÜL.

    Rollforward Denklemi (IFRS17):
    CSM_Closing = CSM_Opening
                + Finance_Cost
                - CSM_Release
                - Unlocking_Adjustment
                + Changes_in_Estimates

    Bileşenler:
    1. CSM_Opening: Dönem başındaki CSM
    2. Finance_Cost: Faiz maliyeti (rate × liability)
    3. CSM_Release: Teminat hizmeti geliri
    4. Unlocking: Assumption değişikliğinden gain/loss
    5. Changes in Estimates: Mortalite, lapse, expense experience

    Args:
        bel_result: BEL calculations
        ra_result: RA calculations
        projection: Projection tablosu
        config: ModelConfig
        prior_assumptions: Önceki dönem assumptions

    Returns:
        pd.DataFrame: Full CSM rollforward
    """

    # ==================================================
    # STEP 1: INITIAL CSM
    # ==================================================

    csm_opening = calculate_initial_csm(bel_result, ra_result, config, projection=projection)

    # ==================================================
    # STEP 2: OPENING LIABILITY
    # ==================================================

    # Opening balances: explicitly map known column names
    opening_liability = (
        bel_result[["policy_id", "bel_per_policy"]]
        .merge(ra_result[["policy_id", "ra_per_policy"]], on="policy_id", how="left")
        .merge(
            csm_opening[["policy_id", "initial_csm", "is_onerous", "onerous_loss", "pv_premiums"]],
            on="policy_id",
            how="left",
        )
        .rename(
            columns={
                "bel_per_policy": "bel_opening",
                "ra_per_policy": "ra_opening",
                "initial_csm": "csm_opening",
            }
        )
    )

    opening_liability[["ra_opening", "csm_opening", "onerous_loss", "pv_premiums"]] = (
        opening_liability[
            [
                "ra_opening",
                "csm_opening",
                "onerous_loss",
                "pv_premiums",
            ]
        ].fillna(0.0)
    )
    opening_liability["is_onerous"] = opening_liability["is_onerous"].fillna(False).astype(bool)

    # ==================================================
    # STEP 3: FINANCE COST
    # ==================================================

    finance_cost_df = calculate_finance_cost(
        opening_liability,
        config,
        prior_year_rate=prior_assumptions.get("discount_rate") if prior_assumptions else None,
    )

    # ==================================================
    # STEP 4: CSM RELEASE
    # ==================================================

    csm_release_df = calculate_csm_release(projection, csm_opening, config)

    # Single reporting-period rollforward: use the current reporting year release,
    # not the full projected lifetime release.
    reporting_year = int(
        getattr(config, "reporting_year", csm_release_df["Year"].min())
        or csm_release_df["Year"].min()
    )
    csm_release_current = csm_release_df[csm_release_df["Year"] == reporting_year]
    if csm_release_current.empty:
        raise ValueError(f"CSM release icin reporting_year bulunamadi: {reporting_year}")

    csm_release_agg = (
        csm_release_current.groupby("policy_id", sort=False)["csm_release"].sum().reset_index()
    )

    # ==================================================
    # STEP 5: UNLOCKING ADJUSTMENT
    # ==================================================

    unlock_df = calculate_assumption_changes(projection, config, prior_assumptions)

    # ==================================================
    # STEP 6: MERGE AND ROLLFORWARD
    # ==================================================

    rollforward = (
        opening_liability.merge(finance_cost_df, on="policy_id", how="left")
        .merge(csm_release_agg, on="policy_id", how="left")
        .merge(unlock_df, on="policy_id", how="left")
    )

    rollforward = rollforward.fillna(0)

    float_dtype = np.float64 if bool(getattr(config, "use_float64", False)) else np.float32

    # ==================================================
    # CSM CLOSING
    # ==================================================

    # Raw (unclipped) closing CSM is useful for detecting "subsequently onerous"
    # situations where the service margin would become negative before IFRS17 floor at 0.
    rollforward["csm_closing_raw"] = (
        rollforward["csm_opening"]
        + rollforward["finance_cost"]
        - rollforward["csm_release"]
        - rollforward["unlock_gain_loss"]
    ).astype(float_dtype)

    rollforward["csm_closing"] = rollforward["csm_closing_raw"].clip(lower=0).astype(float_dtype)

    # ==================================================
    # LOSS COMPONENT (ONEROUS CONTRACTS)
    # ==================================================

    # Loss component (onerous) equals the initial positive loss amount.
    rollforward["loss_component"] = np.where(
        rollforward["is_onerous"],
        rollforward.get("onerous_loss", 0.0),
        0.0,
    ).astype(np.float32)

    logger.info(
        f"✓ CSM Rollforward tamamlandı: "
        f"Opening={rollforward['csm_opening'].sum():,.2f}, "
        f"Closing={rollforward['csm_closing'].sum():,.2f}"
    )

    return rollforward
