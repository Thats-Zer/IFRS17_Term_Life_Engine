import numpy as np
import pandas as pd


def assign_ifrs17_groups(csm_result: pd.DataFrame) -> pd.DataFrame:
    result = csm_result.copy()

    result["ifrs17_group"] = np.where(
        result["Loss_Component"] > 0,
        "Onerous",
        "Profitable"
    )

    result["annual_cohort"] = "Cohort_2026"
    result["portfolio"] = "Term_Life"

    return result