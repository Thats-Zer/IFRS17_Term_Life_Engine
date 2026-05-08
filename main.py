from engine.asumptions import loadconfig
from engine.curves import create_discount_curve

from engine.projection import (
    create_master_data,
    create_projection_table,
    attach_mortality_and_lapse
)

from engine.cashflows import calculate_cashflows
from engine.bel import calculate_bel
from engine.ra import calculate_ra

from engine.csm import (
    calculate_initial_csm,
    calculate_csm_rollforward
)

from engine.grouping import assign_ifrs17_groups
from engine.outputs import save_outputs
from engine.scenarios import run_scenarios


def main() -> None:
    # 1. Load config
    config = loadconfig("config/config.json")

    # 2. Create discount curve
    discount_curve = create_discount_curve(config)

    # 3. Create master policy data
    master = create_master_data(config)

    # 4. Create projection table
    projection = create_projection_table(
        master,
        config
    )

    # 5. Attach mortality, lapse and survival assumptions
    projection = attach_mortality_and_lapse(
        projection,
        config
    )

    # 6. Attach discount factors
    projection = projection.merge(
        discount_curve,
        on="Year",
        how="left"
    )

    # 7. Calculate premiums and insurance cashflows
    projection = calculate_cashflows(
        projection,
        config
    )

    # 8. Calculate BEL
    bel_result = calculate_bel(projection)

    # 9. Calculate RA
    projection, ra_result = calculate_ra(
        projection,
        config
    )

    # 10. Calculate initial CSM and loss component
    csm_result = calculate_initial_csm(
        bel_result,
        ra_result
    )

    # 11. Assign IFRS 17 profitability groups
    csm_result = assign_ifrs17_groups(csm_result)

    # 12. Calculate CSM roll-forward
    projection = calculate_csm_rollforward(
        projection,
        csm_result,
        config
    )

    # 13. Merge policy-level IFRS 17 results into projection
    projection = projection.merge(
        csm_result[[
            "policy_id",
            "BEL",
            "RA",
            "FCF",
            "Initial_CSM",
            "Loss_Component",
            "ifrs17_group",
            "annual_cohort",
            "portfolio"
        ]],
        on="policy_id",
        how="left"
    )

    # 14. Create yearly summary
    summary = (
        projection
        .groupby("Year")[[
            "Gross_Premium_Inflow",
            "Net_Premium_Inflow",
            "Expected_Death_Claims",
            "Net_Death_Claims",
            "Expense_Outflow",
            "Default_Risk_Cost",
            "Total_Cash_Outflow",
            "Net_Cash_Flow",
            "PV_Net_Cash_Flow",
            "S2_Capital",
            "OpRisk_Capital",
            "Total_SCR",
            "CoC_Yearly",
            "PV_CoC_Yearly",
            "CSM_Opening",
            "CSM_Interest",
            "CSM_Release",
            "CSM_Closing"
        ]]
        .sum()
        .reset_index()
    )

    # 15. Run scenarios
    scenario_results = run_scenarios(config)

    # 16. Save main outputs
    save_outputs(
    projection=projection,
    master=master,
    bel_result=bel_result,
    ra_result=ra_result,
    csm_result=csm_result,
    summary=summary,
    scenario_results=scenario_results,
    output_dir="outputs",
    excel_enabled=config.excel_output
)


    # 17. Save scenario results
    scenario_results.to_csv(
        "outputs/scenario_results.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("✓ IFRS 17 Term-Life valuation completed successfully")


if __name__ == "__main__":
    main()