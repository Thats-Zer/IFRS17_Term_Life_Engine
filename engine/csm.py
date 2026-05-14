from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# INITIAL CSM CALCULATION
# ==================================================

# CSM Hesaplama:
def calculate_initial_csm(
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame,
    config: ModelConfig,
    projection: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    

    """
    IFRS17 Başlangıç Contractual Service Margin (CSM) hesapla.
    
    CSM Tanımı:
    CSM = PV(Premiums) - (BEL + RA)

    Not:
    - Bu engine'de BEL "liability-positive" kabul edilir (outflows - inflows).
    
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

    float_dtype = np.float64 if bool(getattr(config, "use_float64", False)) else np.float32
    
    # ==================================================
    # PREMIUM ANNUITY PV
    # ==================================================
    
    # Unutulmuş: projection'dan PV(Premiums) alınması gerekir
    # Öncelik: projection içinden poliçe bazında PV primleri topla.
    # Fallback: (eski davranış) PV premiums ≈ BEL × (1 + premium_margin)

    # projection'da PV primleri yoksa, bel_result üzerinden tahmini PV primleri hesapla
    if "pv_premiums" not in bel_result.columns:
        pv_premiums_df: Optional[pd.DataFrame] = None

        if projection is not None:
            proj = projection
            if "policy_id" not in proj.columns:
                logger.warning("projection'da policy_id yok; PV(Premiums) hesaplanamadı, fallback kullanıldı")
            else:
                pv_col: Optional[str]
                if "PV_Gross_Premium_Inflow" in proj.columns:
                    pv_col = "PV_Gross_Premium_Inflow"
                elif "Gross_Premium_Inflow" in proj.columns and "discount_factor" in proj.columns:
                    pv_col = "PV_Gross_Premium_Inflow"
                    proj = proj.copy()
                    proj[pv_col] = (
                        proj["Gross_Premium_Inflow"] * proj["discount_factor"]
                    ).astype(float_dtype)
                else:
                    pv_col = None

                if pv_col is not None and pv_col in proj.columns:
                    pv_premiums_df = (
                        proj.groupby("policy_id", sort=False, as_index=False)[pv_col]
                        .sum()
                        .rename(columns={pv_col: "pv_premiums"})
                    )

        if pv_premiums_df is not None:
            bel_result = bel_result.merge(pv_premiums_df, on="policy_id", how="left")
            bel_result["pv_premiums"] = bel_result["pv_premiums"].fillna(0.0).astype(float_dtype)
        else:
            bel_result["pv_premiums"] = (
                bel_result["bel_per_policy"]
                * (1 + config.premium_margin)
            ).astype(float_dtype)

        # ==================================================
        # PLAIN COVER (EXPECTED DEATH BENEFIT)
        # ==================================================
        # Düz teminat hesabı: Expected death benefit = S(t-1) * qx_t * sum_assured
        # PV = Expected death benefit * discount_factor
        # Not: Bu değer CSM formülünde doğrudan kullanılmıyor; şeffaflık için poliçe bazında hesaplanır.

        if projection is not None and "pv_death_benefits" not in bel_result.columns:
            proj = projection
            required = {"policy_id", "survival_ratio", "qx", "sum_assured"}
            if not required.issubset(set(proj.columns)):
                missing = sorted(required - set(proj.columns))
                logger.warning(f"PV teminat hesaplanamadı; projection eksik kolonlar: {missing}")
            else:
                if "PV_Death_Benefits" in proj.columns:
                    pv_death_col = "PV_Death_Benefits"
                elif "discount_factor" in proj.columns:
                    pv_death_col = "PV_Death_Benefits"
                    proj = proj.copy()
                    proj["Death_Benefits"] = (
                        proj["survival_ratio"] * proj["qx"] * proj["sum_assured"]
                    ).astype(float_dtype)
                    proj[pv_death_col] = (proj["Death_Benefits"] * proj["discount_factor"]).astype(float_dtype)
                else:
                    pv_death_col = None

                if pv_death_col is not None and pv_death_col in proj.columns:
                    pv_death_df = (
                        proj.groupby("policy_id", sort=False, as_index=False)[pv_death_col]
                        .sum()
                        .rename(columns={pv_death_col: "pv_death_benefits"})
                    )
                    bel_result = bel_result.merge(pv_death_df, on="policy_id", how="left")
                    bel_result["pv_death_benefits"] = bel_result["pv_death_benefits"].fillna(0.0).astype(float_dtype)
    
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
    
    csm_data["initial_csm_raw"] = (
        csm_data["pv_premiums"]
        - csm_data["total_liability"]
    ).astype(float_dtype)
    
    # ==================================================
    # ONEROUS CONTRACT DETECTION
    # ==================================================
    
    csm_data["is_onerous"] = csm_data["initial_csm_raw"] < 0

    # Onerous poliçelerde CSM = 0, loss ayrıca kaydedilir (pozitif tutar)
    csm_data["onerous_loss"] = np.maximum(-csm_data["initial_csm_raw"], 0).astype(float_dtype)
    csm_data["initial_csm"] = csm_data["initial_csm_raw"].clip(lower=0).astype(float_dtype)
    
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
    
    # pv_premiums/onerous_loss output'ta tutulur (rollforward + grouping için)
    cols = ["policy_id", "pv_premiums", "initial_csm", "is_onerous", "onerous_loss"]
    if "pv_death_benefits" in csm_data.columns:
        cols.append("pv_death_benefits")
    return csm_data[cols]


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
    # COVERAGE-UNITS BASED RELEASE (avoid double counting)
    # ==================================================
    # Coverage units proxy (term-life): in-force at period start.
    # Expected in-force weight = survival_ratio * (1 - lapse_rate)
    # Release each period proportionally: opening_csm * units_t / sum(units)

    if "coverage_years" not in projection.columns:
        projection["coverage_years"] = int(getattr(config, "coverage_years", getattr(config, "projection_years", 1)) or 1)

    if "in_force" in projection.columns:
        in_force = projection["in_force"].astype(np.float32)
    else:
        in_force = (projection["Year"] <= projection["coverage_years"]).astype(np.float32)

    projection["coverage_units"] = (
        in_force
        * projection.get("survival_ratio", 1.0)
        * (1 - projection.get("lapse_rate", 0.0))
    ).astype(np.float32)

    total_units = projection.groupby("policy_id", sort=False)["coverage_units"].transform("sum").replace(0, np.nan)
    projection["csm_release"] = (
        projection["opening_csm"]
        * (projection["coverage_units"] / total_units)
    ).fillna(0.0).astype(np.float32)
    
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
    
    csm_opening = calculate_initial_csm(bel_result, ra_result, config, projection=projection)
    
    # ==================================================
    # STEP 2: OPENING LIABILITY
    # ==================================================
    
    # Opening balances: explicitly map known column names
    opening_liability = (
        bel_result[["policy_id", "bel_per_policy"]]
        .merge(ra_result[["policy_id", "ra_per_policy"]], on="policy_id", how="left")
        .merge(csm_opening[["policy_id", "initial_csm", "is_onerous", "onerous_loss", "pv_premiums"]], on="policy_id", how="left")
        .rename(
            columns={
                "bel_per_policy": "bel_opening",
                "ra_per_policy": "ra_opening",
                "initial_csm": "csm_opening",
            }
        )
    )

    opening_liability[["ra_opening", "csm_opening", "onerous_loss", "pv_premiums"]] = opening_liability[[
        "ra_opening",
        "csm_opening",
        "onerous_loss",
        "pv_premiums",
    ]].fillna(0.0)
    opening_liability["is_onerous"] = opening_liability["is_onerous"].fillna(False).astype(bool)
    
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
    
    # Loss component (onerous) = initial onerous loss (pozitif)
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