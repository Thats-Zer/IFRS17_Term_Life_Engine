from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import pandas as pd

from engine.audit import build_audit_report, config_snapshot
from engine.bel import get_last_bel_diagnostic_summary

logger = logging.getLogger(__name__)

EXCEL_MAX_ROWS = 1_048_576


def _write_excel_safe(
    writer: pd.ExcelWriter,
    df: Optional[pd.DataFrame],
    sheet: str,
    preview_rows: int = 200_000,
) -> None:
    """Write a full Excel sheet when possible, otherwise write a bounded preview."""
    if df is None:
        logger.warning("DataFrame is None for sheet: %s", sheet)
        return

    n_rows, n_cols = df.shape
    if n_rows <= EXCEL_MAX_ROWS:
        df.to_excel(writer, sheet_name=sheet, index=False)
        return

    df.head(min(preview_rows, n_rows)).to_excel(writer, sheet_name=sheet, index=False)
    meta = pd.DataFrame(
        [
            {
                "sheet": sheet,
                "rows": n_rows,
                "cols": n_cols,
                "note": (
                    f"Too large for Excel. Wrote first {min(preview_rows, n_rows)} "
                    "rows only. Full data is in CSV outputs."
                ),
            }
        ]
    )
    meta.to_excel(writer, sheet_name=f"{sheet}_meta", index=False)


def _write_csv(output_path: Path, name: str, df: Optional[pd.DataFrame]) -> None:
    if df is None:
        return
    df.to_csv(output_path / name, index=False, encoding="utf-8-sig")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _write_bel_diagnostics_json(output_path: Path, bel_diagnostics: Any) -> None:
    safe_payload = _json_safe(bel_diagnostics)
    (output_path / "bel_diagnostics.json").write_text(
        json.dumps(safe_payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _write_audit_files(
    output_path: Path,
    *,
    config: Any,
    projection: pd.DataFrame,
    master: pd.DataFrame,
    bel_result: Optional[pd.DataFrame],
    ra_result: Optional[pd.DataFrame],
    csm_result: Optional[pd.DataFrame],
    scenario_results: Optional[pd.DataFrame],
    group_result: Optional[pd.DataFrame],
    bel_diagnostics: Optional[dict[str, Any]] = None,
) -> None:
    run_id = uuid4().hex
    snapshot = config_snapshot(config)
    # Prefer the explicitly captured base-run diagnostics; the module-level
    # fallback is only a convenience for older callers.
    if bel_diagnostics is None:
        bel_diagnostics = get_last_bel_diagnostic_summary()
    (output_path / "assumption_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    _write_bel_diagnostics_json(output_path, bel_diagnostics)

    audit_report = build_audit_report(
        config=config,
        projection=projection,
        master=master,
        bel_result=bel_result,
        ra_result=ra_result,
        csm_result=csm_result,
        scenario_results=scenario_results,
        group_result=group_result,
        run_id=run_id,
        bel_diagnostics=_json_safe(bel_diagnostics),
    )
    (output_path / "audit_report.json").write_text(
        json.dumps(audit_report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    registry_row = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "created_at_utc": audit_report["created_at_utc"],
                "assumption_hash": audit_report["assumption_hash"],
                "methodology_version": audit_report["methodology_version"],
                "approval_status": audit_report["approval_status"],
                "projection_rows": audit_report["row_counts"]["projection"]["rows"],
                "total_bel": audit_report["reconciliation_totals"].get("total_bel"),
                "total_ra": audit_report["reconciliation_totals"].get("total_ra"),
                "total_csm_opening": audit_report["reconciliation_totals"].get("total_csm_opening"),
                "total_csm_closing": audit_report["reconciliation_totals"].get("total_csm_closing"),
            }
        ]
    )
    registry_path = output_path / "run_registry.csv"
    registry_row.to_csv(
        registry_path,
        index=False,
        mode="a",
        header=not registry_path.exists(),
        encoding="utf-8-sig",
    )


def save_outputs(
    projection: pd.DataFrame,
    bel_result: Optional[pd.DataFrame],
    ra_result: Optional[pd.DataFrame],
    csm_result: Optional[pd.DataFrame],
    scenario_results: Optional[pd.DataFrame],
    output_dir: str,
    master: pd.DataFrame,
    excel_output: bool = True,
    excel_path: Optional[str] = None,
    group_result: Optional[pd.DataFrame] = None,
    config: Optional[Any] = None,
    bel_diagnostics: Optional[dict[str, Any]] = None,
    disclosure_package: Optional[dict[str, pd.DataFrame]] = None,
) -> None:
    """Persist engine outputs to CSV, optional Excel, and optional audit JSON."""
    if projection is None:
        raise ValueError("projection is required")
    if master is None:
        raise ValueError("master is required")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    _write_csv(output_path, "projection_results.csv", projection)
    _write_csv(output_path, "master_results.csv", master)
    _write_csv(output_path, "bel_results.csv", bel_result)
    _write_csv(output_path, "ra_results.csv", ra_result)
    _write_csv(output_path, "csm_results.csv", csm_result)
    _write_csv(output_path, "scenario_results.csv", scenario_results)
    _write_csv(output_path, "group_results.csv", group_result)
    if disclosure_package:
        for name, df in disclosure_package.items():
            _write_csv(output_path, f"disclosure_{name}.csv", df)

    if config is not None:
        _write_audit_files(
            output_path,
            config=config,
            projection=projection,
            master=master,
            bel_result=bel_result,
            ra_result=ra_result,
            csm_result=csm_result,
            scenario_results=scenario_results,
            group_result=group_result,
            bel_diagnostics=bel_diagnostics,
        )

    logger.info("CSV outputs saved")

    if not excel_output:
        logger.info("Excel output skipped by config")
        return

    excel_file = (
        Path(excel_path) if excel_path else output_path / "ifrs17_term_life_projection.xlsx"
    )
    excel_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
            _write_excel_safe(writer, master, "master")
            _write_excel_safe(writer, projection, "projection")
            _write_excel_safe(writer, bel_result, "bel")
            _write_excel_safe(writer, ra_result, "ra")
            _write_excel_safe(writer, csm_result, "csm")
            _write_excel_safe(writer, group_result, "groups")
            _write_excel_safe(writer, scenario_results, "scenarios")
            if disclosure_package:
                for name, df in disclosure_package.items():
                    _write_excel_safe(writer, df, f"disc_{name}"[:31])
        logger.info("Excel outputs saved: %s", excel_file)
    except ModuleNotFoundError as e:
        logger.warning("Excel export skipped (missing dependency): %s", e)
