import numpy as np
import pandas as pd

def calculate_initial_csm(
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame
) -> pd.DataFrame:
    csm_result = bel_result[["policy_id", "Year", "BEL"]].merge(
        ra_result[["policy_id", "Year", "RA"]],
        on=["policy_id", "Year"],
        how="left"
    )

    csm_result["RA"] = csm_result["RA"].fillna(0)

    csm_result["Initial_CSM"] = csm_result["BEL"] - csm_result["RA"]

    return csm_result[["policy_id", "Year", "Initial_CSM"]]

def calculate_csm_rollforward(
    projection: pd.DataFrame,
    csm_result: pd.DataFrame,
    config
) -> pd.DataFrame:
    projection = projection.copy()

    if "Initial_CSM" not in projection.columns:
        projection = projection.merge(
            csm_result[["policy_id", "Initial_CSM"]],
            on="policy_id",
            how="left"
        )

    projection["Initial_CSM"] = projection["Initial_CSM"].fillna(0)

    projection["Coverage_Units"] = (
        projection["sum_assured"]
        * projection["survival_ratio"]
    )

    projection["Total_Remaining_Coverage_Units"] = (
        projection
        .sort_values(["policy_id", "Year"], ascending=[True, False])
        .groupby("policy_id")["Coverage_Units"]
        .cumsum()
    )

    projection = projection.sort_values(["policy_id", "Year"])

    projection["CSM_Opening"] = 0.0
    projection["CSM_Interest"] = 0.0
    projection["CSM_Release"] = 0.0
    projection["CSM_Closing"] = 0.0

    for policy_id, idxs in projection.groupby("policy_id").groups.items():
        opening_csm = projection.loc[idxs, "Initial_CSM"].iloc[0]

        for idx in idxs:
            coverage_units = projection.loc[idx, "Coverage_Units"]
            remaining_units = projection.loc[idx, "Total_Remaining_Coverage_Units"]

            interest = opening_csm * config.discount_rate
            available_csm = opening_csm + interest

            release = (
                available_csm * coverage_units / remaining_units
                if remaining_units > 0
                else 0
            )

            closing_csm = max(available_csm - release, 0)

            projection.loc[idx, "CSM_Opening"] = opening_csm
            projection.loc[idx, "CSM_Interest"] = interest
            projection.loc[idx, "CSM_Release"] = release
            projection.loc[idx, "CSM_Closing"] = closing_csm

            opening_csm = closing_csm

    return projection
