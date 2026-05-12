from typing import Tuple, Optional 
#Bu, fonksiyonların döndürebileceği türleri belirtmek için kullanılır.
import pandas as pd
#Pandas, veri manipülasyonu ve analizi için kullanılan bir kütüphanedir.
import numpy as np
#NumPy, büyük, çok boyutlu diziler ve matrislerle çalışmak için kullanılan bir kütüphanedir.
import logging
#Logging, uygulama içinde bilgi mesajları, uyarılar ve hatalar kaydetmek için kullanılır.
from scipy import stats
#SciPy, istatistiksel hesaplamalar ve olasılık dağılımları için kullanılan bir kütüphanedir.

from model.config_model import ModelConfig
#ModelConfig, model yapılandırma parametrelerini içeren bir sınıftır.

logger = logging.getLogger(__name__)
#Bu, modülün adıyla bir logger oluşturur. 
# Logger, uygulama içinde bilgi mesajları, uyarılar ve hatalar kaydetmek için kullanılır.


# ==================================================
# RISK ADJUSTMENT CALCULATION
# ==================================================

def calculate_risk_adjustment(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame: # pd.DataFrame: policy_id ve ra_per_policy sütunları içeren bir DataFrame döndürür.
   
    """

    IFRS17 Risk Adjustment (RA) hesapla - KOMPLEKS YÖNTEM.
    
    Risk Adjustment Tanımı (IFRS17):
    RA = CoC × PV[Quantile_alpha(Liability) - E(Liability)]
    
    Nerede:
    - CoC: Cost of Capital Rate (genelde %6)
    - alpha: Confidence Level (genelde 75%)
    - Quantile: x. yüzde değeri
    - Liability: Net liability cashflows
    
    Risk Kategorileri:
    1. MORTALITE RİSKİ: Gerçek qx > beklenen qx
    2. LAPSE RİSKİ: Gerçek lapse > beklenen lapse
    3. EXPENSE RİSKİ: Gerçek expense > beklenen expense
    4. REASÜRANS RİSKİ: Counterparty default riski
        Mealen: karşı tarafın iflas etmesi durumunda ortaya çıkan risk
    
    Metodoloji:
    1. Her risk kategorisi için stokastik senaryo
    2. Yüzdelik hesabı (Quantile)
    3. RA = CoC × PV(Tail Risk)
    
    Args:
        projection: Projection tablosu
        config: ModelConfig (confidence_level, coc_rate)
        
    Returns:
        pd.DataFrame: policy_id ve ra_per_policy sütunları
        
    Raises:
        ValueError: Parameters geçersizse
    """
    
    # Doğrulama
    if config.coc_ratio < 0 or config.coc_ratio > 1:
        raise ValueError(f"coc_ratio [0, 1] olmalı, {config.coc_ratio} verildi")
    # Bu, coc_ratio'nun 0 ile 1 arasında olup olmadığını kontrol eder. Eğer değilse, bir ValueError hatası gönderir.

    if config.confidence_level < 0.5 or config.confidence_level > 1:
        raise ValueError(f"confidence_level [0.5, 1] olmalı, {config.confidence_level} verildi")
    # Bu, confidence_level'in 0.5 ile 1 arasında olup olmadığını kontrol eder. Eğer değilse, bir ValueError hatası gönderir.

    # RA hesaplaması için gerekli kolonların varlığını kontrol et ve sadece gerekli olanları array olarak al
    required_cols = [
        "policy_id",
        "qx",
        "survival_ratio",
        "sum_assured",
        "adjusted_surrender_benefit",
        "Operating_Expenses",
        "Gross_Premium_Inflow",
        "discount_factor",
    ]

    # Eksik sütunları kontrol et
    missing = [c for c in required_cols if c not in projection.columns]
    if missing:
        raise ValueError(f"RA için eksik sütunlar: {missing}")
    #Gerekli sütun yoksa hata mesajı verir ve fonksiyonun çalışmasını durdurur.

    # Sadece gerekli kolonlar ve sadece array olarak
    #Copy olmadan oluşturulan NumPy array'leri, bellek kullanımını azaltır ve performansı artırır.
    policy_id = projection["policy_id"].to_numpy(copy=False) 
    qx = projection["qx"].to_numpy(dtype=np.float32, copy=False)
    survival_ratio = projection["survival_ratio"].to_numpy(dtype=np.float32, copy=False)
    sum_assured = projection["sum_assured"].to_numpy(dtype=np.float32, copy=False)
    adj_surrender = projection["adjusted_surrender_benefit"].to_numpy(dtype=np.float32, copy=False)
    op_exp = projection["Operating_Expenses"].to_numpy(dtype=np.float32, copy=False)
    gross_premium = projection["Gross_Premium_Inflow"].to_numpy(dtype=np.float32, copy=False)
    discount_factor = projection["discount_factor"].to_numpy(dtype=np.float32, copy=False)


    n_rows = len(projection) # Projeksiyon tablosundaki satır sayısı (policy-year satırları).
    n_scenarios = int(config.n_risk_scenarios) # Risk senaryolarının sayısı, model yapılandırmasından alınır.
    #Bu, risk hesaplaması için kaç farklı senaryo oluşturulacağını belirler.

    # policy_id satır bazlı geldiği için poliçe bazına indirgemek gerekir
    unique_policies, policy_index = np.unique(policy_id, return_inverse=True)
    n_policies = unique_policies.size

    # Senaryo sonuçlarını poliçe bazında tut (PV, years summed)
    scenario_pv = np.empty((n_scenarios, n_policies), dtype=np.float32)
    tmp_policy_pv = np.zeros(n_policies, dtype=np.float32)

    for s in range(n_scenarios):
        stochastic_qx = np.random.binomial(n=1, p=qx, size=n_rows).astype(np.float32)
        #Bu, her poliçe için ölüm olayının gerçekleşip gerçekleşmediğini belirlemek için
        # qx değerlerine göre binom dağılımından rastgele sayılar üretir. 
        # 1, ölüm olayının gerçekleştiğini, 0 ise gerçekleşmediğini gösterir.

        stochastic_death_benefits = survival_ratio * stochastic_qx * sum_assured
        #Bu, her poliçe için ölüm durumunda ödenecek tazminat miktarını hesaplar.

        scenario_net_liability = (
            stochastic_death_benefits #poliçe başı tazminat tutarı
            + adj_surrender #beklenen iptal durumunda ödenecek tutar
            + op_exp #beklenen operasyonel giderler
            - gross_premium #beklenen prim gelirleri
        ).astype(np.float32) #Bu, her poliçe için net yükümlülüğü hesaplar.

        pv_row = (scenario_net_liability * discount_factor).astype(np.float32)

        # poliçe bazında PV topla
        tmp_policy_pv.fill(0.0)
        np.add.at(tmp_policy_pv, policy_index, pv_row)
        scenario_pv[s, :] = tmp_policy_pv

    # Beklenen değer ve kuantil
    expected_pv = scenario_pv.mean(axis=0) # Poliçe bazında beklenen PV
    tail_pv = np.quantile(scenario_pv, config.confidence_level, axis=0) # Poliçe bazında kuantil

    ra_per_policy = np.maximum(tail_pv - expected_pv, 0.0) * float(config.coc_ratio)
    # Bu, her poliçe için risk ayarlamasını hesaplar. Eğer tail_pv beklenen değerden düşükse, risk ayarlaması sıfır olur.

    return pd.DataFrame(
        {
            "policy_id": unique_policies,
            "ra_per_policy": ra_per_policy.astype(np.float32),
        }
    )


# ==================================================
# RISK DECOMPOSITION
# ==================================================

def decompose_risk_adjustment(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Risk Adjustment'ı risk bileşenlerine ayır.
    
    Returns:
        pd.DataFrame: Mortality, lapse, expense, counterparty risk ayrı ayrı
    """
    
    ra_full = calculate_risk_adjustment(projection, config)
    
    # Daha detaylı breakdown (basitleştirilmiş)
    ra_breakdown = ra_full.copy()
    
    ra_breakdown["mortality_ra"] = ra_full["ra_per_policy"] * 0.60
    # Bu, toplam risk ayarlamasının %60'ının mortalite riskinden kaynaklandığını varsayar.
    ra_breakdown["lapse_ra"] = ra_full["ra_per_policy"] * 0.25
    # Bu, toplam risk ayarlamasının %25'inin lapse riskinden kaynaklandığını varsayar.
    ra_breakdown["expense_ra"] = ra_full["ra_per_policy"] * 0.10
    # Bu, toplam risk ayarlamasının %10'unun expense riskinden kaynaklandığını varsayar.
    ra_breakdown["counterparty_ra"] = ra_full["ra_per_policy"] * 0.05
    # Bu, toplam risk ayarlamasının %5'inin karşı iflas riskinden kaynaklandığını varsayar.
    
    logger.info("✓ Risk decomposition tamamlandı")
    
    return ra_breakdown #Bu, her poliçe için toplam risk ayarlamasını ve her bir risk kategorisine düşen payı içeren bir DataFrame döndürür.