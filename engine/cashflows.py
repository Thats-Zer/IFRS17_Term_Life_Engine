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
        config.acquisition_cost,
        0
    ).astype(np.float32)
    
    # ==================================================
    # 2. ADMINISTRATION COST (Yıllık, Enflasyon Ayarlı)
    # ==================================================
    # Sabit yıllık gider, enflasyona göre artar
    inflation_factor = ((1 + config.inflation_rate) ** (projection["Year"] - 1)).astype(np.float32)
    projection["admin_cost"] = (
        config.admin_cost_per_policy * inflation_factor
    ).astype(np.float32)
    
    # ==================================================
    # 3. COLLECTION COST (Premium'un Yüzdesi)
    # ==================================================
    # Prim tahsilinde ödenen gider (ileride hesaplanacak)
    # Burada placeholder, calculate_annual_premiums'dan sonra hesaplanacak
    projection["collection_cost"] = 0.0  # Placeholder
    
    # ==================================================
    # 4. MAINTENANCE COST (Poliçe Koruma Gideri)
    # ==================================================
    # Poliçe aktif olduğu sürece yıllık gider
    projection["maintenance_cost"] = (
        config.maintenance_cost_per_policy * inflation_factor
    ).astype(np.float32)
    
    # ==================================================
    # TOTAL EXPENSE (Henüz Collection Cost hariç)
    # ==================================================
    projection["total_expense_before_collection"] = (
        projection["acquisition_cost"]
        + projection["admin_cost"]
        + projection["maintenance_cost"]
    ).astype(np.float32)
    
    logger.debug("✓ Gidiler tahsis edildi (acquisition, admin, maintenance)")
    
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
    
    Surrender Charge Mantığı:
    - Poliçe başında yüksek (ilk yıllarda)
    - Zamanla azalır (linearly veya exponentially)
    - Coverage dönemi sonunda sıfır
    
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
    
    # Surrender charge (Sum Assured'ın yüzdesi olarak)
    projection["surrender_charge"] = (
        projection["sum_assured"]
        * config.surrender_charge_rate
        * surrender_multiplier
    ).astype(np.float32)
    
    # Alternatif: exponential decline (isteğe bağlı)
    # projection["surrender_charge_exp"] = (
    #     projection["sum_assured"]
    #     * config.surrender_charge_rate
    #     * np.exp(-0.3 * projection["Year"])
    # ).clip(lower=0)
    
    logger.debug("✓ Fesih giderleri hesaplandı (linear decline)")
    
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
    
    # Validation
    if config.profit_margin < 0 or config.profit_margin > 1:
        raise ValueError(f"profit_margin [0, 1] olmalı, {config.profit_margin} verildi")
    
    # ==================================================
    # EXPENSE PROJECTION (ALREADY DONE)
    # ==================================================
    if "total_expense_before_collection" not in projection.columns:
        projection = allocate_expenses(projection, config)
    
    # ==================================================
    # COLLECTION COST (NOW CALCULATE)
    # ==================================================
    # Collection cost henüz gross premium hesaplanmadığı için
    # iteratif yaklaşım gerekli veya simplification kullan
    # Simplification: Collection cost = admin_cost'un % X'i
    projection["collection_cost"] = (
        projection["total_expense_before_collection"]
        * config.collection_cost_rate
    ).astype(np.float32)
    
    # Total expense (collection cost included)
    projection["total_expense"] = (
        projection["total_expense_before_collection"]
        + projection["collection_cost"]
    ).astype(np.float32)
    
    # ==================================================
    # PV CALCULATIONS (POLIÇE BAZINDA TOPLAMA)
    # ==================================================
    
    # PV of expected claims (with survival and lapse)
    projection["unit_claim_pv"] = (
        projection["survival_ratio"]
        * projection["qx"]
        * projection["sum_assured"]
        * projection["discount_factor"]
    ).astype(np.float32)
    
    # PV of total expenses
    projection["unit_expense_pv"] = (
        projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["total_expense"]
        * projection["discount_factor"]
    ).astype(np.float32)
    
    # PV of surrender charges (poliçe iptali sırasında)
    projection = calculate_surrender_charges(projection, config)
    
    projection["unit_surrender_pv"] = (
        projection["survival_ratio"]
        * projection["lapse_rate"]
        * projection["surrender_charge"]
        * projection["discount_factor"]
    ).astype(np.float32)
    
    # PV of premium annuity (annuity due - yıl başında ödenebilir)
    projection["premium_annuity_pv"] = (
        projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["discount_factor_opening"]  # Annuity due için opening factor
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
    
    # Net premium: (Claims + Expenses + Surrender Charges) / Annuity
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
    
    # ==================================================
    # PREMIUM CALCULATION (YÖKSEKSELTİLMİŞ)
    # ==================================================
    
    if "net_annual_premium" not in projection.columns:
        projection = calculate_annual_premiums(projection, config)
    
    # ==================================================
    # INFLOWS
    # ==================================================
    
    # Gross premium inflow (survival × (1-lapse) × gross_premium)
    projection["Gross_Premium_Inflow"] = (
        projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["gross_annual_premium"]
    ).astype(np.float32)
    
    # Net premium inflow (cost basis için)
    projection["Net_Premium_Inflow"] = (
        projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["net_annual_premium"]
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - DEATH BENEFITS
    # ==================================================
    
    projection["Death_Benefits"] = (
        projection["survival_ratio"]
        * projection["qx"]
        * projection["sum_assured"]
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - SURRENDER BENEFITS
    # ==================================================
    
    # Iptali halinde, net prim artık hesaplanmış olacağından,
    # poliçe sahibi rezerv miktarı alır (surrender value)
    if "surrender_charge" not in projection.columns:
        projection = calculate_surrender_charges(projection, config)
    
    projection["Surrender_Benefit"] = (
        projection["survival_ratio"]
        * projection["lapse_rate"]
        * (projection["Net_Premium_Inflow"] - projection["surrender_charge"])
    ).clip(lower=0).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - OPERATING EXPENSES
    # ==================================================
    
    if "total_expense" not in projection.columns:
        projection = allocate_expenses(projection, config)
    
    projection["Operating_Expenses"] = (
        projection["survival_ratio"]
        * (1 - projection["lapse_rate"])
        * projection["total_expense"]
    ).astype(np.float32)
    
    # ==================================================
    # OUTFLOWS - REINSURANCE CEDING
    # ==================================================
    
    # Reasürans bedeli (death benefit'in yüzdesi)
    projection["Reinsurance_Ceding"] = (
        projection["Death_Benefits"]
        * config.reinsurance_cost_rate
    ).astype(np.float32)
    
    # Reinsurance recovery (ölüm halinde, reasüranstan alınan)
    projection["Reinsurance_Recovery"] = (
        projection["Death_Benefits"]
        * config.reinsurance_cost_rate
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
    
    # Net death benefit (reinsurance sonrası)
    projection["Net_Death_Benefit"] = (
        projection["Death_Benefits"]
        - projection["Reinsurance_Ceding"]
    ).astype(np.float32)
    
    # ==================================================
    # TOTAL CASH FLOWS
    # ==================================================
    
    projection["Total_Outflows"] = (
        projection["Net_Death_Benefit"]
        + projection["Surrender_Benefit"]
        + projection["Operating_Expenses"]
        + projection["Counterparty_Default_Cost"]
    ).astype(np.float32)
    
    projection["Net_Cash_Flow"] = (
        projection["Gross_Premium_Inflow"]
        - projection["Total_Outflows"]
    ).astype(np.float32)
    
    # ==================================================
    # PRESENT VALUE CALCULATIONS
    # ==================================================
    
    pv_columns = [
        "Gross_Premium_Inflow",
        "Death_Benefits",
        "Surrender_Benefit",
        "Operating_Expenses",
        "Reinsurance_Ceding",
        "Counterparty_Default_Cost",
        "Total_Outflows",
        "Net_Cash_Flow"
    ]
    
    for col in pv_columns:
        projection[f"PV_{col}"] = (
            projection[col] * projection["discount_factor"]
        ).astype(np.float32)
    
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
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
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