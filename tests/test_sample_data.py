from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine.projection import load_policy_data, validate_policy_data
from model.config_model import ConfigModel


def test_sample_policy_input_validates(repo_root: Path):
    cfg = ConfigModel()
    sample_path = repo_root / "data" / "sample" / "sample_policies.csv"
    df = load_policy_data(str(sample_path), cfg)
    assert not df.empty
    assert {"policy_id", "issue_age", "sum_assured", "coverage_years"}.issubset(df.columns)


def test_sample_policy_validation_rejects_duplicates():
    cfg = ConfigModel()
    df = pd.DataFrame(
        {
            "policy_id": [1, 1],
            "issue_age": [25, 30],
            "sum_assured": [50000, 60000],
            "coverage_years": [10, 10],
        }
    )
    with pytest.raises(ValueError):
        validate_policy_data(df, cfg)
