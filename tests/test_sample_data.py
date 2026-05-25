from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine.projection import create_master_data, load_mortality_table, load_policy_data
from model.config_model import ConfigModel


def _write_policy_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "policies.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _valid_policy_rows() -> list[dict]:
    return [
        {
            "policy_id": 1,
            "issue_age": 35,
            "sum_assured": 50000,
            "coverage_years": 10,
        },
        {
            "policy_id": 2,
            "issue_age": 45,
            "sum_assured": 75000,
            "coverage_years": 8,
        },
    ]


def _write_mortality_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "mortality.csv"
    pd.DataFrame(rows).to_csv(path, sep=";", index=False)
    return path


def test_sample_policy_input_validates(repo_root: Path):
    cfg = ConfigModel()
    sample_path = repo_root / "data" / "sample" / "sample_policies.csv"
    df = load_policy_data(str(sample_path), cfg)
    assert not df.empty
    assert {"policy_id", "issue_age", "sum_assured", "coverage_years"}.issubset(df.columns)


def test_valid_sample_policy_input_loads_successfully(tmp_path: Path):
    cfg = ConfigModel()
    policy_path = _write_policy_csv(tmp_path, _valid_policy_rows())

    df = load_policy_data(str(policy_path), cfg)

    assert len(df) == 2
    assert df["policy_id"].tolist() == [1, 2]
    assert {"issue_year", "portfolio_id"}.issubset(df.columns)


def test_sample_policy_input_missing_required_columns_raises_value_error(tmp_path: Path):
    cfg = ConfigModel()
    rows = [{"policy_id": 1, "issue_age": 35, "coverage_years": 10}]
    policy_path = _write_policy_csv(tmp_path, rows)

    with pytest.raises(ValueError, match="missing required columns"):
        load_policy_data(str(policy_path), cfg)


def test_sample_policy_input_duplicate_policy_id_raises_value_error(tmp_path: Path):
    cfg = ConfigModel()
    rows = _valid_policy_rows()
    rows[1]["policy_id"] = rows[0]["policy_id"]
    policy_path = _write_policy_csv(tmp_path, rows)

    with pytest.raises(ValueError, match="Duplicate policy_id"):
        load_policy_data(str(policy_path), cfg)


def test_sample_policy_input_negative_sum_assured_raises_value_error(tmp_path: Path):
    cfg = ConfigModel()
    rows = _valid_policy_rows()
    rows[0]["sum_assured"] = -1
    policy_path = _write_policy_csv(tmp_path, rows)

    with pytest.raises(ValueError, match="sum_assured must be non-negative"):
        load_policy_data(str(policy_path), cfg)


def test_sample_policy_input_invalid_issue_age_raises_value_error(tmp_path: Path):
    cfg = ConfigModel()
    rows = _valid_policy_rows()
    rows[0]["issue_age"] = cfg.max_issue_age + 1
    policy_path = _write_policy_csv(tmp_path, rows)

    with pytest.raises(ValueError, match="issue_age out of configured range"):
        load_policy_data(str(policy_path), cfg)


def test_sample_policy_input_non_positive_coverage_years_raises_value_error(tmp_path: Path):
    cfg = ConfigModel()
    rows = _valid_policy_rows()
    rows[0]["coverage_years"] = 0
    policy_path = _write_policy_csv(tmp_path, rows)

    with pytest.raises(ValueError, match="coverage_years must be positive"):
        load_policy_data(str(policy_path), cfg)


def test_valid_sample_mortality_table_loads_successfully(tmp_path: Path):
    mortality_path = _write_mortality_csv(
        tmp_path,
        [
            {"age": 30, "qx": 0.001},
            {"age": 31, "qx": 0.002},
        ],
    )

    table = load_mortality_table(str(mortality_path))

    assert table["age"].tolist() == [30, 31]
    assert table["qx"].between(0, 1).all()


def test_sample_mortality_table_qx_outside_range_raises_value_error(tmp_path: Path):
    mortality_path = _write_mortality_csv(
        tmp_path,
        [
            {"age": 30, "qx": 0.001},
            {"age": 31, "qx": 1.2},
        ],
    )

    with pytest.raises(ValueError, match=r"qx.*\[0, 1\]"):
        load_mortality_table(str(mortality_path))


def test_sample_mortality_table_missing_rate_column_raises_value_error(tmp_path: Path):
    mortality_path = _write_mortality_csv(
        tmp_path,
        [
            {"age": 30, "not_qx": 0.001},
            {"age": 31, "not_qx": 0.002},
        ],
    )

    with pytest.raises(ValueError, match="mortalite oran"):
        load_mortality_table(str(mortality_path))


def test_synthetic_master_data_path_still_works_without_sample_policy_file():
    cfg = ConfigModel(n_policies=3, projection_years=5, coverage_years=5, random_seed=123)

    master = create_master_data(cfg)

    assert len(master) == 3
    assert {"policy_id", "issue_age", "sum_assured", "coverage_years"}.issubset(master.columns)
    assert master["policy_id"].tolist() == [1, 2, 3]
    assert (master["sum_assured"] >= 0).all()
