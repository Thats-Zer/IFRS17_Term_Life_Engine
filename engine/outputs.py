from pathlib import Path
import logging
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_MAX_ROWS = 1_048_576 # Excel'in tek bir sayfada desteklediği maksimum satır sayısı


def _write_excel_safe(writer: pd.ExcelWriter, df: pd.DataFrame, sheet: str, preview_rows: int = 200_000) -> None:
    """Excel row limitini aşan DF'leri Excel'e tam koyma; sadece preview + özet bas."""
    if df is None:
        logger.warning(f"DataFrame is None for sheet: {sheet}")
        return

    # Excel'in satır limitini kontrol et
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

# Ana fonksiyon: tüm çıktıları kaydet
def save_outputs(
    projection: pd.DataFrame,
    bel_result: Optional[pd.DataFrame],
    ra_result: Optional[pd.DataFrame],
    csm_result: Optional[pd.DataFrame],
    scenario_results: Optional[pd.DataFrame],
    output_dir: str,
    master: pd.DataFrame,
) -> None:
    """Persist engine outputs to CSV and (optionally) Excel.

    Notes:
    - CSVs are written as UTF-8 with BOM for Excel compatibility.
    - Excel export uses `openpyxl` and applies a row-limit guard.
    """
    if projection is None:
        raise ValueError("projection is required")
    if master is None:
        raise ValueError("master is required")

    # 1. Çıktı klasörünü oluştur
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ==================================================
    # CSV OUTPUTS
    # ==================================================

    # CSV olarak kaydet: UTF-8 with BOM (Excel uyumlu)
    projection.to_csv(
        output_path / "projection_results.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Master sonuçları CSV'ye kaydet
    master.to_csv(
        output_path / "master_results.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Diğer sonuçları CSV'ye kaydet
    if bel_result is not None:
        bel_result.to_csv(
            output_path / "bel_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    # RA ve CSM sonuçları CSV'ye kaydet
    if ra_result is not None:
        ra_result.to_csv(
            output_path / "ra_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    # CSM sonuçlarını CSV'ye kaydet
    if csm_result is not None:
        csm_result.to_csv(
            output_path / "csm_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    # Senaryo sonuçlarını CSV'ye kaydet
    if scenario_results is not None:
        scenario_results.to_csv(
            output_path / "scenario_results.csv",
            index=False,
            encoding="utf-8-sig"
        )

    # Log: CSV çıktıların kaydedildiği bilgisini ver
    logger.info("CSV outputs saved")

    # ==================================================
    # EXCEL OUTPUT
    # ==================================================

    #Kaydetme yolunu belirle
    excel_file = output_path / "ifrs17_term_life_projection.xlsx"

    # Excel'e kaydet: openpyxl motorunu kullanarak tüm DataFrame'leri tek bir dosyada farklı sayfalara yaz
    try:
        with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
            _write_excel_safe(writer, master, "master")
            _write_excel_safe(writer, projection, "projection")
            _write_excel_safe(writer, bel_result, "bel")
            _write_excel_safe(writer, ra_result, "ra")
            _write_excel_safe(writer, csm_result, "csm")
            if scenario_results is not None:
                _write_excel_safe(writer, scenario_results, "scenarios")
        logger.info(f"Excel outputs saved: {excel_file}")
    except ModuleNotFoundError as e:
        # openpyxl missing or not importable
        logger.warning(f"Excel export skipped (missing dependency): {e}")