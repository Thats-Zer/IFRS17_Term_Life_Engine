from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# ONEROUS GROUP DETECTION
# ==================================================

# Onerous grup tespiti yap. Hangi grupların onerous olduğunu belirlemek için kullanılır.
def detect_onerous_groups(
    csm_result: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    

    """
    Onerous grup tespiti (KOMPLEKS YÖNTEM).
    
    Onerous Grup Tanımı:
    - CSM < 0 (liability > premiums)
    - Veya BEL + RA > PV(Premiums)
    
    Onerous Grup Özellikleri:
    1. Initial onerous: poliçe başında zaten onerous
    2. Subsequently onerous: sonradan onerous olur
    
    Yönetim:
    - Initial: Loss immediately recognized
    - Subsequently: Loss recognized as happen
    
    Args:
        csm_result: CSM calculations
        config: ModelConfig
        
    Returns:
        pd.DataFrame: Onerous group flag ve loss amount
    """
    
    # CSM sonuçlarını kopyala (orijinal DataFrame'i değiştirmemek için)
    csm_result = csm_result.copy()
    

    # ==================================================
    # ONEROUS GROUP FLAGS
    # ==================================================
    

    # is_onerous_initial sütunu oluşturulurken get() metodu kullanarak varsayılan değer ataması yapalım. Böylece, eğer csm_result DataFrame'inde is_onerous sütunu yoksa, is_onerous_initial sütunu False olarak atanır.
    csm_result["is_onerous_initial"] = csm_result.get("is_onerous", False)
    
    # Subsequently onerous: IFRS17 floor makes reported CSM non-negative.
    # Therefore we detect this using the *raw* (unclipped) closing CSM if available.
    csm_closing_raw = csm_result.get("csm_closing_raw", csm_result.get("csm_closing", 0.0))
    csm_result["is_onerous_subsequently"] = (
        (csm_closing_raw < 0)
        & (~csm_result["is_onerous_initial"])
    )
    
    # is_onerous_group sütunu, is_onerous_initial veya is_onerous_subsequently sütunlarından herhangi biri True ise True olur. Böylece, bir poliçe ya baştan onerous ise ya da sonradan onerous olmuşsa, is_onerous_group sütunu True olarak atanır.
    csm_result["is_onerous_group"] = (
        csm_result["is_onerous_initial"]
        | csm_result["is_onerous_subsequently"]
    )
    
    # ==================================================
    # LOSS CALCULATION
    # ==================================================
    
    # Initial onerous loss should be a POSITIVE amount (consistent with engine.csm output).
    if "onerous_loss" in csm_result.columns:
        csm_result["onerous_loss_initial"] = np.where(
            csm_result["is_onerous_initial"],
            csm_result["onerous_loss"],
            0.0,
        ).astype(np.float32)
    else:
        csm_result["onerous_loss_initial"] = np.where(
            csm_result["is_onerous_initial"],
            (csm_result.get("bel_opening", 0.0) + csm_result.get("ra_opening", 0.0) - csm_result.get("pv_premiums", 0.0)),
            0.0,
        ).clip(lower=0).astype(np.float32)
    
    # Subsequently onerous loss: positive amount = max(-csm_closing_raw, 0)
    csm_result["onerous_loss_subsequently"] = np.where(
        csm_result["is_onerous_subsequently"],
        (-pd.Series(csm_closing_raw)).clip(lower=0),
        0.0,
    ).astype(np.float32)
    
    # Total onerous loss
    csm_result["onerous_loss_total"] = (
        csm_result["onerous_loss_initial"]
        + csm_result["onerous_loss_subsequently"]
    ).astype(np.float32)
    
    # Onerous grup sayısını ve toplam loss miktarını logla
    logger.info(
        f"✓ Onerous grupos detected: "
        f"Initial={csm_result['is_onerous_initial'].sum()}, "
        f"Subsequently={csm_result['is_onerous_subsequently'].sum()}"
    )
    
    return csm_result # is_onerous_group, onerous_loss_total gibi yeni sütunlar eklenmiş olarak döner.


# ==================================================
# BUSINESS NATURE GROUPING
# ==================================================

# Poliçeleri business nature'a göre grupla. Bu, IFRS17 raporlaması için önemli bir adımdır.
def group_by_business_nature(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    
    
    """
    Poliçeleri business nature'a göre grupla.
    
    IFRS17 Business Nature Kategorileri:
    1. Term Life: Belirli dönem teminatı
    2. Permanent: Ömür boyu teminat
    3. Participating: İştirakçi ürünler
    4. Investment Linked: Fonda bağlı ürünler
    
    Grouping Criteria:
    - coverage_years <= 25: Short-term (Term Life)
    - coverage_years > 25: Long-term (Permanent)
    
    Args:
        projection: Projection tablosu
        config: ModelConfig
        
    Returns:
        pd.DataFrame: business_nature grubu eklendi
    """
    
    # Projection tablosunu kopyala (orijinal DataFrame'i değiştirmemek için)
    projection = projection.copy()
    
    # ==================================================
    # BUSINESS NATURE ASSIGNMENT
    # ==================================================
    
    # Öncelikle tüm poliçeleri "Term Life" olarak ata (default)
    projection["business_nature"] = "Term Life"  # Default
    
    # Longer term poliçeler
    projection.loc[
        projection["coverage_years"] > 25,
        "business_nature"
    ] = "Permanent Life"
    
    # Participating ürünler için özel bir işaret varsa, onları "Participating" olarak ata
    if "is_participating" in projection.columns:
        projection.loc[
            projection["is_participating"],
            "business_nature"
        ] = "Participating"
    
    # Investment linked ürünler için özel bir işaret varsa, onları "Investment Linked" olarak ata
    if "is_investment_linked" in projection.columns:
        projection.loc[
            projection["is_investment_linked"],
            "business_nature"
        ] = "Investment Linked"

    # Business nature gruplarını logla
    logger.debug(f"✓ Grouped by business nature: {projection['business_nature'].unique()}")
    
    return projection


# ==================================================
# RISK GROUP ASSIGNMENT
# ==================================================

# Poliçeleri risk karakteristiklerine göre grupla. Bu, risk ayarlamasının daha doğru hesaplanması için önemlidir.
def group_by_risk_characteristics(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    
    
    """
    Poliçeleri risk özelliklerine göre grupla.
    
    Risk Karakteristikleri:
    1. Risk Level: Low, Medium, High
       - qx based (mortalite riski)
    2. Lapse Risk: Low, Medium, High
       - lapse_rate based
    3. Reinsurance: Ceded, Retained
    
    Args:
        projection: Projection tablosu
        config: ModelConfig
        
    Returns:
        pd.DataFrame: risk_group eklendi
    """
    
    # Projection tablosunu kopyala (orijinal DataFrame'i değiştirmemek için)
    projection = projection.copy()
    
    # ==================================================
    # RISK LEVEL
    # ==================================================
    
    # qx'e göre risk seviyesini belirle. Öncelikle policy_id bazında ortalama qx hesapla. Bu, her poliçenin genel risk seviyesini belirlemek için kullanılacak.
    avg_qx = projection.groupby("policy_id")["qx"].mean()
    
    # qx değerlerine göre risk seviyesini ata. Risk seviyeleri, config'te tanımlanan eşiklere göre belirlenir.
    # Eğer avg_qx değeri low_risk_qx_threshold eşik değerinden küçük veya eşitse, risk seviyesi "Low" olarak atanır. 
    # Eğer avg_qx değeri low_risk_qx_threshold ile medium_risk_qx_threshold arasında ise, risk seviyesi "Medium" olarak atanır. 
    # Eğer avg_qx değeri medium_risk_qx_threshold eşik değerinden büyük ise, risk seviyesi "High" olarak atanır.
    projection = projection.merge(
        avg_qx.to_frame("avg_qx"),
        left_on="policy_id",
        right_index=True,
        how="left"
    )
    

    risk_thresholds = {
        "Low": getattr(config, "low_risk_qx_threshold", 0.01),
        "Medium": getattr(config, "medium_risk_qx_threshold", 0.05),
        "High": float("inf")
    }
    
    # risk seviyelerini logla
    for level, threshold in risk_thresholds.items():
        if level == "Low":
            mask = projection["avg_qx"] <= threshold
        elif level == "Medium":
            mask = (projection["avg_qx"] > risk_thresholds["Low"]) & (projection["avg_qx"] <= threshold)
        else:
            mask = projection["avg_qx"] > risk_thresholds["Medium"]
        
        projection.loc[mask, "risk_level"] = level
    
    # ==================================================
    # LAPSE RISK GROUP
    # ==================================================
    
    # Lapse riskini belirlemek için policy_id bazında ortalama lapse_rate hesapla. Bu, her poliçenin genel iptal risk seviyesini belirlemek için kullanılacak.
    avg_lapse = projection.groupby("policy_id")["lapse_rate"].mean().fillna(0.0)
    
    # Lapse risk seviyelerini ata. Lapse risk seviyeleri, config'te tanımlanan eşiklere göre belirlenir.
    projection = projection.merge(
        avg_lapse.to_frame("avg_lapse"),
        left_on="policy_id",
        right_index=True,
        how="left"
    )
    
    projection["lapse_risk"] = pd.cut(
        projection["avg_lapse"],
        bins=[0, 0.05, 0.15, 1.0],
        labels=["Low", "Medium", "High"],
        include_lowest=True,
    )
    
    # ==================================================
    # REINSURANCE GROUP
    # ==================================================

# Reinsurance durumunu belirle. Eğer is_reinsured sütunu varsa, bu sütuna göre "Ceded" veya "Retained" olarak grupla. Eğer is_reinsured sütunu yoksa, tüm poliçeler "Retained" olarak kabul edilir.
    projection["reinsurance_group"] = "Retained"
    if "is_reinsured" in projection.columns:
        projection.loc[projection["is_reinsured"].fillna(False).astype(bool), "reinsurance_group"] = "Ceded"

    # ==================================================
    # RISK GROUP
    # ==================================================

    # Risk grubu ataması yap. Bu örnekte, risk grubu sadece risk_level ve lapse_risk kombinasyonuna göre belirleniyor. Ancak, reinsurance_group gibi diğer faktörler de dahil edilebilir.
    projection["risk_group"] = "DEFAULT"
    if getattr(config, "use_risk_grouping", False) and "some_column" in projection.columns:
        mask = projection["some_column"].notna()
        projection.loc[mask, "risk_group"] = "GROUP_1"

    # Risk karakteristiklerine göre grupları logla
    logger.debug(f"✓ Grouped by risk characteristics")

    return projection # risk_level, lapse_risk ve reinsurance_group gibi yeni sütunlar eklenmiş olarak döner.


# ==================================================
# GROUP LEVEL AGGREGATION
# ==================================================

# IFRS17 gruplarını ata ve grup bazında aggrege et. Bu, raporlama ve analiz için önemli bir adımdır.
def assign_ifrs17_groups(
    csm_result: pd.DataFrame,
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    

    """
    IFRS17 gruplarını ata ve grup bazında aggrege et.
    
    IFRS17 Grup Tanımı:
    - Aynı business nature
    - Aynı risk karakteristikleri
    - Birbirinden bağımsız yönetim
    
    Group Aggregation:
    - Portfolio level: Tüm poliçeler
    - Business Nature level: Term, Permanent, vb.
    - Risk level: Low, Medium, High
    
    Args:
        csm_result: CSM calculations
        projection: Projection tablosu
        config: ModelConfig
        
    Returns:
        pd.DataFrame: Grup bazında aggregasyon
    """
    

    # ==================================================
    # GROUP ASSIGNMENT
    # ==================================================
    

    # Öncelikle business nature'a göre grupla. Bu, tüm gruplama işlemlerinin temelini oluşturur. Business nature, poliçelerin işlevselliğine göre sınıflandırılmasıdır
    projection = group_by_business_nature(projection, config)
    
    # Risk karakteristiklerine göre grupla. Bu, risk ayarlamasının daha doğru hesaplanması için önemlidir.
    projection = group_by_risk_characteristics(projection, config)
    
    # Onerous grup tespiti yap. Hangi grupların onerous olduğunu belirlemek için kullanılır.
    csm_result = detect_onerous_groups(csm_result, config)
    
    # ==================================================
    # GROUP KEYS
    # ==================================================

# Grup anahtarları oluştur. Business nature, risk_level ve lapse_risk kombinasyonuna göre grup anahtarı oluşturulur. Bu, her poliçenin hangi gruba ait olduğunu belirlemek için kullanılır.
    projection["group_id"] = (
        projection["business_nature"]
        + "_"
        + projection.get("risk_level", "Unknown")
        + "_"
        + projection.get("lapse_risk", "Unknown").astype(str)
    )
    
    # ==================================================
    # GROUP LEVEL AGGREGATION
    # ==================================================
    
    # Grup bazında aggregasyon yap. group_id'ye göre gruplama yaparak, her grup için poliçe sayısı, toplam teminat tutarı ve ortalama coverage_years gibi özet istatistikler hesaplanır.
    group_agg = (
        projection
        .groupby("group_id", sort=False, as_index=False)
        .agg({
            "policy_id": "count",
            "sum_assured": "sum",
            "coverage_years": "mean"
        })
        .rename(columns={
            "policy_id": "n_policies",
            "sum_assured": "total_sum_assured"
        })
    )
    
    # CSM sonuçları ile grupları birleştir. CSM sonuçları, poliçe bazında olduğundan, group_id'ye göre gruplama yaparak onerous grup bilgilerini ekleyelim.
    policy_group_mapping = projection[["policy_id", "group_id"]].drop_duplicates()
    
    csm_group = (
        csm_result
        .merge(policy_group_mapping, on="policy_id")
        .groupby("group_id", sort=False, as_index=False)
        .agg({
            "is_onerous_group": "any",
            "onerous_loss_total": "sum",
            "csm_opening": "sum",
            "csm_closing": "sum"
        })
    )
    
    # group_agg ile csm_group'u group_id üzerinden birleştir. Bu, her grup için onerous grup bilgilerini ve loss miktarlarını ekler.
    group_agg = group_agg.merge(csm_group, on="group_id", how="left")
    
    # Onerous grup bilgisi olmayan gruplar için varsayılan değerler ata.
    # Eğer is_onerous_group sütunu eksikse, False olarak atanır. Eğer onerous_loss_total sütunu eksikse, 0 olarak atanır. csm_opening ve csm_closing sütunları da eksikse, 0 olarak atanır.
    group_agg["is_onerous_group"] = group_agg["is_onerous_group"].fillna(False)
    group_agg["onerous_loss_total"] = group_agg["onerous_loss_total"].fillna(0)
    group_agg["csm_opening"] = group_agg["csm_opening"].fillna(0)
    group_agg["csm_closing"] = group_agg["csm_closing"].fillna(0)
    
    # Grup bazında onerous grup sayısını ve toplam loss miktarını logla
    logger.info(
        f"✓ IFRS17 groups assigned: {len(group_agg)} unique groups, "
        f"Onerous groups: {group_agg['is_onerous_group'].sum()}"
    )
    
    return group_agg # group_id, n_policies, total_sum_assured, is_onerous_group, onerous_loss_total gibi sütunlar içeren grup bazında aggregasyon sonucu döner.