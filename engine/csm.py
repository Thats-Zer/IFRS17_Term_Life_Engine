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
    config: ModelConfig
) -> pd.DataFrame:
    """
    IFRS17 Başlangıç Contractual Service Margin (CSM) hesapla.
    
    CSM Tanımı:
    CSM = PV(Premiums) - BEL - RA
    
    Onerous Kontrat Kontrolü:
    - Eğer (BEL + RA) > PV(Premiums) ise: CSM = 0, Onerous Loss kaydedilir
    - Aksi takdirde: Normal CSM
    
    CSM Negatif Olabilir mi?
    - Hayır, IFRS17'de CSM >= 0
    - Onerous kontrat durumunda: CSM=0, Loss kaydedilir ayrıca
    
    Args:
        bel_result: BEL per policy (policy_id, bel_per_policy)
        ra_result: RA per policy (policy_id, ra_per_policy)
        config: ModelConfig
        
    Returns:
        pd.DataFrame: policy_id, initial_csm, is_onerous
        
    Raises:
        ValueError: Veriler geçersizse
    """
    
    # ==================================================
    # PREMIUM ANNUITY PV
    # ==================================================
    # Unutulmuş: projection'dan PV(Premiums) alınması gerekir
    # Burada simplified: assume PV premiums = BEL × (1 + markup)
    
    if "pv_premiums" not in bel_result.columns:
        bel_result["pv_premiums"] = (
            bel_result["bel_per_policy"]
            * (1 + config.premium_margin)
        )
    
    # ==================================================
    # MERGE BEL VE RA
    # ==================================================
    
    csm_data = bel_result.merge(ra_result, on="policy_id", how="left")
    csm_data["ra_per_policy"] = csm_data["ra_per_policy"].fillna(0)
    
    # ==================================================
    # CSM CALCULATION
    # ==================================================
    
    csm_data["total_liability"] = (
        csm_data["bel_per_policy"]
        + csm_data["ra_per_policy"]
    )
    
    csm_data["initial_csm"] = (
        csm_data["pv_premiums"]
        - csm_data["total_liability"]
    ).astype(np.float32)
    
    # ==================================================
    # ONEROUS CONTRACT DETECTION
    # ==================================================
    
    csm_data["is_onerous"] = csm_data["initial_csm"] < 0
    
    # Onerous poliçelerde CSM = 0, loss ayrıca kaydedilir
    csm_data["onerous_loss"] = np.minimum(csm_data["initial_csm"], 0).astype(np.float32)
    csm_data["initial_csm"] = csm_data["initial_csm"].clip(lower=0).astype(np.float32)
    
    # ==================================================
    # LOGGING
    # ==================================================
    
    onerous_count = csm_data["is_onerous"].sum()
    onerous_loss_total = csm_data["onerous_loss"].sum()
    
    if onerous_count > 0:
        logger.warning(
            f"⚠️ {onerous_count} onerous poliçe, "
            f"Total onerous loss: {onerous_loss_total:,.2f}"
        )
    
    logger.info(
        f"✓ Initial CSM Hesaplandı: "
        f"Total={csm_data['initial_csm'].sum():,.2f}, "
        f"Avg={csm_data['initial_csm'].mean():,.2f}"
    )
    
    return csm_data[["policy_id", "initial_csm", "is_onerous"]]


# ==================================================
# ASSUMPTION CHANGES & UNLOCKING
# ==================================================

def calculate_assumption_changes(
    projection: pd.DataFrame,
    config: ModelConfig,
    prior_assumptions: Optional[dict] = None
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
        # İlk dönem: no prior assumptions
        logger.info("✓ İlk dönem, no unlocking")
        return projection[["policy_id"]].drop_duplicates().assign(unlock_gain_loss=0.0)
    
    # ==================================================
    # MORTALITY EXPERIENCE ANALYSIS
    # ==================================================
    
    projection["mortality_experience"] = (
        projection["qx"]
        - prior_assumptions.get("expected_qx", projection["qx"])
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
    
    projection["lapse_experience"] = (
        projection["lapse_rate"]
        - prior_assumptions.get("expected_lapse", projection["lapse_rate"])
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
            rate_change_effect = projection["Net_Cash_Flow"] * ((v_new ** t) - (v_old ** t))
    
    # ==================================================
    # TOTAL UNLOCK ADJUSTMENT
    # ==================================================
    
    unlock_adjustments = (
        projection
        .groupby("policy_id", sort=False, as_index=False)
        .agg({
            "mortality_experience_gain": "sum",
            "lapse_experience_gain": "sum"
        })
    )

    if rate_change_effect is not None:
        rate_change_effect_agg = (
            projection.assign(rate_change_effect=rate_change_effect)
            .groupby("policy_id", sort=False, as_index=False)["rate_change_effect"]
            .sum()
        )
        unlock_adjustments = unlock_adjustments.merge(rate_change_effect_agg, on="policy_id", how="left")
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
    opening_liability: pd.DataFrame,
    config: ModelConfig,
    prior_year_rate: Optional[float] = None
) -> pd.DataFrame:
    """
    Finance Cost (Faiz Maliyeti) hesapla.
    
    IFRS17 Finance Cost:
    Finance Cost = Opening_Liability × (Curve_Rate - Prior_Year_Rate)
    
    Opening Liability:
    = Opening BEL + Opening RA + Opening CSM
    
    Rate Change:
    - Yield curve'ün tenor-specific tarafından
    - Prior year'ın başında kullanılan rate
    - Current year'ın başında kullanılan rate
    
    Formula:
    FC = (BEL_opening + RA_opening + CSM_opening)
       × [Discount_Rate(Year) - Discount_Rate(Year-1)]
    
    Args:
        opening_liability: Opening balance (BEL, RA, CSM)
        config: ModelConfig
        prior_year_rate: Önceki yıl iskonto oranı
        
    Returns:
        pd.DataFrame: policy_id, finance_cost
    """
    
    opening_liability = opening_liability.copy()
    
    if "total_opening_liability" not in opening_liability.columns:
        opening_liability["total_opening_liability"] = (
            opening_liability.get("bel_opening", 0)
            + opening_liability.get("ra_opening", 0)
            + opening_liability.get("csm_opening", 0)
        )
    
    # ==================================================
    # DISCOUNT RATE CHANGE
    # ==================================================
    
    if prior_year_rate is None:
        prior_year_rate = config.discount_rate  # Sabit varsay
    
    rate_change = config.discount_rate - prior_year_rate
    
    # ==================================================
    # FINANCE COST = LIABILITY × RATE CHANGE
    # ==================================================
    
    opening_liability["finance_cost"] = (
        opening_liability["total_opening_liability"]
        * rate_change
    ).astype(np.float32)
    
    logger.info(
        f"✓ Finance cost calculated: "
        f"Rate change={rate_change*100:+.2f}%, "
        f"Total FC={opening_liability['finance_cost'].sum():,.2f}"
    )
    
    return opening_liability[["policy_id", "finance_cost"]]


# ==================================================
# CSM RELEASE CALCULATION
# ==================================================

def calculate_csm_release(
    projection: pd.DataFrame,
    opening_csm: pd.DataFrame,
    config: ModelConfig
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
        how="left"
    )
    
    # ==================================================
    # NORMAL CSM RELEASE (COVERAGE PERIOD BASIS)
    # ==================================================
    
    # Remaining coverage years
    projection["remaining_coverage_years"] = (
        projection["coverage_years"] - projection["Year"] + 1
    ).clip(lower=0).astype(np.int16)
    
    # Normal release
    projection["normal_csm_release"] = (
        projection["opening_csm"]
        / projection["coverage_years"]
    ).astype(np.float32)
    
    # ==================================================
    # LAPSE EFFECT ON CSM RELEASE
    # ==================================================
    
    # Poliçe iptal halinde: tüm kalan CSM release edilir
    projection["lapse_csm_release"] = (
        projection["lapse_rate"]
        * projection["opening_csm"]
        * (projection["remaining_coverage_years"] / projection["coverage_years"])
    ).astype(np.float32)
    
    # ==================================================
    # TOTAL CSM RELEASE
    # ==================================================
    
    projection["total_csm_release"] = (
        projection["normal_csm_release"]
        + projection["lapse_csm_release"]
    ).astype(np.float32)
    
    logger.debug("✓ CSM release hesaplandı")
    
    return projection[["policy_id", "Year", "total_csm_release"]].rename(
        columns={"total_csm_release": "csm_release"}
    )


# ==================================================
# CSM ROLLFORWARD
# ==================================================

def calculate_csm_rollforward(
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame,
    projection: pd.DataFrame,
    config: ModelConfig,
    prior_assumptions: Optional[dict] = None
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
    
    csm_opening = calculate_initial_csm(bel_result, ra_result, config)
    
    # ==================================================
    # STEP 2: OPENING LIABILITY
    # ==================================================
    
    opening_liability = bel_result.merge(ra_result, on="policy_id").merge(
        csm_opening[["policy_id", "initial_csm"]],
        on="policy_id"
    )
    
    # policy_id yoksa index'ten üret
    if "policy_id" not in opening_liability.columns:
        opening_liability = opening_liability.reset_index().rename(columns={"index": "policy_id"})

    # Olası alternatif kolon adlarını yakala
    column_aliases = {
        "bel_opening": ["bel_opening", "BEL_opening", "BEL", "bel", "initial_bel"],
        "ra_opening": ["ra_opening", "RA_opening", "RA", "ra", "initial_ra"],
        "csm_opening": ["csm_opening", "CSM_opening", "CSM", "csm", "initial_csm"],
        "is_onerous": ["is_onerous", "onerous", "onerous_flag"],
    }

    for target, aliases in column_aliases.items():
        if target in opening_liability.columns:
            continue
        found = next((c for c in aliases if c in opening_liability.columns), None)
        if found is not None:
            opening_liability = opening_liability.rename(columns={found: target})
        else:
            opening_liability[target] = 0.0 if target != "is_onerous" else False

    opening_liability = opening_liability.loc[
        :, ["policy_id", "bel_opening", "ra_opening", "csm_opening", "is_onerous"]
    ].copy()
    
    # ==================================================
    # STEP 3: FINANCE COST
    # ==================================================
    
    finance_cost_df = calculate_finance_cost(
        opening_liability,
        config,
        prior_year_rate=prior_assumptions.get("discount_rate") if prior_assumptions else None
    )
    
    # ==================================================
    # STEP 4: CSM RELEASE
    # ==================================================
    
    csm_release_df = calculate_csm_release(projection, csm_opening, config)
    
    # Poliçe bazında toplama
    csm_release_agg = csm_release_df.groupby("policy_id", sort=False)["csm_release"].sum().reset_index()
    
    # ==================================================
    # STEP 5: UNLOCKING ADJUSTMENT
    # ==================================================
    
    unlock_df = calculate_assumption_changes(projection, config, prior_assumptions)
    
    # ==================================================
    # STEP 6: MERGE VE ROLLFORWARD
    # ==================================================
    
    rollforward = (
        opening_liability
        .merge(finance_cost_df, on="policy_id", how="left")
        .merge(csm_release_agg, on="policy_id", how="left")
        .merge(unlock_df, on="policy_id", how="left")
    )
    
    rollforward = rollforward.fillna(0)
    
    # ==================================================
    # CSM CLOSING
    # ==================================================
    
    rollforward["csm_closing"] = (
        rollforward["csm_opening"]
        + rollforward["finance_cost"]
        - rollforward["csm_release"]
        - rollforward["unlock_gain_loss"]
    ).clip(lower=0).astype(np.float32)
    
    # ==================================================
    # LOSS COMPONENT (ONEROUS CONTRACTS)
    # ==================================================
    
    rollforward["loss_component"] = np.where(
        rollforward["is_onerous"],
        -rollforward["bel_opening"] - rollforward["ra_opening"],
        0
    ).astype(np.float32)
    
    logger.info(
        f"✓ CSM Rollforward tamamlandı: "
        f"Opening={rollforward['csm_opening'].sum():,.2f}, "
        f"Closing={rollforward['csm_closing'].sum():,.2f}"
    )
    
    return rollforward