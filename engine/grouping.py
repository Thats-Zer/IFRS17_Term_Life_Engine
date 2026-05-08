from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# ONEROUS GROUP DETECTION
# ==================================================

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
    
    csm_result = csm_result.copy()
    
    # ==================================================
    # ONEROUS GROUP FLAGS
    # ==================================================
    
    # Initial onerous (CSM opening < 0)
    csm_result["is_onerous_initial"] = csm_result.get("is_onerous", False)
    
    # Subsequently onerous (CSM closing < 0, opening was not)
    csm_result["is_onerous_subsequently"] = (
        (csm_result.get("csm_closing", 0) < 0)
        & (~csm_result["is_onerous_initial"])
    )
    
    csm_result["is_onerous_group"] = (
        csm_result["is_onerous_initial"]
        | csm_result["is_onerous_subsequently"]
    )
    
    # ==================================================
    # LOSS CALCULATION
    # ==================================================
    
    # Initial onerous loss
    csm_result["onerous_loss_initial"] = np.where(
        csm_result["is_onerous_initial"],
        -(csm_result.get("bel_opening", 0) + csm_result.get("ra_opening", 0) - csm_result.get("pv_premiums", 0)),
        0
    ).astype(np.float32)
    
    # Subsequently onerous loss
    csm_result["onerous_loss_subsequently"] = np.where(
        csm_result["is_onerous_subsequently"],
        csm_result.get("csm_closing", 0),
        0
    )
    csm_result["onerous_loss_subsequently"] = pd.Series(csm_result["onerous_loss_subsequently"]).clip(upper=0).astype(np.float32)
    
    # Total onerous loss
    csm_result["onerous_loss_total"] = (
        csm_result["onerous_loss_initial"]
        + csm_result["onerous_loss_subsequently"]
    ).astype(np.float32)
    
    logger.info(
        f"✓ Onerous grupos detected: "
        f"Initial={csm_result['is_onerous_initial'].sum()}, "
        f"Subsequently={csm_result['is_onerous_subsequently'].sum()}"
    )
    
    return csm_result


# ==================================================
# BUSINESS NATURE GROUPING
# ==================================================

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
    
    projection = projection.copy()
    
    # ==================================================
    # BUSINESS NATURE ASSIGNMENT
    # ==================================================
    
    projection["business_nature"] = "Term Life"  # Default
    
    # Longer term poliçeler
    projection.loc[
        projection["coverage_years"] > 25,
        "business_nature"
    ] = "Permanent Life"
    
    # Participating ürünler (if applicable)
    if "is_participating" in projection.columns:
        projection.loc[
            projection["is_participating"],
            "business_nature"
        ] = "Participating"
    
    logger.debug(f"✓ Grouped by business nature: {projection['business_nature'].unique()}")
    
    return projection


# ==================================================
# RISK GROUP ASSIGNMENT
# ==================================================

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
    
    projection = projection.copy()
    
    # ==================================================
    # RISK LEVEL
    # ==================================================
    
    avg_qx = projection.groupby("policy_id")["qx"].mean()
    
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
    
    avg_lapse = projection.groupby("policy_id")["lapse_rate"].mean()
    
    projection = projection.merge(
        avg_lapse.to_frame("avg_lapse"),
        left_on="policy_id",
        right_index=True,
        how="left"
    )
    
    projection["lapse_risk"] = pd.cut(
        projection["avg_lapse"],
        bins=[0, 0.05, 0.15, 1.0],
        labels=["Low", "Medium", "High"]
    )
    
    # ==================================================
    # REINSURANCE GROUP
    # ==================================================

    projection["reinsurance_group"] = "Retained"
    if "is_reinsured" in projection.columns:
        projection.loc[projection["is_reinsured"].fillna(False).astype(bool), "reinsurance_group"] = "Ceded"

    # ==================================================
    # RISK GROUP
    # ==================================================

    projection["risk_group"] = "DEFAULT"
    if getattr(config, "use_risk_grouping", False) and "some_column" in projection.columns:
        mask = projection["some_column"].notna()
        projection.loc[mask, "risk_group"] = "GROUP_1"

    logger.debug(f"✓ Grouped by risk characteristics")

    return projection


# ==================================================
# GROUP LEVEL AGGREGATION
# ==================================================

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
    
    # Business nature grouping
    projection = group_by_business_nature(projection, config)
    
    # Risk grouping
    projection = group_by_risk_characteristics(projection, config)
    
    # Onerous grouping
    csm_result = detect_onerous_groups(csm_result, config)
    
    # ==================================================
    # GROUP KEYS
    # ==================================================
    
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
    
    # Onerous flag merge
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
    
    group_agg = group_agg.merge(csm_group, on="group_id", how="left")
    
    logger.info(
        f"✓ IFRS17 groups assigned: {len(group_agg)} unique groups, "
        f"Onerous groups: {group_agg['is_onerous_group'].sum()}"
    )
    
    return group_agg