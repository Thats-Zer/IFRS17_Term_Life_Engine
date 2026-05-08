from pathlib import Path
import pandas as pd


EXCEL_MAX_ROWS = 1_048_576


def save_outputs(
    projection: pd.DataFrame,
    master: pd.DataFrame,
    bel_result: pd.DataFrame | None = None,
    ra_result: pd.DataFrame | None = None,
    csm_result: pd.DataFrame | None = None,
    summary: pd.DataFrame | None = None,
    scenario_results: pd.DataFrame | None = None,
    output_dir: str = "outputs",
    excel_enabled: bool = True
) -> None:

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ==================================================
    # CSV OUTPUTS
    # ==================================================

    projection.to_csv(
        output_path / "projection_results.csv",
        index=False,
        encoding="utf-8-sig"
    )

    master.to_csv(
        output_path / "master_results.csv",
        index=False,
        encoding="utf-8-sig"
    )

    if bel_result is not None:
        bel_result.to_csv(
            output_path / "bel_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    if ra_result is not None:
        ra_result.to_csv(
            output_path / "ra_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    if csm_result is not None:
        csm_result.to_csv(
            output_path / "csm_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    if scenario_results is not None:
        scenario_results.to_csv(
            output_path / "scenario_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    print("✓ CSV outputs saved")

    # ==================================================
    # EXCEL OUTPUT
    # ==================================================

    if not excel_enabled:
        print("ℹ Excel output disabled")
        return

    if len(projection) > EXCEL_MAX_ROWS:
        print(
            f"⚠ Projection exceeds Excel limit "
            f"({EXCEL_MAX_ROWS:,} rows)"
        )
        return

    excel_file = output_path / "ifrs17_term_life_projection.xlsx"

    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:

        # ==============================================
        # CORE SHEETS
        # ==============================================

        master.to_excel(
            writer,
            sheet_name="Policy_Master",
            index=False
        )

        projection.to_excel(
            writer,
            sheet_name="Projection_Detail",
            index=False
        )

        # ==============================================
        # SUMMARY
        # ==============================================

        if summary is not None:
            summary.to_excel(
                writer,
                sheet_name="Summary",
                index=False
            )

        # ==============================================
        # BEL
        # ==============================================

        if bel_result is not None:
            bel_result.to_excel(
                writer,
                sheet_name="BEL",
                index=False
            )

        # ==============================================
        # RA
        # ==============================================

        if ra_result is not None:
            ra_result.to_excel(
                writer,
                sheet_name="RA",
                index=False
            )

        # ==============================================
        # CSM
        # ==============================================

        if csm_result is not None:
            csm_result.to_excel(
                writer,
                sheet_name="CSM",
                index=False
            )

        # ==============================================
        # SCENARIOS
        # ==============================================

        if scenario_results is not None:
            scenario_results.to_excel(
                writer,
                sheet_name="Scenario_Analysis",
                index=False
            )

    print(f"✓ Excel saved: {excel_file}")