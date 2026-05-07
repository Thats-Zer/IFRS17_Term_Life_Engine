import numpy as np
import pandas as pd

from model.config_model import ModelConfig
from engine.curves import get_exponential_lapse


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


def create_projection_table(
    master: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    projection = pd.DataFrame({
        "policy_id": np.repeat(master["policy_id"].values, config.projection_years),
        "Year": np.tile(
            np.arange(1, config.projection_years + 1),
            config.n_policies
        )
    })

    projection = projection.merge(master, on="policy_id", how="left")
    projection["current_age"] = projection["issue_age"] + projection["Year"] - 1

    return projection


def attach_mortality_and_lapse(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    projection = projection.copy()

    projection["base_qx"] = (
        config.base_mortality_rate
        + (projection["current_age"] - config.min_issue_age)
        * config.mortality_age_increment
    )

    projection["qx"] = (
        projection["base_qx"] + config.mortality_shock
    ).clip(0, 1)

    projection["lapse_rate"] = get_exponential_lapse(
        projection["Year"].values,
        config.lapse_initial_rate,
        config.lapse_decay
    )

    projection["survival_multiplier"] = (
        1 - projection["qx"] - projection["lapse_rate"]
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