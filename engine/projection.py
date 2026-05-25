# engine/projection.py

from typing import Optional
from pathlib import Path
from functools import lru_cache
import logging

import numpy as np
import pandas as pd

from model.config_model import ModelConfig
from engine.curves import get_exponential_lapse

logger = logging.getLogger(__name__)


# ==================================================
# MORTALITY TABLE LOADING
# ==================================================


@lru_cache(maxsize=1)
def load_mortality_table(file_path: str) -> pd.DataFrame:
    """
    Mortalite tablosunu CSV'den yükle ve hazırla.

    CSV Beklenen Format:
    - Sütunlar: age (yaş), qx (mortalite olasılığı)
    - qx değerleri [0, 1] aralığında olmalı
    - Encoding: UTF-8
    - Separator: semicolon (;)

    Args:
        file_path: Mortalite CSV dosyasının yolu

    Returns:
        pd.DataFrame: age (int32) ve qx (float32) sütunları içeren DataFrame

    Raises:
        FileNotFoundError: Dosya bulunamazsa
        ValueError: CSV format hatalıysa veya veri geçersizse
    """
    file_path = str(Path(file_path).resolve())
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Mortalite tablosu bulunamadı: {file_path}")

    logger.info(f"Mortalite tablosu yükleniyor: {file_path}")

    try:
        mortality_table = pd.read_csv(path, sep=";", encoding="utf-8")
    except Exception as e:
        raise ValueError(f"CSV okuma hatası ({file_path}): {e}")

    # Normalize column names for case-insensitive CSV input.
    mortality_table.columns = mortality_table.columns.str.lower().str.strip()

    # Required age column.
    if "age" not in mortality_table.columns:
        raise ValueError(
            f"CSV'de 'age' sütunu gerekli, bulunan sütunlar: {mortality_table.columns.tolist()}"
        )

    # Mortality rate column aliases.
    rate_col = None
    for col in ["qx", "mortality_rate", "rate", "mortality_age"]:
        if col in mortality_table.columns:
            rate_col = col
            break

    if rate_col is None:
        raise ValueError(
            f"CSV'de mortalite oran sütunu gerekli (qx, mortality_rate, rate), bulunan: {mortality_table.columns.tolist()}"
        )

    # Standardize the mortality rate column name.
    mortality_table = mortality_table.rename(columns={rate_col: "qx"})

    # Coerce input types.
    try:
        mortality_table["age"] = mortality_table["age"].astype(np.int32)
        mortality_table["qx"] = mortality_table["qx"].astype(np.float32)
    except Exception as e:
        raise ValueError(f"Veri tipi dönüştürme hatası: {e}")

    # qx must be a probability.
    if (mortality_table["qx"] < 0).any() or (mortality_table["qx"] > 1).any():
        invalid_rows = mortality_table[(mortality_table["qx"] < 0) | (mortality_table["qx"] > 1)]
        raise ValueError(f"qx değerleri [0, 1] aralığında olmalı. Hatalı satırlar:\n{invalid_rows}")

    # age must be non-negative.
    if (mortality_table["age"] < 0).any():
        raise ValueError("age değerleri >= 0 olmalı")

    # Keep interpolation inputs sorted.
    mortality_table = mortality_table.sort_values("age").reset_index(drop=True)

    # Reject incomplete mortality rows.
    if mortality_table.isna().any().any():
        raise ValueError(
            f"CSV'de NaN değer bulundu: {mortality_table[mortality_table.isna().any(axis=1)]}"
        )

    logger.info(
        f"✓ Mortalite tablosu yüklendi: {len(mortality_table)} satır, "
        f"yaşlar [{mortality_table['age'].min()}-{mortality_table['age'].max()}]"
    )

    return mortality_table


def get_mortality_rate(age: int, mortality_table: pd.DataFrame) -> float:
    """
    Belirli bir yaş için mortalite oranını al (interpolasyon ile).

    Edge cases:
    - age < min_age: en küçük yaş oranını döndür
    - age > max_age: en büyük yaş oranını döndür
    - Exact match varsa: o oranı döndür
    - Araded: lineer interpolasyon

    Args:
        age: Yaş (tamsayı)
        mortality_table: Mortalite tablosu (age, qx sütunları)

    Returns:
        float: qx mortalite oranı (float32)

    Raises:
        ValueError: age geçersizse
    """
    if age < 0:
        raise ValueError(f"age >= 0 olmalı, {age} verildi")

    min_age = mortality_table["age"].min()
    max_age = mortality_table["age"].max()

    # Edge case: below the table range.
    if age < min_age:
        logger.debug(f"⚠️ age ({age}) < min_table_age ({min_age}), en küçük oranı kullan")
        return mortality_table["qx"].iloc[0]

    # Edge case: above the table range.
    if age > max_age:
        logger.debug(f"⚠️ age ({age}) > max_table_age ({max_age}), en büyük oranı kullan")
        return mortality_table["qx"].iloc[-1]

    # Exact match
    match = mortality_table[mortality_table["age"] == age]
    if not match.empty:
        return match["qx"].iloc[0]

    # Linear interpolation between available table ages.
    lower_row = mortality_table[mortality_table["age"] <= age].iloc[-1]
    upper_row = mortality_table[mortality_table["age"] > age].iloc[0]

    age_range = upper_row["age"] - lower_row["age"]
    qx_range = upper_row["qx"] - lower_row["qx"]
    weight = (age - lower_row["age"]) / age_range

    qx_interpolated = lower_row["qx"] + weight * qx_range

    return float(np.float32(qx_interpolated))


# ==================================================
# MASTER DATA
# ==================================================


def validate_policy_data(policy_data: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """
    Validate externally supplied policy data for sample runs.

    Required columns:
    - policy_id
    - issue_age
    - sum_assured
    - coverage_years

    Optional columns:
    - issue_year (defaults to config.issue_year)
    - portfolio_id (defaults to config.portfolio_id)
    """
    if policy_data is None or policy_data.empty:
        raise ValueError("Sample policy data is empty")

    df = policy_data.copy()
    df.columns = df.columns.str.strip()

    required = {"policy_id", "issue_age", "sum_assured", "coverage_years"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Sample policy data missing required columns: {sorted(missing)}")

    if df["policy_id"].isna().any():
        raise ValueError("policy_id contains null values")

    if df["policy_id"].duplicated().any():
        dupes = df[df["policy_id"].duplicated()]["policy_id"].tolist()
        raise ValueError(f"Duplicate policy_id values found: {dupes}")

    df["policy_id"] = df["policy_id"].astype(np.int32)
    df["issue_age"] = df["issue_age"].astype(np.int16)
    df["coverage_years"] = df["coverage_years"].astype(np.int16)
    df["sum_assured"] = df["sum_assured"].astype(np.float32)

    if (df["sum_assured"] < 0).any():
        raise ValueError("sum_assured must be non-negative")

    min_age = int(getattr(config, "min_issue_age", 0))
    max_age = int(getattr(config, "max_issue_age", 200))
    if (df["issue_age"] < min_age).any() or (df["issue_age"] > max_age).any():
        raise ValueError("issue_age out of configured range")

    if (df["coverage_years"] <= 0).any():
        raise ValueError("coverage_years must be positive")

    if "issue_year" not in df.columns:
        df["issue_year"] = int(getattr(config, "issue_year", 2026))
    if "portfolio_id" not in df.columns:
        df["portfolio_id"] = str(getattr(config, "portfolio_id", "TERM_LIFE"))

    if df.isna().any().any():
        raise ValueError("Sample policy data contains NaN values")

    return df


def load_policy_data(file_path: str, config: ModelConfig) -> pd.DataFrame:
    """
    Load a sample policy dataset from CSV for inspection and lineage demos.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Sample policy file not found: {file_path}")

    policy_data = pd.read_csv(path, encoding="utf-8")
    return validate_policy_data(policy_data, config)


def create_master_data(config: ModelConfig) -> pd.DataFrame:
    """
    Ana poliçe verilerini oluştur.

    Açıklama:
    - policy_id: Poliçe kimliği (1'den n_policies'e)
    - issue_age: Poliçe başlatıldığı yaş (min-max arasında random)
    - sum_assured: Teminat tutarı (lognormal dağılım)

    Args:
        config: ModelConfig

    Returns:
        pd.DataFrame: Master poliçe verileri (optimized dtypes)
    """
    np.random.seed(config.random_seed)

    sum_assured_sigma = float(getattr(config, "sum_assured_sigma", 0.8) or 0.0)
    sum_assured_mu = np.log(config.target_avg_sum_assured) - 0.5 * (sum_assured_sigma**2)

    master_data = pd.DataFrame(
        {
            "policy_id": np.arange(1, config.n_policies + 1, dtype=np.int32),
            "issue_age": np.random.randint(
                config.min_issue_age,
                config.max_issue_age + 1,
                size=config.n_policies,
                dtype=np.int16,
            ),
            "sum_assured": np.random.lognormal(
                mean=sum_assured_mu, sigma=sum_assured_sigma, size=config.n_policies
            ).astype(np.float32),
            "coverage_years": np.full(
                config.n_policies,
                int(getattr(config, "coverage_years", config.projection_years)),
                dtype=np.int16,
            ),
            "issue_year": np.full(
                config.n_policies, int(getattr(config, "issue_year", 2026)), dtype=np.int16
            ),
            "portfolio_id": np.full(
                config.n_policies, str(getattr(config, "portfolio_id", "TERM_LIFE"))
            ),
        }
    )

    logger.info(f"✓ Master data oluşturuldu: {len(master_data)} poliçe")

    return master_data


# ==================================================
# YEAR-AGE GRID
# ==================================================


def create_year_age_grid(master_data: pd.DataFrame, projection_years: int) -> pd.DataFrame:
    """
    Her poliçe ve yıl kombinasyonu için yaş-yıl grid'i oluştur.

    Mantık:
    - Poliçe sayısı × Yıl sayısı satır
    - Her satırda: policy_id, Year, current_age, issue_age
    - in_force: poliçe teminat süresi içinde mi

    Args:
        master_data: Master poliçe verisi
        projection_years: Proje periyodu (yıl)

    Returns:
        pd.DataFrame: Grid tablosu (optimized dtypes)
    """
    years = np.arange(1, projection_years + 1, dtype=np.int32)

    # Cartesian product of policies and projection years.
    grid = pd.DataFrame(
        {
            "policy_id": np.repeat(master_data["policy_id"].values, len(years)),
            "Year": np.tile(years, len(master_data)),
        }
    )

    # Attach policy attributes.
    grid = grid.merge(
        master_data[["policy_id", "issue_age", "coverage_years", "issue_year", "portfolio_id"]],
        on="policy_id",
        how="left",
    )

    # Current age in each policy year.
    grid["current_age"] = (
        grid["issue_age"].astype(np.int16) + grid["Year"].astype(np.int16) - 1
    ).astype(np.int16)

    # Keep projection dtypes compact.
    grid = grid.astype(
        {
            "policy_id": np.int32,
            "Year": np.int32,
            "current_age": np.int16,
            "issue_age": np.int16,
            "coverage_years": np.int16,
            "issue_year": np.int16,
        }
    )

    # Coverage-period in-force flag.
    grid["in_force"] = (grid["Year"] <= grid["coverage_years"]).astype(bool)

    # Defensive NaN handling for merged policy attributes.
    if grid.isna().any().any():
        nan_count = grid.isna().sum().sum()
        logger.warning(f"⚠️ Grid'de {nan_count} NaN değer bulundu, dolduruldu")
        grid = grid.fillna(0)

    logger.info(f"✓ Yaş-Yıl grid oluşturuldu: {len(grid)} satır")

    return grid


# ==================================================
# FINANCIAL DATA
# ==================================================


def attach_financial_data(grid: pd.DataFrame, master_data: pd.DataFrame) -> pd.DataFrame:
    """
    Grid'e finansal veri ekle (sum_assured).

    Args:
        grid: Yaş-yıl grid'i
        master_data: Master poliçe verisi

    Returns:
        pd.DataFrame: Finansal veriler eklenmiş grid
    """
    grid = grid.merge(master_data[["policy_id", "sum_assured"]], on="policy_id", how="left")

    # NaN handling
    grid["sum_assured"] = grid["sum_assured"].fillna(0.0).astype(np.float32)

    return grid


# ==================================================
# MORTALITY + LAPSE
# ==================================================


def attach_mortality_and_lapse(
    projection: pd.DataFrame, config: ModelConfig, mortality_table: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Projection'a mortalite ve lapse verileri ekle.

    Mortalite:
    - Tablodan age'e göre qx oranı (eğer tablo sağlanmışsa)
    - Fallback: formül tabanlı qx = base + age_factor × yaş
    - Interpolasyon: exact age yoksa lineer interpolasyon
    - Edge case: age < min veya age > max tablodaki ekstrem values

    Lapse:
    - get_exponential_lapse ile hesapla
    - Year'a göre

    Survival:
    - Kümülatif çarpım: S(t) = ∏(1 - qx - lapse) for i=1 to t

    Args:
        projection: Projection tablosu
        config: ModelConfig
        mortality_table: (Opsiyonel) Önceden yüklü mortalite tablosu

    Returns:
        pd.DataFrame: Mortalite, lapse, survival eklenmiş

    Raises:
        ValueError: Mortality table format hatalıysa
    """
    projection = projection.copy()

    # Load the configured mortality table when one was not supplied.
    if mortality_table is None and config.use_mortality_table:
        mortality_table = load_mortality_table(config.mortality_table_path)

    # ===============================================
    # MORTALITY RATE
    # ===============================================

    mortality_mult = float(getattr(config, "mortality_shock_multiplier", 1.0) or 1.0)
    mortality_add = float(getattr(config, "mortality_shock", 0.0) or 0.0)

    if mortality_table is not None:
        # Vectorized table lookup with numpy.interp and out-of-range clamping.
        mt = mortality_table.sort_values("age")
        ages = mt["age"].to_numpy(dtype=np.float32, copy=False)
        qx_vals = mt["qx"].to_numpy(dtype=np.float32, copy=False)
        if ages.size == 0:
            raise ValueError("Mortality table is empty")

        proj_age = projection["current_age"].to_numpy(dtype=np.float32, copy=False)
        qx_interp = np.interp(
            proj_age,
            ages,
            qx_vals,
            left=float(qx_vals[0]),
            right=float(qx_vals[-1]),
        )
        projection["qx"] = qx_interp.astype(np.float32)
        logger.debug("✓ Mortalite oranları tablodan alındı")

    else:
        # Formula-based fallback.
        projection["qx"] = (
            config.base_mort_rate
            + (projection["current_age"] - config.min_issue_age) * config.mortality_age_factor
        ).astype(np.float32)
        logger.debug("✓ Mortalite oranları formülden hesaplandı")

    # Apply mortality multiplier and additive shocks in all paths.
    projection["qx"] = (
        (projection["qx"] * mortality_mult + mortality_add).clip(0, 1).astype(np.float32)
    )

    # ===============================================
    # LAPSE RATE
    # ===============================================

    lapse_mult = float(getattr(config, "lapse_initial_rate_multiplier", 1.0) or 1.0)
    lapse_initial = float(config.lapse_base_rate) * lapse_mult
    lapse_initial = float(np.clip(lapse_initial, 0.0, 1.0))

    lapse_array = get_exponential_lapse(
        projection["Year"].values, initial_rate=lapse_initial, decay=config.lapse_decay
    )
    projection["lapse_rate"] = lapse_array

    # ===============================================
    # SURVIVAL PROBABILITY
    # ===============================================

    # Within-year survival under a simple competing decrements assumption:
    #   survive_t = (1 - qx_t) * (1 - lapse_t)
    # This is more coherent than a direct 1 - qx - lapse approximation.
    projection["survival_multiplier"] = (
        ((1 - projection["qx"]) * (1 - projection["lapse_rate"])).clip(0, 1).astype(np.float32)
    )

    # Opening survival: S_open(t) = product of prior-year survival multipliers.
    # Thus the Year=t survival_ratio represents beginning-of-year in-force exposure.
    projection = projection.sort_values(["policy_id", "Year"]).reset_index(drop=True)

    g = projection.groupby("policy_id", sort=False)
    projection["survival_multiplier_opening"] = (
        g["survival_multiplier"].shift(1).fillna(1.0).astype(np.float32)
    )
    projection["survival_ratio"] = (
        g["survival_multiplier_opening"].cumprod().astype(np.float32).reset_index(drop=True)
    )

    # NaN handling
    nan_cols = ["qx", "lapse_rate", "survival_ratio"]
    for col in nan_cols:
        nan_count = projection[col].isna().sum()
        if nan_count > 0:
            logger.warning(f"⚠️ {col}'de {nan_count} NaN değer, dolduruldu")
            projection[col] = projection[col].fillna(0.0)

    logger.info("✓ Mortalite, lapse ve survival verileri eklendi")

    return projection


# ==================================================
# PROJECTION TABLE
# ==================================================


def create_projection_table(
    master_data: pd.DataFrame, config: ModelConfig, mortality_table: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Tam projection tablosu oluştur (modüler yapı).

    Adımlar:
    1. create_year_age_grid: Yaş-yıl kombinasyonları
    2. attach_financial_data: Teminat tutarı ekle
    3. attach_mortality_and_lapse: Mortalite, lapse, survival ekle

    Args:
        master_data: Master poliçe verisi
        config: ModelConfig
        mortality_table: (Opsiyonel) Mortalite tablosu

    Returns:
        pd.DataFrame: Tam projection tablosu

    Raises:
        ValueError: Veriler geçersizse
    """
    logger.info("Projection tablosu oluşturuluyor...")

    # Step 1: Build policy-year grid.
    projection = create_year_age_grid(master_data, config.projection_years)

    # Step 2: Attach financial attributes.
    projection = attach_financial_data(projection, master_data)

    # Step 3: Attach mortality, lapse, and survival assumptions.
    projection = attach_mortality_and_lapse(projection, config, mortality_table)

    logger.info(
        f"✓ Projection tablosu oluşturuldu: {len(projection)} satır, "
        f"{len(projection.columns)} sütun"
    )

    return projection
