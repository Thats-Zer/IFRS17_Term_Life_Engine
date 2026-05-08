import pandas as pd


def calculate_bel(projection: pd.DataFrame) -> pd.DataFrame:
    result = (
        projection
        .groupby("policy_id")
        .agg({
            "PV_Gross_Premium_Inflow": "sum",
            "PV_Total_Cash_Outflow": "sum",
            "PV_Net_Cash_Flow": "sum"
        })
        .reset_index()
    )

    result["BEL"] = (
        result["PV_Total_Cash_Outflow"]
        - result["PV_Gross_Premium_Inflow"]
    )

    return result