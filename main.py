from engine.asumptions import loadconfig
from engine.curves import create_discount_curve
from engine.projection import (
    create_master_data,
    create_projection_table,
    attach_mortality_and_lapse
)
from engine.cashflows import calculate_cashflows
from engine.outputs import save_outputs


def main() -> None:
    config = loadconfig("config/config.json")

    discount_curve = create_discount_curve(config)

    master = create_master_data(config)

    projection = create_projection_table(
        master,
        config
    )

    projection = attach_mortality_and_lapse(
        projection,
        config
    )

    projection = projection.merge(
        discount_curve,
        on="Year",
        how="left"
    )

    projection = calculate_cashflows(
        projection,
        config
    )

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
            "PV_Net_Cash_Flow"
        ]]
        .sum()
        .reset_index()
    )

    save_outputs(
        projection=projection,
        master=master,
        summary=summary,
        output_dir="outputs",
        excel_enabled=config.excel_output
    )


if __name__ == "__main__":
    main()