from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _issue(
    code: str, message: str, column: str | None = None, severity: str = "error"
) -> dict[str, str]:
    issue = {"severity": severity, "code": code, "message": message}
    if column is not None:
        issue["column"] = column
    return issue


def _table_report(name: str, df: pd.DataFrame | None) -> dict[str, Any]:
    if df is None:
        return {
            "table": name,
            "status": "not_provided",
            "row_count": 0,
            "errors": [],
            "warnings": [],
        }
    return {
        "table": name,
        "status": "pass",
        "row_count": int(len(df)),
        "errors": [],
        "warnings": [],
    }


def _add_error(report: dict[str, Any], code: str, message: str, column: str | None = None) -> None:
    report["errors"].append(_issue(code, message, column))
    report["status"] = "fail"


def _check_required_columns(
    report: dict[str, Any], df: pd.DataFrame, required_columns: set[str]
) -> None:
    missing = sorted(required_columns - set(df.columns))
    if missing:
        _add_error(
            report,
            "missing_required_columns",
            f"Missing required columns: {missing}",
        )


def _check_missing_and_infinite(report: dict[str, Any], df: pd.DataFrame) -> None:
    missing_cols = sorted(df.columns[df.isna().any()].tolist())
    for col in missing_cols:
        _add_error(report, "missing_values", f"Column contains missing values: {col}", col)

    numeric = df.select_dtypes(include=[np.number])
    if numeric.empty:
        return
    infinite_mask = np.isinf(numeric.to_numpy(dtype=float, copy=False))
    if not infinite_mask.any():
        return
    for col in numeric.columns[infinite_mask.any(axis=0)].tolist():
        _add_error(report, "infinite_values", f"Column contains infinite values: {col}", col)


def _check_between(
    report: dict[str, Any],
    df: pd.DataFrame,
    column: str,
    lower: float,
    upper: float,
) -> None:
    if column not in df.columns:
        return
    invalid = ~df[column].between(lower, upper, inclusive="both")
    if invalid.any():
        _add_error(
            report,
            "value_out_of_range",
            f"{column} must be within [{lower}, {upper}]",
            column,
        )


def _check_positive(report: dict[str, Any], df: pd.DataFrame, column: str) -> None:
    if column not in df.columns:
        return
    if (df[column] <= 0).any():
        _add_error(report, "non_positive_value", f"{column} must be greater than zero", column)


def validate_policy_input(df: pd.DataFrame | None, config: Any = None) -> dict[str, Any]:
    report = _table_report("policy_input", df)
    if df is None:
        return report

    required = {"policy_id", "issue_age", "sum_assured", "coverage_years"}
    _check_required_columns(report, df, required)
    _check_missing_and_infinite(report, df)
    if not required.issubset(df.columns):
        return report

    if df["policy_id"].duplicated().any():
        _add_error(report, "duplicate_policy_id", "policy_id values must be unique", "policy_id")

    _check_positive(report, df, "sum_assured")
    _check_positive(report, df, "coverage_years")

    min_age = int(getattr(config, "min_issue_age", 0)) if config is not None else 0
    max_age = int(getattr(config, "max_issue_age", 200)) if config is not None else 200
    invalid_age = (df["issue_age"] < min_age) | (df["issue_age"] > max_age)
    if invalid_age.any():
        _add_error(
            report,
            "invalid_issue_age",
            f"issue_age must be within [{min_age}, {max_age}]",
            "issue_age",
        )
    return report


def validate_mortality_table(df: pd.DataFrame | None) -> dict[str, Any]:
    report = _table_report("mortality_table", df)
    if df is None:
        return report

    required = {"age", "qx"}
    _check_required_columns(report, df, required)
    _check_missing_and_infinite(report, df)
    if not required.issubset(df.columns):
        return report

    if (df["age"] < 0).any():
        _add_error(report, "invalid_age", "age must be non-negative", "age")
    _check_between(report, df, "qx", 0.0, 1.0)
    return report


def validate_discount_curve(df: pd.DataFrame | None) -> dict[str, Any]:
    report = _table_report("discount_curve", df)
    if df is None:
        return report

    required = {"Year", "discount_factor"}
    _check_required_columns(report, df, required)
    _check_missing_and_infinite(report, df)
    if not required.issubset(df.columns):
        return report

    _check_positive(report, df, "discount_factor")
    _check_positive(report, df, "discount_factor_opening")
    return report


def validate_projection_table(df: pd.DataFrame | None) -> dict[str, Any]:
    report = _table_report("projection_table", df)
    if df is None:
        return report

    required = {
        "policy_id",
        "Year",
        "coverage_years",
        "qx",
        "lapse_rate",
        "sum_assured",
        "discount_factor",
    }
    _check_required_columns(report, df, required)
    _check_missing_and_infinite(report, df)
    if not required.issubset(df.columns):
        return report

    _check_positive(report, df, "coverage_years")
    _check_positive(report, df, "sum_assured")
    _check_positive(report, df, "discount_factor")
    _check_between(report, df, "qx", 0.0, 1.0)
    _check_between(report, df, "lapse_rate", 0.0, 1.0)
    return report


def validate_cashflow_table(df: pd.DataFrame | None) -> dict[str, Any]:
    report = _table_report("cashflow_table", df)
    if df is None:
        return report

    required = {"policy_id", "Year", "Gross_Premium_Inflow", "Death_Benefits", "Net_Cash_Flow"}
    _check_required_columns(report, df, required)
    _check_missing_and_infinite(report, df)
    return report


def build_data_validation_report(
    *,
    policy_input: pd.DataFrame | None = None,
    mortality_table: pd.DataFrame | None = None,
    discount_curve: pd.DataFrame | None = None,
    projection: pd.DataFrame | None = None,
    cashflows: pd.DataFrame | None = None,
    config: Any = None,
) -> dict[str, Any]:
    tables = [
        validate_policy_input(policy_input, config),
        validate_mortality_table(mortality_table),
        validate_discount_curve(discount_curve),
        validate_projection_table(projection),
        validate_cashflow_table(cashflows),
    ]
    error_count = sum(len(table["errors"]) for table in tables)
    warning_count = sum(len(table["warnings"]) for table in tables)
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "fail" if error_count else "pass",
        "error_count": int(error_count),
        "warning_count": int(warning_count),
        "tables": tables,
    }


def write_data_validation_report(output_path: Path | str, report: dict[str, Any]) -> Path:
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "data_validation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return report_path
