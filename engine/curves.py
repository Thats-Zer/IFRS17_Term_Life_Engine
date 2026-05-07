import numpy as np
import pandas as pd
from model.config_model import ModelConfig


def tax_adjusted_discount_factor(config: ModelConfig) -> float:
    """
    Vergi sonrası iskonto faktörü.

    v = 1 / (1 + i * (1 - tax_rate))
    """
    return 1 / (1 + config.discount_rate * (1 - config.tax_rate))


def create_discount_curve(config: ModelConfig) -> pd.DataFrame:
    """
    Tek oranlı iskonto eğrisi üretir.
    İleride yield curve bu fonksiyonun içine alınabilir.
    """
    years = np.arange(1, config.projection_years + 1)
    v = tax_adjusted_discount_factor(config)

    return pd.DataFrame({
        "Year": years,
        "discount_factor": v ** years,
        "discount_factor_opening": v ** (years - 1)
    })


def get_exponential_lapse(
    years: np.ndarray,
    initial_rate: float,
    decay: float
) -> np.ndarray:
    """
    Üssel azalan lapse oranı.

    lapse_t = l0 * exp(-k * (t - 1))
    """
    lapse = initial_rate * np.exp(-decay * (years - 1))
    return np.clip(lapse, 0, 1)