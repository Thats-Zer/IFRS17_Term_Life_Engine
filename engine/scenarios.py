from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import gc
import pandas as pd

from model.config_model import ModelConfig
from engine.curves import create_discount_curve
from engine.projection import (
    create_master_data,
    create_projection_table,
)
from engine.cashflows import calculate_cashflows
from engine.bel import calculate_bel
from engine.ra import calculate_risk_adjustment


SCENARIOS = {
    "base": {},
    "mortality_up_10": {"mortality_shock_multiplier": 1.10},
    "lapse_up_20": {"lapse_initial_rate_multiplier": 1.20},
    "expense_up_15": {"unit_expense_multiplier": 1.15},
    "discount_down_100bps": {"discount_rate_shift": -0.01},
}


def apply_scenario(config: ModelConfig, scenario: dict) -> ModelConfig:
    # Pydantic v2
    if hasattr(config, "model_copy"):
        return config.model_copy(update=scenario)  # type: ignore[attr-defined]
    # Pydantic v1
    if hasattr(config, "copy"):
        try:
            return config.copy(update=scenario)  # type: ignore[attr-defined]
        except TypeError:
            pass

    cfg = deepcopy(config)
    for k, v in scenario.items():
        setattr(cfg, k, v)
    return cfg


def run_single_scenario(
    index: str,
    scenario_cfg: dict,
    base_config: ModelConfig,
    mortality_table: pd.DataFrame
) -> Optional[dict]:
    try:
        config = apply_scenario(base_config, scenario_cfg)

        master_data = create_master_data(config)
        projection = create_projection_table(master_data, config, mortality_table)

        # --- Ensure Year int
        if "Year" not in projection.columns:
            raise ValueError("projection içinde 'Year' yok")
        projection["Year"] = projection["Year"].astype(int)

        # --- Add discount factors safely (avoid cartesian explode)
        discount_curve = create_discount_curve(config).copy()
        if "Year" not in discount_curve.columns:
            raise ValueError("discount_curve içinde 'Year' yok")
        discount_curve["Year"] = discount_curve["Year"].astype(int)

        if "discount_factor" not in discount_curve.columns:
            raise ValueError("discount_curve içinde 'discount_factor' yok")
        if "discount_factor_opening" not in discount_curve.columns:
            discount_curve["discount_factor_opening"] = discount_curve["discount_factor"]

        curve_subset = (
            discount_curve[["Year", "discount_factor", "discount_factor_opening"]]
            .drop_duplicates(subset=["Year"])
        )
        projection = projection.merge(curve_subset, on="Year", how="left", validate="m:1")

        # --- coverage_years required by cashflows
        if "coverage_years" not in projection.columns:
            projection["coverage_years"] = projection["Year"]

        projection = calculate_cashflows(projection, config)
        bel_result = calculate_bel(projection, config)
        ra_result = calculate_risk_adjustment(projection, config)

        total_bel = float(bel_result["BEL"].sum()) if "BEL" in bel_result.columns else float("nan")
        # RA kolonu isimleri projeye göre değişebiliyor; iki olasılığı da destekle
        if "RA" in ra_result.columns:
            total_ra = float(ra_result["RA"].sum())
        elif "ra_per_policy" in ra_result.columns:
            total_ra = float(ra_result["ra_per_policy"].sum())
        else:
            total_ra = float("nan")

        return {
            "scenario": index,
            "n_policies": int(getattr(config, "n_policies", len(master_data))),
            "Total_BEL": total_bel,
            "Total_RA": total_ra,
        }

    except Exception as e:
        print(f"Error processing scenario {index}: {e}")
        return None
    finally:
        # best-effort memory release for scenario threads
        gc.collect()


def run_scenarios(
    base_config: ModelConfig,
    scenarios: dict,
    mortality_table: pd.DataFrame
) -> pd.DataFrame:
    # Memory-safe default: run sequentially unless explicitly increased
    max_workers = int(getattr(base_config, "scenario_max_workers", 1) or 1)
    max_workers = max(1, max_workers)

    results: list[dict] = []

    # threads >1 can still be used, but keep small to avoid RAM spikes
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
        return pd.DataFrame(columns=["scenario", "n_policies", "Total_BEL", "Total_RA"])

    return pd.DataFrame(results).sort_values("scenario").reset_index(drop=True)