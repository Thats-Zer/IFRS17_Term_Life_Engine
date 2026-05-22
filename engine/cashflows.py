from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# EXPENSE ALLOCATION
# ==================================================

def allocate_expenses(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Giderleri yıllara ve poliçelere tahsis et.
    
    Gider Türleri:
    1. Acquisition Cost (AC): Poliçe başında, ilk yılda
    2. Administration Cost (AdC): Yıllık, sabit veya premium'a % bağlı
    3. Collection Cost (CC): Premium tahsilinde, premium × rate
    4. Maintenance Cost (MC): Poliçe süresi boyunca, yıllık sabit
    5. Inflation Adjustment: Tüm giderlere enflasyon etkisi
    
    Formül:
    Total_Expense_t = (AC × indicator_year_1)
                    + AdC × (1 + inflation_rate)^(t-1)
                    + CC × Gross_Premium_t
                    + MC × (1 + inflation_rate)^(t-1)
    
    Args:
        projection: Projection tablosu (Year, policy_id sütunları)
        config: ModelConfig
        
    Returns:
        pd.DataFrame: Gider sütunları eklenmiş
        
    Raises:
        ValueError: Config giderleri geçersizse
    """
    projection = projection.copy()

    expense_mult = float(getattr(config, "unit_expense_multiplier", 1.0) or 1.0)
    
    # Validation
    if config.acquisition_cost < 0:
        raise ValueError(f"acquisition_cost >= 0 olmalı, {config.acquisition_cost} verildi")
    if config.admin_cost_per_policy < 0:
        raise ValueError(f"admin_cost_per_policy >= 0 olmalı, {config.admin_cost_per_policy} verildi")
    if config.collection_cost_rate < 0 or config.collection_cost_rate > 1:
        raise ValueError(f"collection_cost_rate [0, 1] olmalı, {config.collection_cost_rate} verildi")
    
    # ==================================================
    # 1. ACQUISITION COST (İlk Yıl)
    # ==================================================
    # Poliçe başında, ilk yılda ödenir
    projection["acquisition_cost"] = np.where(
        projection["Year"] == 1,
        float(config.acquisition_cost) * expense_mult,
        0
    ).astype(np.float32)
    
    # ==================================================
    # 2. ADMINISTRATION COST (Yıllık, Enflasyon Ayarlı)
    # ==================================================
    # Sabit yıllık gider, enflasyona göre artar
    inflation_factor = ((1 + config.inflation_rate) ** (projection["Year"] - 1)).astype(np.float32)
    projection["admin_cost"] = (
        (float(config.admin_cost_per_policy) * expense_mult) * inflation_factor
    ).astype(np.float32)
    
    # ==================================================
    # 3. COLLECTION COST (Premium'un Yüzdesi)
    # ==================================================
    # Prim tahsilinde ödenen gider: collection_cost_rate × collected premium
    # Not: Gross premium hesaplanmadan kesinleşmez; cashflows adımında hesaplanır.
    projection["collection_cost"] = 0.0  # placeholder
    
    # ==================================================
    # 4. MAINTENANCE COST (Poliçe Koruma Gideri)
    # ==================================================
    # Poliçe aktif olduğu sürece yıllık gider
    projection["maintenance_cost"] = (
        (float(config.maintenance_cost_per_policy) * expense_mult) * inflation_factor
    ).astype(np.float32)
    
    # ==================================================
    # TOTAL EXPENSE (Henüz Collection Cost hariç)
    # ==================================================
    projection["total_expense_base"] = (
        projection["acquisition_cost"]
        + projection["admin_cost"]
        + projection["maintenance_cost"]
    ).astype(np.float32)
    
    logger.debug("✓ Giderler tahsis edildi (acquisition, admin, maintenance)")
    
    return projection


# ==================================================
# SURRENDER CHARGES
# ==================================================

def calculate_surrender_charges(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Poliçe iptali durumunda fesih giderlerini hesapla.
    
    Term-life surrender convention:
    - Default cash surrender value is zero via `surrender_value_rate = 0`.
    - If a non-zero surrender value is configured, surrender charges are applied
      against that value rather than against sum assured.
    
    Formula (Linear Decline):
    Surrender_Charge_t = max(0, Surrender_Base × (1 - t / Coverage_Years))
    
    Formula (Exponential Decline):
    Surrender_Charge_t = max(0, Surrender_Base × exp(-decay × t))
    
    Args:
        projection: Projection tablosu
        config: ModelConfig
        
    Returns:
        pd.DataFrame: surrender_charge sütunu eklenmiş
        
    Raises:
        ValueError: Surrender parameters geçersizse
    """
    projection = projection.copy()
    
    # Validation
    if config.surrender_charge_rate < 0 or config.surrender_charge_rate > 1:
        raise ValueError(f"surrender_charge_rate [0, 1] olmalı, {config.surrender_charge_rate} verildi")
    
    # ==================================================
    # SURRENDER CHARGE HESAPLAMA (LINEAR DECLINE)
    # ==================================================
    # Formül: SC(t) = SC_base × max(0, 1 - t / coverage_years)
    
    # coverage_years'i projection'a merge et
    if "coverage_years" not in projection.columns:
        raise ValueError("projection'da 'coverage_years' sütunu gerekli")
    
    # Yıl oranı: t / coverage_years
    year_ratio = (projection["Year"] / projection["coverage_years"]).astype(np.float32)
    
    # Linear decline: max(0, 1 - year_ratio)
    surrender_multiplier = np.maximum(0, 1 - year_ratio).astype(np.float32)
    
    surrender_value_rate = float(getattr(config, "surrender_value_rate", 0.0) or 0.0)

    # Surrender charge (annual net premium surrender value base)
    if "net_annual_premium" in projection.columns:
        surrender_base = projection["net_annual_premium"] * surrender_value_rate
    else:
        surrender_base = 0.0

    projection["surrender_charge"] = (
        surrender_base
        * config.surrender_charge_rate
        * surrender_multiplier
    ).astype(np.float32)
    
    # Alternatif: exponential decline (isteğe bağlı)
    # projection["surrender_charge_exp"] = (
    #     projection["sum_assured"]
    #     * config.surrender_charge_rate
    #     * np.exp(-0.3 * projection["Year"])
    # ).clip(lower=0)
    
    logger.debug("✓ Surrender charges calculated (term-life value base)")
    
    return projection


# ==================================================
# ANNUAL PREMIUM CALCULATION
# ==================================================

def calculate_annual_premiums(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Yıllık net ve brüt prim hesapla (gelişmiş).
    
    IFRS17'de Premium Hesabı:
    
    Net Premium (NP):
        NP = PV(Expected Claims + Total Expenses) / PV(Premium Annuity)
    
    Brüt Premium (GP):
        GP = NP / (1 - loading_rate)
    
    Loading Rate:
        - Collection Cost Loading
        - Profit Margin Loading
        - Contingency Loading
    
    Premium Annuity (yıllık prim ödenebilir anüite):
        PA = Σ [v^t × S(t) × (1 - lapse_rate_t)]
    
    Args:
        projection: Projection tablosu (mortality, lapse, discount_factor içeren)
        config: ModelConfig
        
    Returns:
        pd.DataFrame: net_annual_premium ve gross_annual_premium eklenmiş
        
    Raises:
        ValueError: Premium parameters geçersizse
    """
    projection = projection.copy()

    if "coverage_years" in projection.columns:
        in_force = (projection["Year"] <= projection["coverage_years"]).astype(np.float32)
    else:
        in_force = np.float32(1.0)
    
    # Validation
    if config.profit_margin < 0 or config.profit_margin > 1:
        raise ValueError(f"profit_margin [0, 1] olmalı, {config.profit_margin} verildi")
    
    # ==================================================
    # EXPENSE PROJECTION (ALREADY DONE)
    # ==================================================
    if "total_expense_base" not in projection.columns:
        projection = allocate_expenses(projection, config)
    
    # Collection cost premium'un yüzdesidir; gross premium belirlendikten sonra cashflows adımında hesaplanır.
    projection["total_expense"] = projection["total_expense_base"].astype(np.float32)
    
    # ==================================================
    # PV CALCULATIONS (POLIÇE BAZINDA TOPLAMA)
    # ==================================================
    
    # PV of expected claims (with survival and lapse)
    projection["unit_claim_pv"] = (
        in_force
        * projection["survival_ratio"]
        * projection["qx"]
        * projection["sum_assured"]
        * projection["discount_factor"]
    ).astype(np.float32)
    
    # PV of total expenses
    projection["unit_expense_pv"] = (
        in_force
        * projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["total_expense"]
        * projection["discount_factor"]
    ).astype(np.float32)
    
    # Not: Surrender benefit modeli premium'a bağlı olduğundan net premium pricing içinde tam çözüm iteratif olur.
    # Bu engine'de net premium pricing'de surrender etkisi ihmal edilir (0) — yanlış işaret/double-count riskini önler.
    projection["unit_surrender_pv"] = np.float32(0.0)
    
    # PV of premium annuity (annuity due - yıl başında ödenebilir)
    # Premium annuity PV (annuity-due): prim yıl başında ödenir; lapse aynı yılın primini azaltmaz.
    projection["premium_annuity_pv"] = (
        in_force
        * projection["survival_ratio"]
        * projection["discount_factor_opening"]
    ).astype(np.float32)
    
    # ==================================================
    # POLIÇE BAZINDA TOPLAMA
    # ==================================================
    
    premium_calc = (
        projection
        .groupby("policy_id", sort=False, as_index=False)
        .agg({
            "unit_claim_pv": "sum",
            "unit_expense_pv": "sum",
            "unit_surrender_pv": "sum",
            "premium_annuity_pv": "sum",
            "sum_assured": "first",
            "coverage_years": "first"
        })
    )
    
    # ==================================================
    # NET PREMIUM HESAPLAMA
    # ==================================================
    
    # Denominator koruma (division by zero)
    premium_calc["premium_annuity_pv"] = premium_calc["premium_annuity_pv"].replace(0, np.nan)
    
    # Net premium: (Claims + Expenses) / Annuity
    premium_calc["net_annual_premium"] = (
        (premium_calc["unit_claim_pv"]
         + premium_calc["unit_expense_pv"]
         + premium_calc["unit_surrender_pv"])
        / premium_calc["premium_annuity_pv"]
    ).fillna(0).astype(np.float32)
    
    # ==================================================
    # GROSS PREMIUM HESAPLAMA
    # ==================================================
    
    # Loading: profit margin + contingency + expense loading
    total_loading = (
        config.profit_margin
        + config.contingency_loading
        + config.collection_cost_rate
    )
    
    # Gross premium = Net Premium / (1 - total_loading)
    # Eğer loading >= 1 ise uyarı
    if total_loading >= 1:
        logger.warning(f"⚠️ Total loading ({total_loading}) >= 1, gross premium hesaplanamayacak")
        premium_calc["gross_annual_premium"] = premium_calc["net_annual_premium"]
    else:
        premium_calc["gross_annual_premium"] = (
            premium_calc["net_annual_premium"]
            / (1 - total_loading)
        ).astype(np.float32)
    
    # ==================================================
    # PROJECTION'A MERGE ET
    # ==================================================
    
    projection = projection.merge(
        premium_calc[[
            "policy_id",
            "net_annual_premium",
            "gross_annual_premium"
        ]],
        on="policy_id",
        how="left"
    )
    
    # NaN handling
    projection["net_annual_premium"] = projection["net_annual_premium"].fillna(0.0).astype(np.float32)
    projection["gross_annual_premium"] = projection["gross_annual_premium"].fillna(0.0).astype(np.float32)
    
    logger.info("✓ Premium hesaplandı (net & gross, loading, surrender charges)")
    
    return projection


# ==================================================
# CASH FLOW CALCULATION
# ==================================================

def calculate_cashflows(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Term-life için yıllık nakit akışlarını hesapla (gelişmiş).
    
    Nakit Akış Bileşenleri:
    
    INFLOWS:
    1. Gross_Premium_Inflow: Tahsil edilen brüt prim
    
    OUTFLOWS:
    1. Death_Benefits: Ölüm halinde tazminat
    2. Surrender_Benefits: Poliçe iptali halinde iade
    3. Operating_Expenses: İşletme giderleri
    4. Reinsurance_Ceding: Reasürans bedeli
    5. Counterparty_Risk: Reasürans karşı taraf riski
    
    NET CASH FLOW = Inflows - Outflows
    
    Args:
        projection: Projection tablosu
        config: ModelConfig
        
    Returns:
        pd.DataFrame: Tüm nakit akış sütunları (PV ile)
        
    Raises:
        ValueError: Veriler geçersizse
    """
    projection = projection.copy()

    float_dtype = np.float64 if bool(getattr(config, "use_float64", False)) else np.float32

    if "coverage_years" in projection.columns:
        in_force = (projection["Year"] <= projection["coverage_years"]).astype(np.float32)
    else:
        in_force = np.float32(1.0)

    expense_mult = float(getattr(config, "unit_expense_multiplier", 1.0) or 1.0)
    
    # ==================================================
    # PREMIUM CALCULATION (YÖKSEKSELTİLMİŞ)
    # ==================================================
    
    if "net_annual_premium" not in projection.columns:
        projection = calculate_annual_premiums(projection, config)
    
    # ==================================================
    # INFLOWS
    # ==================================================
    
    # Gross premium inflow (prim yıl başında ödenir): in_force_opening × gross_premium
    projection["Gross_Premium_Inflow"] = (
        in_force
        * projection["survival_ratio"]
        * projection["gross_annual_premium"]
    ).astype(np.float32)
    
    # Net premium inflow (cost basis için)
    projection["Net_Premium_Inflow"] = (
        in_force
        * projection["survival_ratio"]
        * projection["net_annual_premium"]
    ).astype(np.float32)

    # Collection cost: premium'un yüzdesi (scenario expense multiplier dahil)
    projection["collection_cost"] = (
        projection["Gross_Premium_Inflow"]
        * float(config.collection_cost_rate)
        * expense_mult
    ).astype(np.float32)

    # Total expense (collection dahil)
    if "total_expense_base" not in projection.columns:
        projection = allocate_expenses(projection, config)
    projection["total_expense"] = (
        projection["total_expense_base"].astype(np.float32) + projection["collection_cost"]
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - DEATH BENEFITS
    # ==================================================
    
    lapse_mortality_correlation = float(getattr(config, "lapse_mortality_correlation", 0.1) or 0.0)
    projection["adjusted_qx"] = (
        projection["qx"]
        * (1 - lapse_mortality_correlation * projection["lapse_rate"])
    ).clip(0, 1).astype(np.float32)

    projection["Death_Benefits"] = (
        in_force
        * projection["survival_ratio"]
        * projection["adjusted_qx"]
        * projection["sum_assured"]
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - SURRENDER BENEFITS
    # ==================================================
    
    # Term-life default: no cash surrender value unless explicitly configured.
    if "surrender_charge" not in projection.columns:
        projection = calculate_surrender_charges(projection, config)

    surrender_value_rate = float(getattr(config, "surrender_value_rate", 0.0) or 0.0)
    surrender_value = (projection["net_annual_premium"] * surrender_value_rate).astype(np.float32)
    
    projection["Surrender_Benefit"] = (
        in_force
        * projection["survival_ratio"]
        * projection["lapse_rate"]
        * (surrender_value - projection["surrender_charge"])
    ).clip(lower=0).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - OPERATING EXPENSES
    # ==================================================
    
    if "total_expense" not in projection.columns:
        projection = allocate_expenses(projection, config)
    
    projection["Operating_Expenses"] = (
        in_force
        * projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["total_expense"]
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - REINSURANCE CEDING
    # ==================================================
    
    # Basit reasürans modeli:
    # - Reinsurance_Ceding: reasürans primi (prim tahsilatıyla orantılı)
    # - Reinsurance_Recovery: ölüm tazminatının ceded kısmı (inflow)
    projection["Reinsurance_Ceding"] = (
        projection["Gross_Premium_Inflow"]
        * float(config.reinsurance_cost_rate)
    ).astype(np.float32)

    projection["Reinsurance_Recovery"] = (
        projection["Death_Benefits"]
        * float(config.reinsurance_cost_rate)
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - COUNTERPARTY RISK
    # ==================================================
    
    # Reasürans karşı taraf default riski
    # Risk = Recovery Amount × Probability of Default × Loss Given Default
    projection["Counterparty_Default_Cost"] = (
        projection["Reinsurance_Recovery"]
        * config.counterparty_pd
        * config.counterparty_lgd
    ).astype(np.float32)
    
    # Net death benefit (reinsurance recovery sonrası)
    projection["Net_Death_Benefit"] = (
        projection["Death_Benefits"]
        - projection["Reinsurance_Recovery"]
    ).astype(np.float32)
    
    # ==================================================
    # TOTAL CASH FLOWS
    # ==================================================
    
    projection["Total_Outflows"] = (
        projection["Net_Death_Benefit"]
        + projection["Surrender_Benefit"]
        + projection["Operating_Expenses"]
        + projection["Reinsurance_Ceding"]
        + projection["Counterparty_Default_Cost"]
    ).astype(float_dtype)
    
    projection["Total_Inflows"] = (
        projection["Gross_Premium_Inflow"]
        + projection["Reinsurance_Recovery"]
    ).astype(float_dtype)

    projection["Net_Cash_Flow"] = (
        projection["Total_Inflows"]
        - projection["Total_Outflows"]
    ).astype(float_dtype)
    
    # ==================================================
    # PRESENT VALUE CALCULATIONS
    # ==================================================
    
    # PV CALCULATIONS — timing convention:
    # - Premium inflows & reinsurance premium at period start => discount_factor_opening
    # - Claims/expenses/surrender/recovery at period end => discount_factor
    if "discount_factor_opening" not in projection.columns:
        projection["discount_factor_opening"] = projection["discount_factor"]

    opening_cols = ["Gross_Premium_Inflow", "Net_Premium_Inflow", "Reinsurance_Ceding"]
    closing_cols = [
        "Death_Benefits",
        "Surrender_Benefit",
        "Operating_Expenses",
        "Reinsurance_Recovery",
        "Counterparty_Default_Cost",
        "Net_Death_Benefit",
        "Total_Inflows",
        "Total_Outflows",
        "Net_Cash_Flow",
    ]

    for col in opening_cols:
        if col in projection.columns:
            projection[f"PV_{col}"] = (projection[col] * projection["discount_factor_opening"]).astype(float_dtype)

    for col in closing_cols:
        if col in projection.columns:
            projection[f"PV_{col}"] = (projection[col] * projection["discount_factor"]).astype(float_dtype)

    projection["PV_Total_Inflows"] = (
        projection["PV_Gross_Premium_Inflow"]
        + projection["PV_Reinsurance_Recovery"]
    ).astype(float_dtype)
    projection["PV_Total_Outflows"] = (
        projection["PV_Net_Death_Benefit"]
        + projection["PV_Surrender_Benefit"]
        + projection["PV_Operating_Expenses"]
        + projection["PV_Reinsurance_Ceding"]
        + projection["PV_Counterparty_Default_Cost"]
    ).astype(float_dtype)
    projection["PV_Net_Cash_Flow"] = (
        projection["PV_Total_Inflows"]
        - projection["PV_Total_Outflows"]
    ).astype(float_dtype)
    
    logger.info("✓ Nakit akışları hesaplandı (inflow, outflow, PV)")
    
    return projection


# ==================================================
# TEST CASES
# ==================================================

def test_cashflows() -> None:
    """
    Nakit akış hesaplamalarının test modülü.
    
    Test Senaryoları:
    1. Premium hesabı
    2. Expense allocation
    3. Surrender charges
    4. Death benefit hesabı
    5. Net cash flow
    """
    from engine.assumptions import loadconfig
    from engine.curves import create_discount_curve
    from engine.projection import (
        create_master_data,
        create_projection_table,
        load_mortality_table
    )
    
    logger.info("=" * 60)
    logger.info("CASHFLOW TESTS BAŞLAMAK")
    logger.info("=" * 60)
    
    # Config yükle
    config = loadconfig("config/config.json")
    
    # Master data oluştur
    master_data = create_master_data(config)
    logger.info(f"✓ Test: Master data oluşturuldu ({len(master_data)} poliçe)")
    
    # Discount curve oluştur
    discount_curve = create_discount_curve(config)
    logger.info(f"✓ Test: Discount curve oluşturuldu ({len(discount_curve)} yıl)")
