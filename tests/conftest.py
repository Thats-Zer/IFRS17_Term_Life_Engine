from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from engine.asumptions import loadconfig
from engine.projection import load_mortality_table


def _config_copy_with_updates(cfg: Any, updates: Dict[str, Any]) -> Any:
    if hasattr(cfg, "model_copy"):
        return cfg.model_copy(update=updates)  # pydantic v2
    if hasattr(cfg, "copy"):
        try:
            return cfg.copy(update=updates)  # pydantic v1
        except TypeError:
            pass
    for k, v in updates.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def mortality_table(repo_root: Path):
    # Prod koduyla aynı şekilde oku (sep/kolon isimleri doğru gelsin)
    return load_mortality_table(str(repo_root / "data" / "mortality_table.csv"))


@pytest.fixture(scope="session")
def config_small(repo_root: Path):
    cfg = loadconfig(str(repo_root / "config" / "config.json"))

    updates: Dict[str, Any] = {"n_policies": 200, "projection_years": 10}
    if hasattr(cfg, "run_scenarios"):
        updates["run_scenarios"] = False
    if hasattr(cfg, "scenario_max_workers"):
        updates["scenario_max_workers"] = 1
    if hasattr(cfg, "random_seed"):
        updates["random_seed"] = 42

    return _config_copy_with_updates(cfg, updates)