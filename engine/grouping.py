from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


def detect_onerous_groups(csm_result: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Add initial/subsequent onerous flags and positive loss amounts."""
    csm_result = csm_result.copy()

    csm_result["is_onerous_initial"] = csm_result.get("is_onerous", False)
    csm_closing_raw = csm_result.get("csm_closing_raw", csm_result.get("csm_closing", 0.0))
    csm_result["is_onerous_subsequently"] = (
        (csm_closing_raw < 0)
        & (~csm_result["is_onerous_initial"])
    )
    csm_result["is_onerous_group"] = (
        csm_result["is_onerous_initial"]
        | csm_result["is_onerous_subsequently"]
    )

    if "onerous_loss" in csm_result.columns:
        csm_result["onerous_loss_initial"] = np.where(
            csm_result["is_onerous_initial"],
            csm_result["onerous_loss"],
            0.0,
        ).astype(np.float32)
    else:
        csm_result["onerous_loss_initial"] = np.where(
            csm_result["is_onerous_initial"],
            csm_result.get("bel_opening", 0.0) + csm_result.get("ra_opening", 0.0),
            0.0,
        ).clip(min=0).astype(np.float32)

    csm_result["onerous_loss_subsequently"] = np.where(
        csm_result["is_onerous_subsequently"],
        (-pd.Series(csm_closing_raw)).clip(lower=0),
        0.0,
    ).astype(np.float32)
    csm_result["onerous_loss_total"] = (
        csm_result["onerous_loss_initial"]
        + csm_result["onerous_loss_subsequently"]
    ).astype(np.float32)

    logger.info(
        "Onerous flags assigned: initial=%s, subsequent=%s",
        int(csm_result["is_onerous_initial"].sum()),
        int(csm_result["is_onerous_subsequently"].sum()),
    )
    return csm_result


def group_by_business_nature(projection: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Assign a product nature bucket used as the IFRS 17 portfolio anchor."""
    projection = projection.copy()
    projection["business_nature"] = "Term Life"
    projection.loc[projection["coverage_years"] > 25, "business_nature"] = "Permanent Life"

    if "is_participating" in projection.columns:
        projection.loc[projection["is_participating"].fillna(False), "business_nature"] = "Participating"
    if "is_investment_linked" in projection.columns:
        projection.loc[projection["is_investment_linked"].fillna(False), "business_nature"] = "Investment Linked"

    return projection


def group_by_risk_characteristics(projection: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Assign policy-level mortality, lapse, and reinsurance risk buckets."""
    projection = projection.copy()

    avg_qx = projection.groupby("policy_id", sort=False)["qx"].mean()
    projection = projection.merge(avg_qx.to_frame("avg_qx"), left_on="policy_id", right_index=True, how="left")

    low_qx = float(getattr(config, "low_risk_qx_threshold", 0.01))
    medium_qx = float(getattr(config, "medium_risk_qx_threshold", 0.05))
    projection["risk_level"] = np.select(
        [
            projection["avg_qx"] <= low_qx,
            projection["avg_qx"] <= medium_qx,
        ],
        ["Low", "Medium"],
        default="High",
    )

    avg_lapse = projection.groupby("policy_id", sort=False)["lapse_rate"].mean().fillna(0.0)
    projection = projection.merge(avg_lapse.to_frame("avg_lapse"), left_on="policy_id", right_index=True, how="left")
    projection["lapse_risk"] = pd.cut(
        projection["avg_lapse"],
        bins=[-np.inf, 0.05, 0.15, np.inf],
        labels=["Low", "Medium", "High"],
    ).astype(str)

    projection["reinsurance_group"] = "Retained"
    if "is_reinsured" in projection.columns:
        projection.loc[projection["is_reinsured"].fillna(False).astype(bool), "reinsurance_group"] = "Ceded"

    projection["risk_group"] = (
        projection["risk_level"].astype(str)
        + "_"
        + projection["lapse_risk"].astype(str)
        + "_"
        + projection["reinsurance_group"].astype(str)
    )
    return projection


def assign_portfolio_boundary(projection: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Assign portfolio and annual cohort fields.

    IFRS 17 groups normally cannot include contracts issued more than one year
    apart. The sample engine has synthetic policies, so default issue year and
    portfolio are taken from config when the input data does not provide them.
    """
    projection = projection.copy()
    default_issue_year = int(getattr(config, "issue_year", 2026))
    default_portfolio = str(getattr(config, "portfolio_id", "TERM_LIFE"))

    if "issue_year" not in projection.columns:
        projection["issue_year"] = default_issue_year
    if "portfolio_id" not in projection.columns:
        projection["portfolio_id"] = default_portfolio

    projection["annual_cohort"] = projection["issue_year"].astype(int).astype(str)
    projection["portfolio_group"] = (
        projection["portfolio_id"].astype(str)
        + "_"
        + projection["business_nature"].astype(str)
    )
    return projection


def _profitability_bucket(csm_result: pd.DataFrame) -> pd.Series:
    if "is_onerous_group" in csm_result.columns:
        onerous = csm_result["is_onerous_group"].fillna(False).astype(bool)
    else:
        onerous = csm_result.get("is_onerous", False)

    csm_opening = csm_result.get("csm_opening", csm_result.get("initial_csm", 0.0))
    ra_opening = csm_result.get("ra_opening", 0.0)
    margin_ratio = csm_opening / (csm_opening.abs() + pd.Series(ra_opening).abs() + 1.0)

    return pd.Series(
        np.select(
            [onerous, margin_ratio > 0.25],
            ["Onerous", "No Significant Possibility of Becoming Onerous"],
            default="Other Profitable",
        ),
        index=csm_result.index,
    )


def assign_ifrs17_groups(
    csm_result: pd.DataFrame,
    projection: pd.DataFrame,
    config: ModelConfig,
) -> pd.DataFrame:
    """Assign IFRS 17-style groups and aggregate policy-level balances."""
    projection = group_by_business_nature(projection, config)
    projection = group_by_risk_characteristics(projection, config)
    projection = assign_portfolio_boundary(projection, config)
    csm_result = detect_onerous_groups(csm_result, config)
    csm_result["profitability_bucket"] = _profitability_bucket(csm_result)

    policy_level = projection[
        [
            "policy_id",
            "portfolio_group",
            "annual_cohort",
            "risk_group",
            "business_nature",
            "risk_level",
            "lapse_risk",
            "sum_assured",
            "coverage_years",
        ]
    ].drop_duplicates("policy_id")

    policy_group = policy_level.merge(
        csm_result[
            [
                "policy_id",
                "profitability_bucket",
                "is_onerous_group",
                "onerous_loss_total",
                "csm_opening",
                "csm_closing",
            ]
        ],
        on="policy_id",
        how="left",
    )
    policy_group["profitability_bucket"] = policy_group["profitability_bucket"].fillna("Unknown")
    policy_group["group_id"] = (
        policy_group["portfolio_group"].astype(str)
        + "_"
        + policy_group["annual_cohort"].astype(str)
        + "_"
        + policy_group["profitability_bucket"].astype(str)
        + "_"
        + policy_group["risk_group"].astype(str)
    )

    group_agg = (
        policy_group
        .groupby(
            [
                "group_id",
                "portfolio_group",
                "annual_cohort",
                "profitability_bucket",
                "risk_group",
                "business_nature",
                "risk_level",
                "lapse_risk",
            ],
            sort=False,
            as_index=False,
        )
        .agg(
            n_policies=("policy_id", "nunique"),
            total_sum_assured=("sum_assured", "sum"),
            coverage_years=("coverage_years", "mean"),
            is_onerous_group=("is_onerous_group", "any"),
            onerous_loss_total=("onerous_loss_total", "sum"),
            csm_opening=("csm_opening", "sum"),
            csm_closing=("csm_closing", "sum"),
        )
    )

    fill_zero = ["onerous_loss_total", "csm_opening", "csm_closing"]
    group_agg[fill_zero] = group_agg[fill_zero].fillna(0.0)
    group_agg["is_onerous_group"] = group_agg["is_onerous_group"].fillna(False).astype(bool)

    logger.info(
        "IFRS 17 groups assigned: %s groups, %s onerous groups",
        len(group_agg),
        int(group_agg["is_onerous_group"].sum()),
    )
    return group_agg
