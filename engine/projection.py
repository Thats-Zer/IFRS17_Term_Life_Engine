# engine/projection.py

from pathlib import Path

import numpy as np
import pandas as pd

from model.config_model import ModelConfig
from engine.curves import get_exponential_lapse


# ==================================================
# MORTALITY TABLE LOADING
# ==================================================

def load_mortality_table(path: str) -> pd.DataFrame | None:
    mortality_path = Path(path)

    if not mortality_path.exists():
        print(f"⚠ Mortality table not found: {mortality_path}")
        return None

    separators = [";", ",", "\t"]

    for sep in separators:
        try:
            df = pd.read_csv(mortality_path, sep=sep)

            if {"age", "qx"}.issubset(df.columns):

                df = df[["age", "qx"]].copy()

                df["age"] = pd.to_numeric(df["age"], errors="coerce")
                df["qx"] = pd.to_numeric(df["qx"], errors="coerce")

                df = df.dropna()

                df["age"] = df["age"].astype(int)

                df["qx"] = df["qx"].clip(0, 1)

                return df.rename(columns={"age": "mortality_age"})

        except Exception:
            continue

    raise ValueError(
        "Mortality table could not be parsed."
    )


# ==================================================
# MASTER DATA
# ==================================================

def create_master_data(config: ModelConfig) -> pd.DataFrame:

    np.random.seed(config.random_seed)

    return pd.DataFrame({
        "policy_id": np.arange(1, config.n_policies + 1),

        "issue_age": np.random.randint(
            config.min_issue_age,
            config.max_issue_age,
            size=config.n_policies
        ),

        "sum_assured": np.random.lognormal(
            mean=np.log(config.target_avg_sum_assured),
            sigma=0.8,
            size=config.n_policies
        )
    })


# ==================================================
# PROJECTION TABLE
# ==================================================

def create_projection_table(
    master: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:

    projection = pd.DataFrame({
        "policy_id": np.repeat(
            master["policy_id"].values,
            config.projection_years
        ),

        "Year": np.tile(
            np.arange(1, config.projection_years + 1),
            config.n_policies
        )
    })

    projection = projection.merge(
        master,
        on="policy_id",
        how="left"
    )

    projection["current_age"] = (
        projection["issue_age"]
        + projection["Year"]
        - 1
    )

    return projection


# ==================================================
# MORTALITY + LAPSE
# ==================================================

def attach_mortality_and_lapse(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:

    projection = projection.copy()

    mortality_table = None

    if config.use_mortality_table:
        mortality_table = load_mortality_table(
            config.mortality_table_path
        )

    # ==================================================
    # USE MORTALITY TABLE
    # ==================================================

    if mortality_table is not None:

        projection = projection.merge(
            mortality_table,
            left_on="current_age",
            right_on="mortality_age",
            how="left"
        )

        projection["base_qx"] = projection["qx"].fillna(
            config.base_mortality_rate
            + (
                projection["current_age"]
                - config.min_issue_age
            )
            * config.mortality_age_increment
        )

    # ==================================================
    # FALLBACK FORMULA
    # ==================================================

    else:

        projection["base_qx"] = (
            config.base_mortality_rate
            + (
                projection["current_age"]
                - config.min_issue_age
            )
            * config.mortality_age_increment
        )

    # ==================================================
    # FINAL QX
    # ==================================================

    projection["qx"] = (
        projection["base_qx"]
        + config.mortality_shock
    ).clip(0, 1)

    # ==================================================
    # LAPSE
    # ==================================================

    projection["lapse_rate"] = get_exponential_lapse(
        projection["Year"].values,
        config.lapse_initial_rate,
        config.lapse_decay
    )

    # ==================================================
    # SURVIVAL
    # ==================================================

    projection["survival_multiplier"] = (
        1
        - projection["qx"]
        - projection["lapse_rate"]
    ).clip(0, 1)

    projection["survival_ratio"] = (
        projection
        .groupby("policy_id")["survival_multiplier"]
        .shift(1)
        .fillna(1)
    )

    projection["survival_ratio"] = (
        projection
        .groupby("policy_id")["survival_ratio"]
        .cumprod()
    )

    return projection