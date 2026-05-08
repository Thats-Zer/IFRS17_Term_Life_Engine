import numpy as np
import pandas as pd


def calculate_initial_csm(
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame
) -> pd.DataFrame:

    result = bel_result.merge(
        ra_result[["policy_id", "RA"]],
        on="policy_id",
        how="left"
    )

    result["FCF"] = result["BEL"] + result["RA"]

    result["Initial_CSM"] = np.where(
        result["FCF"] < 0,
        -result["FCF"],
        0
    )

    result["Loss_Component"] = np.where(
        result["FCF"] > 0,
        result["FCF"],
        0
    )

    return result


def calculate_csm_release(
    projection: pd.DataFrame,
    csm_result: pd.DataFrame
) -> pd.DataFrame:

    projection = projection.copy()

    projection = projection.merge(
        csm_result[["policy_id", "Initial_CSM"]],
        on="policy_id",
        how="left"
    )

    projection["Coverage_Units"] = (
        projection["sum_assured"]
        * projection["survival_ratio"]
    )

    projection["Total_Coverage_Units"] = (
        projection
        .groupby("policy_id")["Coverage_Units"]
        .transform("sum")
    )

    projection["CSM_Release"] = np.where(
        projection["Total_Coverage_Units"] > 0,
        projection["Initial_CSM"]
        * projection["Coverage_Units"]
        / projection["Total_Coverage_Units"],
        0
    )

    projection["CSM_Closing"] = (
        projection["Initial_CSM"]
        - projection
        .groupby("policy_id")["CSM_Release"]
        .cumsum()
    )

    projection["CSM_Closing"] = projection["CSM_Closing"].clip(lower=0)

    return projection