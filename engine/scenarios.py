from copy import deepcopy
import pandas as pd

from model.config_model import ModelConfig
from engine.curves import create_discount_curve
from engine.projection import (
    create_master_data,
    create_projection_table,
    attach_mortality_and_lapse
)
from engine.cashflows import calculate_cashflows
from engine.bel import calculate_bel
from engine.ra import calculate_ra
from engine.csm import calculate_initial_csm
from engine.grouping import assign_ifrs17_groups


SCENARIOS = {
    "base": {},
    "mortality_up_10": {
        "mortality_shock_multiplier": 1.10
    },
    "lapse_up_20": {
        "lapse_initial_rate_multiplier": 1.20
    },
    "expense_up_15": {
        "unit_expense_multiplier": 1.15
    },
    "discount_down_100bps": {
        "discount_rate_shift": -0.01
    }
}


def apply_scenario(
    config: ModelConfig,
    scenario: dict
) -> ModelConfig:

    scenario_config = deepcopy(config)

    if "mortality_shock_multiplier" in scenario:
        scenario_config.mortality_shock *= scenario["mortality_shock_multiplier"]

    if "lapse_initial_rate_multiplier" in scenario:
        scenario_config.lapse_base_rate *= scenario["lapse_initial_rate_multiplier"]

    if "unit_expense_multiplier" in scenario:
        scenario_config.unit_cost *= scenario["unit_expense_multiplier"]

    if "discount_rate_shift" in scenario:
        scenario_config.discount_rate += scenario["discount_rate_shift"]
        scenario_config.discount_rate = max(scenario_config.discount_rate, 0)

    return scenario_config


def run_single_scenario(
    base_config: ModelConfig,
    scenario_name: str,
    scenario: dict
) -> dict:

    config = apply_scenario(base_config, scenario)

    discount_curve = create_discount_curve(config)

    master = create_master_data(config)
    projection = create_projection_table(master, config)
    projection = attach_mortality_and_lapse(projection, config)

    projection = projection.merge(
        discount_curve,
        on="Year",
        how="left"
    )

    projection = calculate_cashflows(projection, config)

    bel_result = calculate_bel(projection)

    projection, ra_result = calculate_ra(projection, config)

    csm_result = calculate_initial_csm(
        bel_result,
        ra_result
    )

    csm_result = assign_ifrs17_groups(csm_result)

    return {
        "scenario": scenario_name,
        "Total_BEL": bel_result["BEL"].sum(),
        "Total_RA": ra_result["RA"].sum(),
        "Total_FCF": csm_result["FCF"].sum(),
        "Total_CSM": csm_result["Initial_CSM"].sum(),
        "Total_Loss_Component": csm_result["Loss_Component"].sum(),
        "Onerous_Count": (csm_result["ifrs17_group"] == "Onerous").sum(),
        "Profitable_Count": (csm_result["ifrs17_group"] == "Profitable").sum()
    }


def run_scenarios(
    base_config: ModelConfig,
    scenarios: dict = SCENARIOS
) -> pd.DataFrame:

    results = []

    for scenario_name, scenario in scenarios.items():
        result = run_single_scenario(
            base_config,
            scenario_name,
            scenario
        )

        results.append(result)

    return pd.DataFrame(results)