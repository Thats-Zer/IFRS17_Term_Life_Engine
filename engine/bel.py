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
    #Hata kontrol bloğu, PV_NetCash_Flow'u konntrol eder, yoksa hata uyarısı verir.
    
    # ==================================================
    # EARLY SURRENDER ADJUSTMENT
    # ==================================================
    # Yıl 1-2'de surrender value negatif olabilir (acquisition cost recovery)
    
    projection["adjusted_surrender_benefit"] = projection["Surrender_Benefit"].copy()
    # İlk 2 yıl için surrender benefit'i düzelt (acquisition cost recovery etkisi)
    
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
    ).clip(0, 1).astype(np.float32)
    # Lapse oranı arttıkça, adjusted_qx azalır (selection effect). Clip ile 0-1 arasında sınırla.
    
    # ==================================================
    # RECALCULATE DEATH BENEFITS (ADJUSTED)
    # ==================================================
    
    projection["Adjusted_Death_Benefits"] = (
        projection["survival_ratio"]
        * projection["adjusted_qx"]
        * projection["sum_assured"]
    ).astype(np.float32)
    # Adjusted death benefit = Survival Ratio × Adjusted qx × Sum Assured. Survival ratio, poliçenin hayatta kalma olasılığını temsil eder.
    
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
    # Adjusted Net Cash Flow = Gross Premiums - Adjusted Death Benefits - Adjusted Surrender Benefits - Operating Expenses - Counterparty Default Cost
    
    projection["PV_Adjusted_Net_Cash_Flow"] = (
        projection["Adjusted_Net_Cash_Flow"]
        * projection["discount_factor"]
    ).astype(np.float32)
    # PV Adjusted Net Cash Flow = Adjusted Net Cash Flow × Discount Factor. Discount factor, gelecekteki nakit akışlarının bugünkü değerini hesaplamak için kullanılır.
    
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
    # Policy bazında BEL'i hesapla: PV Adjusted Net Cash Flow'ların toplamı. Diğer bilgileri de ekle (sum assured, coverage years, issue age).


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
    # Onerous poliçelerin sayısını logla. Onerous poliçe, BEL değeri negatif olan poliçedir ve bu durum finansal raporlama açısından önemlidir.


    total_bel = bel_result["bel_per_policy"].sum()
    # Toplam BEL'i hesapla. Bu, tüm poliçelerin BEL'lerinin toplamıdır ve şirketin toplam yükümlülüğünü gösterir.

    avg_bel = bel_result["bel_per_policy"].mean()
    # Ortalama BEL'i hesapla. Bu, poliçe başına ortalama yükümlülüğü gösterir.

    logger.info(
        f"✓ BEL Hesaplandı: Total={total_bel:,.2f}, "
        f"Avg={avg_bel:,.2f}, Onerous={onerous_count}"
    )
    # Hesaplama tamamlandığında toplam BEL, ortalama BEL ve onerous poliçe sayısını logla.
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
            "base": {"mort_shock": 0, "lapse_shock": 0, "rate_shock": 0},
            "mortality_up_10": {"mort_shock": 0.10, "lapse_shock": 0, "rate_shock": 0},
            "lapse_up_20": {"mort_shock": 0, "lapse_shock": 0.20, "rate_shock": 0},
            "rate_down_100bps": {"mort_shock": 0, "lapse_shock": 0, "rate_shock": -0.01},
        }
    
    sensitivity_results = [] #Her senaryo için BEL sonuçlarını depolamak için boş bir liste oluşturulur.
    
    # Her senaryo için BEL'i hesapla
    for scenario_name, shocks in shock_scenarios.items():
        proj_shock = projection.copy()
        
        #Mortalite ve lapse şoklarını uygula
        proj_shock["adjusted_qx"] = (
            proj_shock["qx"]
            * (1 + shocks["mort_shock"])
        ).clip(0, 1)
        
        #Lapse şokunu uygula
        proj_shock["shocked_lapse_rate"] = (
            proj_shock["lapse_rate"]
            + shocks["lapse_shock"]
        ).clip(0, 1)
        
        # BEL hesaplaması için discount rate şokunu uygula
        proj_shock["shocked_discount_rate"] = (
            proj_shock["discount_rate"]
            + shocks["rate_shock"]
        ).clip(0, 1)
        proj_shock["discount_factor"] = 1 / (1 + proj_shock["shocked_discount_rate"]) ** proj_shock["Year"]
        bel_shock = calculate_bel(proj_shock, config)
        bel_shock["scenario"] = scenario_name
        
        sensitivity_results.append(bel_shock)
    
    # Tüm senaryo sonuçlarını birleştir
    sensitivity_df = pd.concat(sensitivity_results, ignore_index=True)
    
    # Loglama
    logger.info(f"✓ Sensitivity analysis tamamlandı: {len(shock_scenarios)} senaryo")
    
    return sensitivity_df #Senaryo bazında BEL sonuçlarını içeren DataFrame'i döndür.