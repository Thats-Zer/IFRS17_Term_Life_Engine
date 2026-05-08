from pathlib import Path
import pandas as pd

EXCEL_MAX_ROWS = 1_048_576


def _write_excel_safe(writer: pd.ExcelWriter, df: pd.DataFrame, sheet: str, preview_rows: int = 200_000) -> None:
    """Excel row limitini aşan DF'leri Excel'e full basma; sadece preview + özet bas."""
    if df is None:
        return

    n_rows, n_cols = df.shape
    if n_rows <= EXCEL_MAX_ROWS:
        df.to_excel(writer, sheet_name=sheet, index=False)
        return

    # preview
    df.head(min(preview_rows, n_rows)).to_excel(writer, sheet_name=sheet, index=False)

    # meta sheet
    meta = pd.DataFrame([{
        "sheet": sheet,
        "rows": n_rows,
        "cols": n_cols,
        "note": f"Too large for Excel. Wrote first {min(preview_rows, n_rows)} rows only. Full data is in CSV outputs."
    }])
    meta.to_excel(writer, sheet_name=f"{sheet}_meta", index=False)


def save_outputs(
    projection: pd.DataFrame,
    bel_result: pd.DataFrame,
    ra_result: pd.DataFrame,
    csm_result: pd.DataFrame,
    scenario_results: pd.DataFrame,
    output_dir: str,
    master: pd.DataFrame,
):

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

    excel_file = output_path / "ifrs17_term_life_projection.xlsx"

    # Excel write: safe
    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        _write_excel_safe(writer, master, "master")
        _write_excel_safe(writer, projection, "projection")
        _write_excel_safe(writer, bel_result, "bel")
        _write_excel_safe(writer, ra_result, "ra")
        _write_excel_safe(writer, csm_result, "csm")
        if scenario_results is not None:
            _write_excel_safe(writer, scenario_results, "scenarios")

    print(f"✓ Excel saved: {excel_file}")