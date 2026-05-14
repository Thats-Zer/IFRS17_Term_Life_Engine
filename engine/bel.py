from typing import Tuple, Optional #Bu modül, fonksiyon tiplerini belirtmek için kullanılır. 

import pandas as pd #Pandas, veri manipülasyonu ve analizi için kullanılan bir kütüphanedir. DataFrame yapısı sağlar.

import numpy as np #Numpy, sayısal hesaplamalar için kullanılan bir kütüphanedir. Diziler ve matrisler üzerinde işlem yapmayı sağlar.

import logging #Logging, uygulama içinde loglama yapmak için kullanılan bir modüldür. Hata ayıklama ve izleme için kullanılır.

from model.config_model import ModelConfig #ModelConfig, model yapılandırması için kullanılan bir sınıftır. Model parametrelerini içerir.

logger = logging.getLogger(__name__) #Logger, bu modül için bir logger nesnesi oluşturur. Loglama işlemleri bu nesne üzerinden yapılır.


# ==================================================
# BEL CALCULATION (BEST ESTIMATE LIABILITY)
# ==================================================

def calculate_bel(
    projection: pd.DataFrame,
    config: ModelConfig #bel hesaplama için gerekli yapılandırma parametrelerini içeren ModelConfig içeri alınır.
) -> pd.DataFrame:
    

    """
    IFRS17 Best Estimate Liability (BEL) hesapla.
    
    IFRS17 Tanımı (liability-pozitif konvansiyon):
    BEL = Σ PV(Expected Liability Cashflows)
        = Σ PV(Outflows) - Σ PV(Inflows)
    
        Net Cashflow Tanımı:
        Net CF = Inflows - Outflows

        Not:
        - Bu fonksiyon BEL'i "yükümlülük pozitif" olarak üretir.
            (Outflows - Inflows). Bu yüzden değer negatif çıkarsa net "asset" durumu oluşmuştur.
    
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
    
    Args:
        projection: Projection tablosu (cashflows eklenmiş)
        config: ModelConfig
        
    Returns:
        pd.DataFrame: policy_id ve bel_per_policy sütunları
        
    Raises:
        ValueError: Veriler geçersizse
    """
    
    required_cols = [
        "policy_id",
        "Year",
        "qx",
        "lapse_rate",
        "survival_ratio",
        "sum_assured",
        "Gross_Premium_Inflow",
        "Surrender_Benefit",
        "Operating_Expenses",
        "discount_factor",
        "discount_factor_opening",
    ]
    missing = [c for c in required_cols if c not in projection.columns]
    if missing:
        raise ValueError(f"BEL için eksik sütunlar: {missing}")

    # Avoid mutating caller-owned DataFrame (BEL adds many intermediate columns)
    projection = projection.copy()

    float_dtype = np.float64 if bool(getattr(config, "use_float64", False)) else np.float32
    
    # ==================================================
    # EARLY SURRENDER ADJUSTMENT
    # ==================================================
    
    # Yıl 1-2'de surrender value negatif olabilir (acquisition cost recovery)
    
    projection["adjusted_surrender_benefit"] = projection["Surrender_Benefit"].copy()
    # İlk 2 yıl için surrender benefit'i düzelt (acquisition cost recovery etkisi)
    
    # Yıl 1: Surrender benefit = 0 (minimum cash value)
    projection.loc[projection["Year"] == 1, "adjusted_surrender_benefit"] = 0
    
    # Yıl 2: Partial surrender value (basitleştirme)
    projection.loc[
        projection["Year"] == 2,
        "adjusted_surrender_benefit"
    ] = (
        (
            projection.loc[projection["Year"] == 2, "net_annual_premium"]
            if "net_annual_premium" in projection.columns
            else projection.loc[projection["Year"] == 2, "Gross_Premium_Inflow"]
        )
        * 0.5
    )
    
    # ==================================================
    # MATURITY ADJUSTMENT
    # ==================================================

    # Son yıl: poliçe olgunlaştı, surrender value = 0
    
    if "coverage_years" in projection.columns:
        last_year_mask = projection["Year"] >= projection["coverage_years"]
        projection.loc[last_year_mask, "adjusted_surrender_benefit"] = 0
    # Eğer coverage_years bilgisi varsa, son yıl ve sonrası için surrender benefit'i 0 yap.
    
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
    ).clip(0, 1).astype(float_dtype)
    # Lapse oranı arttıkça, adjusted_qx azalır (selection effect). Clip ile 0-1 arasında sınırla.
    
    # ==================================================
    # RECALCULATE DEATH BENEFITS (ADJUSTED)
    # ==================================================
    
    if "coverage_years" in projection.columns:
        in_force = (projection["Year"] <= projection["coverage_years"]).astype(np.float32)
    else:
        in_force = np.float32(1.0)

    projection["Adjusted_Death_Benefits"] = (
        in_force
        * projection["survival_ratio"]
        * projection["adjusted_qx"]
        * projection["sum_assured"]
    ).astype(float_dtype)
    # Adjusted death benefit = Survival Ratio × Adjusted qx × Sum Assured. Survival ratio, poliçenin hayatta kalma olasılığını temsil eder.
    
    # ==================================================
    # REINSURANCE (consistent with cashflows.py)
    # ==================================================

    re_rate = float(getattr(config, "reinsurance_cost_rate", 0.0) or 0.0)
    projection["Reinsurance_Ceding"] = (projection["Gross_Premium_Inflow"] * re_rate).astype(float_dtype)
    projection["Reinsurance_Recovery"] = (projection["Adjusted_Death_Benefits"] * re_rate).astype(float_dtype)

    projection["Counterparty_Default_Cost"] = (
        projection["Reinsurance_Recovery"]
        * float(getattr(config, "counterparty_pd", 0.0) or 0.0)
        * float(getattr(config, "counterparty_lgd", 0.0) or 0.0)
    ).astype(float_dtype)
    
    # ==================================================
    # POLICY-LEVEL BEL AGGREGATION
    # ==================================================
    
    # ==================================================
    # POLICY-LEVEL BEL AGGREGATION (LIABILITY-POSITIVE)
    # ==================================================

    # ==================================================
    # PV LIABILITY CASHFLOWS (liability-positive)
    # Timing convention:
    # - Premium inflow + reinsurance premium at opening
    # - Claims/expenses/surrender/recovery/default cost at closing
    # ==================================================

    pv_premiums_opening = (projection["Gross_Premium_Inflow"] * projection["discount_factor_opening"]).astype(float_dtype)
    pv_re_premium_opening = (projection["Reinsurance_Ceding"] * projection["discount_factor_opening"]).astype(float_dtype)

    pv_claims_closing = (projection["Adjusted_Death_Benefits"] * projection["discount_factor"]).astype(float_dtype)
    pv_surrender_closing = (projection["adjusted_surrender_benefit"] * projection["discount_factor"]).astype(float_dtype)
    pv_expenses_closing = (projection["Operating_Expenses"] * projection["discount_factor"]).astype(float_dtype)
    pv_recovery_closing = (projection["Reinsurance_Recovery"] * projection["discount_factor"]).astype(float_dtype)
    pv_default_closing = (projection["Counterparty_Default_Cost"] * projection["discount_factor"]).astype(float_dtype)

    projection["PV_Adjusted_Liability_Cash_Flow"] = (
        (pv_claims_closing + pv_surrender_closing + pv_expenses_closing + pv_re_premium_opening + pv_default_closing)
        - (pv_premiums_opening + pv_recovery_closing)
    ).astype(float_dtype)

    agg_map = {
        "PV_Adjusted_Liability_Cash_Flow": "sum",
        "sum_assured": "first",
    }
    # Opsiyonel alanlar
    for extra in ("coverage_years", "issue_age"):
        if extra in projection.columns:
            agg_map[extra] = "first"

    bel_result = (
        projection
        .groupby("policy_id", sort=False, as_index=False)
        .agg(agg_map)
        .rename(columns={"PV_Adjusted_Liability_Cash_Flow": "bel_per_policy"})
    )


    # ==================================================
    # LOGGING
    # ==================================================

    total_bel = float(bel_result["bel_per_policy"].sum())
    avg_bel = float(bel_result["bel_per_policy"].mean())
    asset_count = int((bel_result["bel_per_policy"] < 0).sum())

    if asset_count > 0:
        logger.info(f"ℹ️ {asset_count} poliçede net asset (BEL < 0) oluştu")

    logger.info(
        f"✓ BEL Hesaplandı (liability-positive): Total={total_bel:,.2f}, Avg={avg_bel:,.2f}"
    )
    return bel_result #Policy bazında BEL sonuçlarını içeren DataFrame'i döndür. Her satır bir poliçeyi temsil eder ve bel_per_policy sütunu o poliçenin BEL değerini içerir.


# ==================================================
# BEL SENSITIVITY ANALYSIS
# ==================================================

# BEL'in duyarlılık analizi (mortalite, lapse, discount rate şokları).
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
    
    # Default şok senaryoları
    if shock_scenarios is None:
        shock_scenarios = {
            # New-style keys (aligned with engine.scenarios.SCENARIOS)
            "base": {},
            "mortality_up_10": {"mortality_shock_multiplier": 1.10},
            "lapse_up_20": {"lapse_initial_rate_multiplier": 1.20},
            "rate_down_100bps": {"discount_rate_shift": -0.01},
        }
    
    sensitivity_results = [] #Her senaryo için BEL sonuçlarını depolamak için boş bir liste oluşturulur.
    
    # Her senaryo için BEL'i hesapla
    for scenario_name, shocks in shock_scenarios.items():
        proj_shock = projection.copy()

        # Backward-compatible interpretation of shocks:
        # - Prefer new-style keys used by engine.scenarios
        # - Fall back to legacy keys: mort_shock/lapse_shock/rate_shock
        scenario_updates: dict = {}

        if "discount_rate_shift" in shocks:
            scenario_updates["discount_rate_shift"] = float(shocks.get("discount_rate_shift") or 0.0)
        elif "rate_shock" in shocks:
            scenario_updates["discount_rate_shift"] = float(shocks.get("rate_shock") or 0.0)

        if "unit_expense_multiplier" in shocks:
            scenario_updates["unit_expense_multiplier"] = float(shocks.get("unit_expense_multiplier") or 1.0)

        # Config copy with scenario updates so that expense shocks apply in calculate_cashflows
        if hasattr(config, "model_copy"):
            cfg = config.model_copy(update=scenario_updates)
        else:
            from copy import deepcopy
            cfg = deepcopy(config)
            for k, v in scenario_updates.items():
                setattr(cfg, k, v)

        float_dtype = np.float64 if bool(getattr(cfg, "use_float64", False)) else np.float32

        # Mortality shock on qx (multiplier + optional additive)
        if "mortality_shock_multiplier" in shocks:
            mort_mult = float(shocks.get("mortality_shock_multiplier") or 1.0)
        else:
            mort_mult = 1.0 + float(shocks.get("mort_shock", 0.0) or 0.0)
        mort_add = float(shocks.get("mortality_shock", 0.0) or 0.0)

        # Lapse shock on lapse_rate (multiplier)
        if "lapse_initial_rate_multiplier" in shocks:
            lapse_mult = float(shocks.get("lapse_initial_rate_multiplier") or 1.0)
        else:
            lapse_mult = 1.0 + float(shocks.get("lapse_shock", 0.0) or 0.0)

        if "qx" in proj_shock.columns:
            proj_shock["qx"] = (proj_shock["qx"] * mort_mult + mort_add).clip(0, 1)
        if "lapse_rate" in proj_shock.columns:
            proj_shock["lapse_rate"] = (proj_shock["lapse_rate"] * lapse_mult).clip(0, 1)

        # Discount factors (flat rate curve assumption)
        effective_rate = float(cfg.discount_rate) + float(getattr(cfg, "discount_rate_shift", 0.0) or 0.0)
        if effective_rate <= -0.999:
            raise ValueError(f"discount_rate_shift çok büyük negatif: effective_rate={effective_rate}")

        v = 1.0 / (1.0 + effective_rate)
        t = proj_shock["Year"].astype(np.int32)
        proj_shock["discount_factor"] = (v ** t).astype(float_dtype)
        proj_shock["discount_factor_opening"] = (v ** (t - 1)).astype(float_dtype)

        # Recompute cashflows under shocked assumptions, then BEL
        from engine.cashflows import calculate_cashflows

        proj_shock = calculate_cashflows(proj_shock, cfg)
        bel_shock = calculate_bel(proj_shock, cfg)
        bel_shock["scenario"] = scenario_name
        
        sensitivity_results.append(bel_shock)
    
    # Tüm senaryo sonuçlarını birleştir
    sensitivity_df = pd.concat(sensitivity_results, ignore_index=True)
    
    # Loglama
    logger.info(f"✓ Sensitivity analysis tamamlandı: {len(shock_scenarios)} senaryo")
    
    return sensitivity_df #Senaryo bazında BEL sonuçlarını içeren DataFrame'i döndür.