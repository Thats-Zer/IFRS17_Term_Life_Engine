import logging

import numpy as np
import pandas as pd

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


def _prepare_adjusted_surrender(projection: pd.DataFrame) -> pd.DataFrame:
    projection = projection.copy()
    if "Surrender_Benefit" not in projection.columns:
        projection["adjusted_surrender_benefit"] = np.float32(0.0)
        return projection

    projection["adjusted_surrender_benefit"] = projection["Surrender_Benefit"].astype(np.float32)
    return projection


def calculate_risk_adjustment(
    projection: pd.DataFrame,
    config: ModelConfig,
) -> pd.DataFrame:
    """Calculate a simplified IFRS17 risk adjustment.

    The distribution uses the same liability-positive timing convention as BEL:
    closing outflows/recoveries are discounted with `discount_factor`, while
    opening premiums and reinsurance ceding are discounted with
    `discount_factor_opening`.
    """
    if config.coc_ratio < 0 or config.coc_ratio > 1:
        raise ValueError(f"coc_ratio [0, 1] olmali, {config.coc_ratio} verildi")
    if config.confidence_level < 0.5 or config.confidence_level > 1:
        raise ValueError(f"confidence_level [0.5, 1] olmali, {config.confidence_level} verildi")

    if "adjusted_surrender_benefit" not in projection.columns:
        projection = _prepare_adjusted_surrender(projection)

    required_cols = [
        "policy_id",
        "Year",
        "qx",
        "lapse_rate",
        "survival_ratio",
        "sum_assured",
        "adjusted_surrender_benefit",
        "Operating_Expenses",
        "Gross_Premium_Inflow",
        "discount_factor",
        "discount_factor_opening",
    ]
    missing = [c for c in required_cols if c not in projection.columns]
    if missing:
        raise ValueError(f"RA icin eksik sutunlar: {missing}")

    policy_id = projection["policy_id"].to_numpy(copy=False)
    qx = projection["qx"].to_numpy(dtype=np.float32, copy=False)
    lapse_rate = projection["lapse_rate"].to_numpy(dtype=np.float32, copy=False)
    survival_ratio = projection["survival_ratio"].to_numpy(dtype=np.float32, copy=False)
    sum_assured = projection["sum_assured"].to_numpy(dtype=np.float32, copy=False)
    adj_surrender = projection["adjusted_surrender_benefit"].to_numpy(dtype=np.float32, copy=False)
    op_exp = projection["Operating_Expenses"].to_numpy(dtype=np.float32, copy=False)
    gross_premium = projection["Gross_Premium_Inflow"].to_numpy(dtype=np.float32, copy=False)
    discount_factor = projection["discount_factor"].to_numpy(dtype=np.float32, copy=False)
    discount_factor_opening = projection["discount_factor_opening"].to_numpy(dtype=np.float32, copy=False)

    if "coverage_years" in projection.columns:
        in_force = (
            projection["Year"].to_numpy(copy=False)
            <= projection["coverage_years"].to_numpy(copy=False)
        ).astype(np.float32)
    else:
        in_force = np.ones(len(projection), dtype=np.float32)

    n_rows = len(projection)
    n_scenarios = int(config.n_risk_scenarios)
    base_seed = int(getattr(config, "random_seed", 0) or 0) % (2**32)

    unique_policies, policy_index = np.unique(policy_id, return_inverse=True)
    n_policies = unique_policies.size
    scenario_pv = np.empty((n_scenarios, n_policies), dtype=np.float32)
    tmp_policy_pv = np.zeros(n_policies, dtype=np.float32)

    re_rate = float(getattr(config, "reinsurance_cost_rate", 0.0) or 0.0)
    counterparty_pd = float(getattr(config, "counterparty_pd", 0.0) or 0.0)
    counterparty_lgd = float(getattr(config, "counterparty_lgd", 0.0) or 0.0)
    lapse_mortality_correlation = float(getattr(config, "lapse_mortality_correlation", 0.1) or 0.0)

    mort_sigma = float(getattr(config, "ra_mortality_sigma", 0.10) or 0.10)
    lapse_sigma = float(getattr(config, "ra_lapse_sigma", 0.15) or 0.15)
    expense_sigma = float(getattr(config, "ra_expense_sigma", 0.10) or 0.10)

    reinsurance_ceding = (gross_premium * re_rate).astype(np.float32)

    for s in range(n_scenarios):
        rng = np.random.default_rng((base_seed + s) % (2**32))
        mort_mult = rng.lognormal(mean=-0.5 * mort_sigma**2, sigma=mort_sigma, size=n_rows).astype(np.float32)
        lapse_mult = rng.lognormal(mean=-0.5 * lapse_sigma**2, sigma=lapse_sigma, size=n_rows).astype(np.float32)
        expense_mult = rng.lognormal(mean=-0.5 * expense_sigma**2, sigma=expense_sigma, size=n_rows).astype(np.float32)

        stochastic_lapse = np.clip(lapse_rate * lapse_mult, 0.0, 1.0).astype(np.float32)
        stochastic_qx = (
            qx
            * (1 - lapse_mortality_correlation * stochastic_lapse)
            * mort_mult
        ).clip(0.0, 1.0).astype(np.float32)

        death_benefits = (
            in_force
            * survival_ratio
            * stochastic_qx
            * sum_assured
        ).astype(np.float32)
        surrender = (adj_surrender * lapse_mult).astype(np.float32)
        expenses = (op_exp * expense_mult).astype(np.float32)
        reinsurance_recovery = (death_benefits * re_rate).astype(np.float32)

        if counterparty_pd > 0:
            default_event = rng.binomial(
                n=1,
                p=np.clip(counterparty_pd, 0.0, 1.0),
                size=n_rows,
            ).astype(np.float32)
            default_cost = reinsurance_recovery * default_event * counterparty_lgd
        else:
            default_cost = np.float32(0.0)

        pv_row = (
            (
                death_benefits
                + surrender
                + expenses
                + default_cost
                - reinsurance_recovery
            )
            * discount_factor
            + (reinsurance_ceding - gross_premium) * discount_factor_opening
        ).astype(np.float32)

        tmp_policy_pv.fill(0.0)
        np.add.at(tmp_policy_pv, policy_index, pv_row)
        scenario_pv[s, :] = tmp_policy_pv

    expected_pv = scenario_pv.mean(axis=0)
    tail_pv = np.quantile(scenario_pv, config.confidence_level, axis=0)
    ra_per_policy = np.maximum(tail_pv - expected_pv, 0.0) * float(config.coc_ratio)

    return pd.DataFrame(
        {
            "policy_id": unique_policies,
            "ra_per_policy": ra_per_policy.astype(np.float32),
        }
    )


def decompose_risk_adjustment(
    projection: pd.DataFrame,
    config: ModelConfig,
) -> pd.DataFrame:
    """Return total RA only.

    A reliable component attribution needs separate controlled runs by risk
    driver; fixed percentage splits would be misleading.
    """
    return calculate_risk_adjustment(projection, config)
