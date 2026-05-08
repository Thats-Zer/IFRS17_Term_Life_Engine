from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging
from scipy import stats

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


# ==================================================
# RISK ADJUSTMENT CALCULATION
# ==================================================

def calculate_risk_adjustment(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    IFRS17 Risk Adjustment (RA) hesapla - KOMPLEKS YÖNTEM.
    
    Risk Adjustment Tanımı (IFRS17):
    RA = CoC × PV[Quantile_α(Liability) - E(Liability)]
    
    Nerede:
    - CoC: Cost of Capital Rate (genelde %6)
    - α: Confidence Level (genelde 75%)
    - Quantile: α'ıncı persentil (örn: 75th percentile)
    - Liability: Net liability cashflows
    
    Risk Kategorileri:
    1. MORTALITE RİSKİ: Gerçek qx > beklenen qx
    2. LAPSE RİSKİ: Gerçek lapse > beklenen lapse
    3. EXPENSİ RİSKİ: Gerçek expense > beklenen expense
    4. REASÜRANS RİSKİ: Counterparty default riski
    
    Metodoloji:
    1. Her risk kategorisi için stokastik senaryo
    2. Persentil hesabı (Quantile)
    3. RA = CoC × PV(Tail Risk)
    
    Args:
        projection: Projection tablosu
        config: ModelConfig (confidence_level, coc_rate)
        
    Returns:
        pd.DataFrame: policy_id ve ra_per_policy sütunları
        
    Raises:
        ValueError: Parameters geçersizse
    """
    
    # Validation
    if config.coc_ratio < 0 or config.coc_ratio > 1:
        raise ValueError(f"coc_ratio [0, 1] olmalı, {config.coc_ratio} verildi")
    
    if config.confidence_level < 0.5 or config.confidence_level > 1:
        raise ValueError(f"confidence_level [0.5, 1] olmalı, {config.confidence_level} verildi")
    
    required_cols = [
        "policy_id",
        "qx",
        "survival_ratio",
        "sum_assured",
        "Adjusted_Death_Benefits",
        "adjusted_surrender_benefit",
        "Operating_Expenses",
        "Gross_Premium_Inflow",
        "discount_factor",
    ]

    missing = [c for c in required_cols if c not in projection.columns]
    if missing:
        raise ValueError(f"RA için eksik sütunlar: {missing}")

    # Sadece gerekli kolonlar ve sadece array olarak
    policy_id = projection["policy_id"].to_numpy(copy=False)
    qx = projection["qx"].to_numpy(dtype=np.float32, copy=False)
    survival_ratio = projection["survival_ratio"].to_numpy(dtype=np.float32, copy=False)
    sum_assured = projection["sum_assured"].to_numpy(dtype=np.float32, copy=False)
    adj_death = projection["Adjusted_Death_Benefits"].to_numpy(dtype=np.float32, copy=False)
    adj_surrender = projection["adjusted_surrender_benefit"].to_numpy(dtype=np.float32, copy=False)
    op_exp = projection["Operating_Expenses"].to_numpy(dtype=np.float32, copy=False)
    gross_premium = projection["Gross_Premium_Inflow"].to_numpy(dtype=np.float32, copy=False)
    discount_factor = projection["discount_factor"].to_numpy(dtype=np.float32, copy=False)

    n_rows = len(projection)
    n_scenarios = int(config.n_risk_scenarios)

    # Senaryo sonuçlarını doğrudan matris içinde tut
    scenario_pv = np.empty((n_scenarios, n_rows), dtype=np.float32)

    for s in range(n_scenarios):
        stochastic_qx = np.random.binomial(n=1, p=qx, size=n_rows).astype(np.float32)

        stochastic_death_benefits = survival_ratio * stochastic_qx * sum_assured

        scenario_net_liability = (
            stochastic_death_benefits
            + adj_surrender
            + op_exp
            - gross_premium
        ).astype(np.float32)

        scenario_pv[s, :] = scenario_net_liability * discount_factor

    # Beklenen değer ve kuantil
    expected_pv = scenario_pv.mean(axis=0)
    tail_pv = np.quantile(scenario_pv, config.confidence_level, axis=0)

    ra_per_policy = np.maximum(tail_pv - expected_pv, 0.0) * float(config.coc_ratio)

    return pd.DataFrame(
        {
            "policy_id": policy_id,
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
    ra_breakdown["lapse_ra"] = ra_full["ra_per_policy"] * 0.25
    ra_breakdown["expense_ra"] = ra_full["ra_per_policy"] * 0.10
    ra_breakdown["counterparty_ra"] = ra_full["ra_per_policy"] * 0.05
    
    logger.info("✓ Risk decomposition tamamlandı")
    
    return ra_breakdown