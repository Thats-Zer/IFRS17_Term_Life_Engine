import pandas as pd

from model.config_model import ModelConfig


def calculate_annual_premiums(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Yıllık net ve brüt prim hesaplar.

    Net premium:
        PV(Expected Death Claims + Expenses) / PV(Premium Annuity)

    Gross premium:
        Net premium * premium_margin
    """

    projection = projection.copy()

    projection["unit_claim_pv"] = (
        projection["survival_ratio"]
        * projection["qx"]
        * projection["sum_assured"]
        * projection["discount_factor"]
    )

    projection["unit_expense_pv"] = (
        projection["survival_ratio"]
        * projection["Expected_Expenses"]
        * projection["discount_factor"]
    )

    projection["premium_annuity_pv"] = (
        projection["survival_ratio"]
        * projection["discount_factor_opening"]
    )

    premium_calc = (
        projection
        .groupby("policy_id")
        .agg({
            "unit_claim_pv": "sum",
            "unit_expense_pv": "sum",
            "premium_annuity_pv": "sum"
        })
        .reset_index()
    )

    premium_calc["net_annual_premium"] = (
        premium_calc["unit_claim_pv"]
        + premium_calc["unit_expense_pv"]
    ) / premium_calc["premium_annuity_pv"]

    premium_calc["gross_annual_premium"] = (
        premium_calc["net_annual_premium"]
        * config.premium_margin
    )

    projection = projection.merge(
        premium_calc[[
            "policy_id",
            "net_annual_premium",
            "gross_annual_premium"
        ]],
        on="policy_id",
        how="left"
    )

    return projection


def calculate_cashflows(
    projection: pd.DataFrame,
    config: ModelConfig
) -> pd.DataFrame:
    """
    Term-life için yıllık inflow / outflow hesaplar.
    """

    projection = projection.copy()

    # Expense projection
    projection["Expected_Expenses"] = (
        config.unit_cost
        * ((1 + config.inflation_rate) ** (projection["Year"] - 1))
    )

    # Premium calculation
    projection = calculate_annual_premiums(projection, config)

    # Gross premium inflow
    projection["Gross_Premium_Inflow"] = (
        projection["survival_ratio"]
        * projection["gross_annual_premium"]
    )

    # Net premium inflow
    projection["Net_Premium_Inflow"] = (
        projection["survival_ratio"]
        * projection["net_annual_premium"]
    )

    # Expected death claims
    projection["Expected_Death_Claims"] = (
        projection["survival_ratio"]
        * projection["qx"]
        * projection["sum_assured"]
    )

    # Expenses cash outflow
    projection["Expense_Outflow"] = (
        projection["survival_ratio"]
        * projection["Expected_Expenses"]
    )

    # Reinsurance recoverable
    projection["Reinsurance_Recoverable"] = (
        projection["Expected_Death_Claims"]
        * config.reinsurance_cost
    )

    # Net death claims after reinsurance
    projection["Net_Death_Claims"] = (
        projection["Expected_Death_Claims"]
        - projection["Reinsurance_Recoverable"]
    )

    # Counterparty default risk cost
    projection["Default_Risk_Cost"] = (
        projection["Reinsurance_Recoverable"]
        * config.counterparty_pd
        * config.counterparty_lgd
    )

    # Total outflow
    projection["Total_Cash_Outflow"] = (
        projection["Net_Death_Claims"]
        + projection["Expense_Outflow"]
        + projection["Default_Risk_Cost"]
    )

    # Net cash flow using gross premium
    projection["Net_Cash_Flow"] = (
        projection["Gross_Premium_Inflow"]
        - projection["Total_Cash_Outflow"]
    )

    # PV values
    projection["PV_Gross_Premium_Inflow"] = (
        projection["Gross_Premium_Inflow"]
        * projection["discount_factor"]
    )

    projection["PV_Total_Cash_Outflow"] = (
        projection["Total_Cash_Outflow"]
        * projection["discount_factor"]
    )

    projection["PV_Net_Cash_Flow"] = (
        projection["Net_Cash_Flow"]
        * projection["discount_factor"]
    )

    return projection