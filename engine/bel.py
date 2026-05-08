from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# BEL CALCULATION (BEST ESTIMATE LIABILITY)
# ==================================================

def calculate_bel(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    IFRS17 Best Estimate Liability (BEL) hesapla.
    
    IFRS17 Tanımı:
    BEL = Σ PV(Expected Cashflows)
        = Σ PV(Inflows) - Σ PV(Outflows)
    
    Net Cashflow Tanımı:
    Net CF = Gross Premiums - Death Benefits - Surrender Benefits - Expenses
    
    Bileşenler:
    1. INFLOWS:
       - Gross premiums: Tahsil edilen brüt primler
    
    2. OUTFLOWS:
       - Death benefits: Ölüm halinde tazminat (mortalite riski)
       - Surrender benefits: Poliçe iptali halinde iade
       - Operating expenses: İşletme giderleri
       - Reinsurance cost: Reasürans bedeli
       - Counterparty default: Reasürans karşı taraf riski
    
    Mortalite Riski Entegrasyonu:
    - Death benefit = Sum Assured × qx × Survival Ratio
    - Lapse etkisi: (1 - lapse_rate) çarpanı
    - Policyholder behavior: stokastik mortalite ve lapse
    
    Edge Cases:
    1. Early Surrender (Yıl 1-2): Acquisition cost recovery
    2. Maturity (Son Yıl): Sıfır surrender value
    3. Full Lapse: Poliçe iptal, CF = 0
    4. Multiple Deaths: Ortalama expected claims
    
    Args:
        projection: Projection tablosu (cashflows eklenmiş)
        config: ModelConfig
        
    Returns:
        pd.DataFrame: policy_id ve bel_per_policy sütunları
        
    Raises:
        ValueError: Veriler geçersizse
    """
    
    if "PV_Net_Cash_Flow" not in projection.columns:
        raise ValueError("projection'da 'PV_Net_Cash_Flow' sütunu gerekli")
    
    # ==================================================
    # EARLY SURRENDER ADJUSTMENT
    # ==================================================
    # Yıl 1-2'de surrender value negatif olabilir (acquisition cost recovery)
    
    projection["adjusted_surrender_benefit"] = projection["Surrender_Benefit"].copy()
    
    # Yıl 1: Surrender benefit = 0 (minimum cash value)
    projection.loc[projection["Year"] == 1, "adjusted_surrender_benefit"] = 0
    
    # Yıl 2: Partial surrender value (50% of year 1 premium)
    projection.loc[
        projection["Year"] == 2,
        "adjusted_surrender_benefit"
    ] = (
        projection.loc[projection["Year"] == 2, "Net_Premium_Inflow"]
        * 0.5
    )
    
    # ==================================================
    # MATURITY ADJUSTMENT
    # ==================================================
    # Son yıl: poliçe olgunlaştı, surrender value = 0
    
    if "coverage_years" in projection.columns:
        last_year_mask = projection["Year"] >= projection["coverage_years"]
        projection.loc[last_year_mask, "adjusted_surrender_benefit"] = 0
    
    # ==================================================
    # LAPSE & MORTALITY CORRECTION
    # ==================================================
    # Policyholder behavior'ı düzelt
    
    # Lapse oranı yüksekse, mortality risk azalır (selection effect)
    # Formula: Adjusted_qx = qx × (1 - lapse_correlation)
    
    lapse_mortality_correlation = getattr(config, "lapse_mortality_correlation", 0.1)
    
    projection["adjusted_qx"] = (
        projection["qx"]
        * (1 - lapse_mortality_correlation * projection["lapse_rate"])
    ).clip(0, 1).astype(np.float32)
    
    # ==================================================
    # RECALCULATE DEATH BENEFITS (ADJUSTED)
    # ==================================================
    
    projection["Adjusted_Death_Benefits"] = (
        projection["survival_ratio"]
        * projection["adjusted_qx"]
        * projection["sum_assured"]
    ).astype(np.float32)
    
    # ==================================================
    # ADJUSTED NET CASH FLOW
    # ==================================================
    
    projection["Adjusted_Net_Cash_Flow"] = (
        projection["Gross_Premium_Inflow"]
        - projection["Adjusted_Death_Benefits"]
        - projection["adjusted_surrender_benefit"]
        - projection["Operating_Expenses"]
        - projection["Counterparty_Default_Cost"]
    ).astype(np.float32)
    
    projection["PV_Adjusted_Net_Cash_Flow"] = (
        projection["Adjusted_Net_Cash_Flow"]
        * projection["discount_factor"]
    ).astype(np.float32)
    
    # ==================================================
    # POLICY-LEVEL BEL AGGREGATION
    # ==================================================
    
    bel_result = (
        projection
        .groupby("policy_id", sort=False, as_index=False)
        .agg({
            "PV_Adjusted_Net_Cash_Flow": "sum",
            "sum_assured": "first",
            "coverage_years": "first",
            "issue_age": "first"
        })
        .rename(columns={"PV_Adjusted_Net_Cash_Flow": "bel_per_policy"})
    )
    
    # ==================================================
    # ONEROUS CONTRACT DETECTION
    # ==================================================
    
    # Onerous: BEL < 0 (liability miktarı negatif)
    bel_result["is_onerous"] = bel_result["bel_per_policy"] < 0
    
    # Onerous BEL'i 0'a ayarla (minimum liability)
    bel_result["bel_per_policy"] = bel_result["bel_per_policy"].clip(lower=0)
    
    # ==================================================
    # VALIDATION & LOGGING
    # ==================================================
    
    onerous_count = bel_result["is_onerous"].sum()
    if onerous_count > 0:
        logger.warning(f"⚠️ {onerous_count} poliçe onerous (BEL < 0)")
    
    total_bel = bel_result["bel_per_policy"].sum()
    avg_bel = bel_result["bel_per_policy"].mean()
    
    logger.info(
        f"✓ BEL Hesaplandı: Total={total_bel:,.2f}, "
        f"Avg={avg_bel:,.2f}, Onerous={onerous_count}"
    )
    
    return bel_result


# ==================================================
# BEL SENSITIVITY ANALYSIS
# ==================================================

def calculate_bel_sensitivity(
    projection: pd.DataFrame,
    config: ModelConfig,
    shock_scenarios: Optional[dict] = None
) -> pd.DataFrame:
    """
    BEL'in duyarlılık analizi (mortalite, lapse, discount rate şokları).
    
    Şok Senaryoları:
    1. Mortality +10%
    2. Lapse +20%
    3. Discount Rate -100 bps
    4. Combined shock
    
    Args:
        projection: Projection tablosu
        config: ModelConfig
        shock_scenarios: Custom şok senaryoları
        
    Returns:
        pd.DataFrame: Senaryo bazında BEL değerleri
    """
    
    if shock_scenarios is None:
        shock_scenarios = {
            "base": {"mort_shock": 0, "lapse_shock": 0, "rate_shock": 0},
            "mortality_up_10": {"mort_shock": 0.10, "lapse_shock": 0, "rate_shock": 0},
            "lapse_up_20": {"mort_shock": 0, "lapse_shock": 0.20, "rate_shock": 0},
            "rate_down_100bps": {"mort_shock": 0, "lapse_shock": 0, "rate_shock": -0.01},
        }
    
    sensitivity_results = []
    
    for scenario_name, shocks in shock_scenarios.items():
        proj_shock = projection.copy()
        
        # Apply shocks
        proj_shock["adjusted_qx"] = (
            proj_shock["qx"]
            * (1 + shocks["mort_shock"])
        ).clip(0, 1)
        
        proj_shock["shocked_lapse_rate"] = (
            proj_shock["lapse_rate"]
            + shocks["lapse_shock"]
        ).clip(0, 1)
        
        # Recalculate BEL
        bel_shock = calculate_bel(proj_shock, config)
        bel_shock["scenario"] = scenario_name
        
        sensitivity_results.append(bel_shock)
    
    sensitivity_df = pd.concat(sensitivity_results, ignore_index=True)
    
    logger.info(f"✓ Sensitivity analysis tamamlandı: {len(shock_scenarios)} senaryo")
    
    return sensitivity_df