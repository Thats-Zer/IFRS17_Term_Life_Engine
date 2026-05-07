from pathlib import Path
import pandas as pd


EXCEL_MAX_ROWS = 1_048_576


def save_outputs(
    projection: pd.DataFrame,
    master: pd.DataFrame,
    summary: pd.DataFrame | None = None,
    output_dir: str = "outputs",
    excel_enabled: bool = True
) -> None:
    """
    Projection ve master tablolarını CSV ve Excel olarak kaydeder.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # CSV outputs
    projection_csv = output_path / "projection_results.csv"
    master_csv = output_path / "master_results.csv"

    projection.to_csv(projection_csv, index=False, encoding="utf-8-sig")
    master.to_csv(master_csv, index=False, encoding="utf-8-sig")

    print(f"✓ CSV saved: {projection_csv}")
    print(f"✓ CSV saved: {master_csv}")

    # Excel output
    if not excel_enabled:
        print("ℹ Excel output disabled.")
        return

    if len(projection) > EXCEL_MAX_ROWS:
        print(
            f"⚠ Projection has {len(projection):,} rows. "
            f"Excel limit is {EXCEL_MAX_ROWS:,}. Excel skipped."
        )
        return

    excel_file = output_path / "ifrs17_term_life_projection.xlsx"

    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        master.to_excel(writer, sheet_name="Policy_Master", index=False)
        projection.to_excel(writer, sheet_name="Projection_Detail", index=False)

        if summary is not None:
            summary.to_excel(writer, sheet_name="Summary", index=False)

    print(f"✓ Excel saved: {excel_file}")