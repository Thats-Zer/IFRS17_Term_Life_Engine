import json
from pathlib import Path

import pandas as pd

from engine.validation import (
    build_data_validation_report,
    validate_discount_curve,
    validate_mortality_table,
    validate_policy_input,
    write_data_validation_report,
)
from model.config_model import ConfigModel


def _config() -> ConfigModel:
    return ConfigModel(n_policies=2, projection_years=2, coverage_years=2)


def _valid_policy_input() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [30, 40],
            "sum_assured": [10000.0, 20000.0],
            "coverage_years": [2, 2],
        }
    )


def test_valid_policy_input_passes():
    report = validate_policy_input(_valid_policy_input(), _config())

    assert report["status"] == "pass"
    assert report["errors"] == []


def test_duplicate_policy_id_fails():
    df = _valid_policy_input()
    df.loc[1, "policy_id"] = df.loc[0, "policy_id"]

    report = validate_policy_input(df, _config())

    assert report["status"] == "fail"
    assert any(error["code"] == "duplicate_policy_id" for error in report["errors"])


def test_missing_required_column_fails():
    report = validate_policy_input(_valid_policy_input().drop(columns=["sum_assured"]), _config())

    assert report["status"] == "fail"
    assert any(error["code"] == "missing_required_columns" for error in report["errors"])


def test_invalid_qx_fails():
    mortality = pd.DataFrame({"age": [30, 31], "qx": [0.001, 1.2]})

    report = validate_mortality_table(mortality)

    assert report["status"] == "fail"
    assert any(error.get("column") == "qx" for error in report["errors"])


def test_negative_sum_assured_fails():
    df = _valid_policy_input()
    df.loc[0, "sum_assured"] = -1.0

    report = validate_policy_input(df, _config())

    assert report["status"] == "fail"
    assert any(error.get("column") == "sum_assured" for error in report["errors"])


def test_invalid_discount_factor_fails():
    curve = pd.DataFrame({"Year": [1, 2], "discount_factor": [0.95, 0.0]})

    report = validate_discount_curve(curve)

    assert report["status"] == "fail"
    assert any(error.get("column") == "discount_factor" for error in report["errors"])


def test_report_writes_to_json(tmp_path: Path):
    report = build_data_validation_report(policy_input=_valid_policy_input(), config=_config())

    report_path = write_data_validation_report(tmp_path, report)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert report_path.name == "data_validation_report.json"
    assert payload["status"] == "pass"
    assert any(table["table"] == "policy_input" for table in payload["tables"])
