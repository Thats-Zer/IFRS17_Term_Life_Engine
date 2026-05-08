import pandas as pd

from model.config_model import ModelConfig


def calculate_ra(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:

    projection = projection.copy()

    projection["S2_Capital"] = (
        projection["Expected_Death_Claims"]
        * config.s2_margin
    )

    projection["OpRisk_Capital"] = (
        projection["Gross_Premium_Inflow"]
        + projection["Total_Cash_Outflow"]
    ) * config.op_risk_ratio

    projection["Total_SCR"] = (
        projection["S2_Capital"]
        + projection["OpRisk_Capital"]
    )

    projection["CoC_Yearly"] = (
        projection["Total_SCR"]
        * config.coc_ratio
    )

    projection["PV_CoC_Yearly"] = (
        projection["CoC_Yearly"]
        * projection["discount_factor"]
    )

    ra_result = (
        projection
        .groupby("policy_id")
        .agg({
            "PV_CoC_Yearly": "sum",
            "S2_Capital": "sum",
            "OpRisk_Capital": "sum",
            "Total_SCR": "sum"
        })
        .reset_index()
    )

    ra_result = ra_result.rename(
        columns={"PV_CoC_Yearly": "RA"}
    )

    return projection, ra_result