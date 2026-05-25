from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
import logging
from typing import Optional

import pandas as pd

from engine.bel import calculate_bel
from engine.cashflows import calculate_cashflows
from engine.csm import calculate_csm_rollforward
from engine.curves import create_discount_curve
from model.config_model import ModelConfig
from engine.projection import (
    create_master_data,
    create_projection_table,
)
from engine.ra import calculate_risk_adjustment

logger = logging.getLogger(__name__)


SCENARIOS = {
    "base": {},
    "mortality_up_10": {"mortality_shock_multiplier": 1.10},
    "lapse_up_20": {"lapse_initial_rate_multiplier": 1.20},
    "expense_up_15": {"unit_expense_multiplier": 1.15},
    "discount_down_100bps": {"discount_rate_shift": -0.01},
}


def apply_scenario(config: ModelConfig, scenario: dict) -> ModelConfig:
    if hasattr(config, "model_copy"):
        return config.model_copy(update=scenario)

    cfg = deepcopy(config)
    for k, v in scenario.items():
        setattr(cfg, k, v)
    return cfg


def run_single_scenario(
    index: str,
    scenario_cfg: dict,
    base_config: ModelConfig,
    mortality_table: pd.DataFrame,
) -> Optional[dict]:
    try:
        config = apply_scenario(base_config, scenario_cfg)
        # Scenario runs should not overwrite the base run's diagnostic snapshot.
        # Diagnostics remain available for the base run and are disabled here by default.
        if hasattr(config, "model_copy"):
            config = config.model_copy(update={"enable_bel_diagnostics": False})
        else:
            setattr(config, "enable_bel_diagnostics", False)

        master_data = create_master_data(config)
        projection = create_projection_table(master_data, config, mortality_table)

        if "Year" not in projection.columns:
            raise ValueError("projection içinde 'Year' yok")
        projection["Year"] = projection["Year"].astype(int)

        discount_curve = create_discount_curve(config).copy()
        if "Year" not in discount_curve.columns:
            raise ValueError("discount_curve içinde 'Year' yok")
        discount_curve["Year"] = discount_curve["Year"].astype(int)

        if "discount_factor" not in discount_curve.columns:
            raise ValueError("discount_curve içinde 'discount_factor' yok")
        if "discount_factor_opening" not in discount_curve.columns:
            discount_curve["discount_factor_opening"] = discount_curve["discount_factor"]

        curve_subset = discount_curve[
            ["Year", "discount_factor", "discount_factor_opening"]
        ].drop_duplicates(subset=["Year"])

        projection = projection.merge(curve_subset, on="Year", how="left", validate="m:1")

        if "coverage_years" not in projection.columns:
            projection["coverage_years"] = int(
                getattr(config, "coverage_years", getattr(config, "projection_years", 1)) or 1
            )

        projection = calculate_cashflows(projection, config)

        bel_result = calculate_bel(projection, config, run_type="scenario", scenario_name=index)

        ra_result = calculate_risk_adjustment(projection, config)
        csm_result = calculate_csm_rollforward(
            bel_result,
            ra_result,
            projection,
            config,
        )

        if "bel_per_policy" in bel_result.columns:
            total_bel = float(bel_result["bel_per_policy"].sum())
        elif "BEL" in bel_result.columns:
            total_bel = float(bel_result["BEL"].sum())
        else:
            total_bel = float("nan")

        if "ra_per_policy" in ra_result.columns:
            total_ra = float(ra_result["ra_per_policy"].sum())
        elif "RA" in ra_result.columns:
            total_ra = float(ra_result["RA"].sum())
        else:
            total_ra = float("nan")

        total_csm_opening = float(csm_result["csm_opening"].sum())
        total_csm_closing = float(csm_result["csm_closing"].sum())
        onerous_count = int(csm_result["is_onerous"].sum())
        onerous_loss = float(csm_result["onerous_loss"].sum())

        return {
            "scenario": index,
            "n_policies": int(getattr(config, "n_policies", len(master_data))),
            "Total_BEL": total_bel,
            "Total_RA": total_ra,
            "Total_CSM_Opening": total_csm_opening,
            "Total_CSM_Closing": total_csm_closing,
            "Onerous_Count": onerous_count,
            "Onerous_Loss": onerous_loss,
        }

    except Exception as e:
        logger.warning(f"Error processing scenario {index}: {e}", exc_info=True)
        return None

    finally:
        gc.collect()


def run_scenarios(
    base_config: ModelConfig, scenarios: dict, mortality_table: pd.DataFrame
) -> pd.DataFrame:
    max_workers = int(getattr(base_config, "scenario_max_workers", 1) or 1)
    max_workers = max(1, max_workers)

    results: list[dict] = []

    # Run scenarios concurrently when configured.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_single_scenario, name, cfg, base_config, mortality_table): name
            for name, cfg in scenarios.items()
        }
        for fut in as_completed(futures):
            r = fut.result()
            if r is not None:
                results.append(r)

    if not results:
        return pd.DataFrame(
            columns=[
                "scenario",
                "n_policies",
                "Total_BEL",
                "Total_RA",
                "Total_CSM_Opening",
                "Total_CSM_Closing",
                "Onerous_Count",
                "Onerous_Loss",
            ]
        )

    return pd.DataFrame(results).sort_values("scenario").reset_index(drop=True)
