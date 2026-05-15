from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import pandas as pd


def _json_ready(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def config_snapshot(config: Any) -> dict[str, Any]:
    """Return a deterministic assumption snapshot for audit output."""
    if config is None:
        return {}
    if hasattr(config, "model_dump"):
        data = config.model_dump(mode="json")
    elif hasattr(config, "dict"):
        data = config.dict()
    else:
        data = dict(vars(config))
    return {str(k): _json_ready(v) for k, v in sorted(data.items())}


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    import json

    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _df_shape(df: Optional[pd.DataFrame]) -> dict[str, int]:
    if df is None:
        return {"rows": 0, "columns": 0}
    return {"rows": int(df.shape[0]), "columns": int(df.shape[1])}


def build_audit_report(
    *,
    config: Any,
    projection: pd.DataFrame,
    master: pd.DataFrame,
    bel_result: Optional[pd.DataFrame],
    ra_result: Optional[pd.DataFrame],
    csm_result: Optional[pd.DataFrame],
    scenario_results: Optional[pd.DataFrame],
    group_result: Optional[pd.DataFrame],
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    assumptions = config_snapshot(config)
    run_id = run_id or uuid4().hex

    totals: dict[str, Any] = {}
    if bel_result is not None and "bel_per_policy" in bel_result.columns:
        totals["total_bel"] = float(bel_result["bel_per_policy"].sum())
    if ra_result is not None and "ra_per_policy" in ra_result.columns:
        totals["total_ra"] = float(ra_result["ra_per_policy"].sum())
    if csm_result is not None:
        for col in ("csm_opening", "csm_closing", "onerous_loss"):
            if col in csm_result.columns:
                totals[f"total_{col}"] = float(csm_result[col].sum())

    return {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "assumption_hash": snapshot_hash(assumptions),
        "methodology_version": assumptions.get("methodology_version"),
        "approval_status": assumptions.get("approval_status"),
        "locked_in_discount_rate": assumptions.get("locked_in_discount_rate"),
        "data_lineage": {
            "config_path": "config/config.json",
            "mortality_table_path": assumptions.get("mortality_table_path"),
            "output_path": assumptions.get("output_path"),
        },
        "assumptions": assumptions,
        "row_counts": {
            "master": _df_shape(master),
            "projection": _df_shape(projection),
            "bel": _df_shape(bel_result),
            "ra": _df_shape(ra_result),
            "csm": _df_shape(csm_result),
            "groups": _df_shape(group_result),
            "scenarios": _df_shape(scenario_results),
        },
        "reconciliation_totals": totals,
    }
