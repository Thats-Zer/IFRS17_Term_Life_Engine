from typing import Tuple, Optional, Dict, Any #Bu modül, fonksiyon tiplerini belirtmek için kullanılır. 

import pandas as pd #Pandas, veri manipülasyonu ve analizi için kullanılan bir kütüphanedir. DataFrame yapısı sağlar.

import numpy as np #Numpy, sayısal hesaplamalar için kullanılan bir kütüphanedir. Diziler ve matrisler üzerinde işlem yapmayı sağlar.

import logging #Logging, uygulama içinde loglama yapmak için kullanılan bir modüldür. Hata ayıklama ve izleme için kullanılır.

from model.config_model import ModelConfig #ModelConfig, model yapılandırması için kullanılan bir sınıftır. Model parametrelerini içerir.

logger = logging.getLogger(__name__) #Logger, bu modül için bir logger nesnesi oluşturur. Loglama işlemleri bu nesne üzerinden yapılır.

# ==================================================
# MODULE-LEVEL STORAGE FOR BEL DIAGNOSTICS
# ==================================================
# Stores the most recent BEL diagnostic summary for retrieval by outputs/audit modules

_last_bel_diagnostic_summary: Optional[Dict[str, Any]] = None


def get_last_bel_diagnostic_summary() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recent BEL diagnostic summary (if diagnostics were enabled).
    
    Returns None if no diagnostic summary has been built yet or if diagnostics
    are disabled.
    
    Returns:
        dict or None: Dictionary containing BEL diagnostic metrics.
    """
    return _last_bel_diagnostic_summary


# ==================================================
# BEL CALCULATION (BEST ESTIMATE LIABILITY)
# ==================================================

def calculate_bel(
    projection: pd.DataFrame,
    config: ModelConfig, #bel hesaplama için gerekli yapılandırma parametrelerini içeren ModelConfig içeri alınır.
    run_type: str = "base",
    scenario_name: Optional[str] = None,
) -> pd.DataFrame:
    """
    IFRS 17 Best Estimate Liability (BEL) hesapla.

    BEL sign convention:
    - Liability-positive convention is used:
      BEL = PV(Outflows) - PV(Inflows)
    - If BEL > 0, the policy/group behaves like a net liability.
    - If BEL < 0, premium inflows exceed the discounted liability outflows
      and the policy behaves asset-like at BEL level.

    Timing convention:
    - Premium inflows and reinsurance ceding premiums are discounted with
      discount_factor_opening (period start).
    - Claims, surrender benefits, operating expenses, reinsurance recoveries,
      and counterparty default costs are discounted with discount_factor
      (period end).

        Reconciliation:
    - The function returns a full per-policy breakdown so that:
      bel_per_policy = pv_bel_outflows - pv_bel_inflows
    - This makes BEL explainable and easier to reconcile with cashflows.py.

        Note:
        - Module-level diagnostic storage is convenient, but it is risky when the
            same Python process evaluates multiple runs. Base diagnostics should be
            captured immediately after the base BEL calculation if they will be
            exported later.

    Preference order:
    - Use already-calculated cashflow / PV columns from engine.cashflows
      whenever they exist.
    - Only fall back to documented legacy calculations if the relevant cashflow
      column is missing.

    Returns at least:
    - policy_id
    - bel_per_policy
    - pv_bel_outflows
    - pv_bel_inflows
    - pv_claims
    - pv_surrender_benefits
    - pv_expenses
    - pv_reinsurance_ceding
    - pv_reinsurance_recovery
    - pv_counterparty_default_cost
    - pv_premiums
    """

    projection = projection.copy()
    float_dtype = np.float64 if bool(getattr(config, "use_float64", False)) else np.float32
    tolerance = np.float64(1e-6) if float_dtype == np.float64 else np.float32(1e-4)

    if "policy_id" not in projection.columns:
        raise ValueError("BEL için zorunlu sütun eksik: policy_id")

    def _require_column(column_name: str, purpose: str) -> None:
        if column_name not in projection.columns:
            raise ValueError(f"BEL için eksik sütun: '{column_name}' ({purpose})")

    def _pv_from_raw(raw_col: str, discount_col: str, output_col: str) -> pd.Series:
        _require_column(raw_col, f"{output_col} hesaplamak için gerekli ham cashflow")
        _require_column(discount_col, f"{output_col} hesaplamak için gerekli iskonto faktörü")
        return (projection[raw_col].astype(float_dtype) * projection[discount_col].astype(float_dtype)).astype(float_dtype)

    def _direct_or_discounted(
        *,
        pv_candidates: tuple[str, ...],
        raw_candidates: tuple[str, ...],
        discount_col: str,
        output_col: str,
        purpose: str,
    ) -> pd.Series:
        for candidate in pv_candidates:
            if candidate in projection.columns:
                return projection[candidate].astype(float_dtype)

        for candidate in raw_candidates:
            if candidate in projection.columns:
                return _pv_from_raw(candidate, discount_col, output_col)

        raise ValueError(
            f"BEL için gerekli cashflow sütunu bulunamadı: {output_col} / {purpose}. "
            f"Beklenen adaylar: {list(pv_candidates) + list(raw_candidates)}"
        )

    # Timing convention: opening DF for premiums / ceded premiums.
    # If direct PV columns already exist from cashflows.py, reuse them.
    if "discount_factor_opening" not in projection.columns:
        projection["discount_factor_opening"] = projection.get("discount_factor")
    _require_column("discount_factor", "closing timing PV hesapları için gerekli")

    # Premium inflows (opening timing)
    pv_premiums = _direct_or_discounted(
        pv_candidates=("PV_Gross_Premium_Inflow", "pv_premiums"),
        raw_candidates=("Gross_Premium_Inflow",),
        discount_col="discount_factor_opening",
        output_col="pv_premiums",
        purpose="premium inflow",
    )

    # Claims / death benefits (closing timing)
    if "PV_Death_Benefits" in projection.columns:
        pv_claims = projection["PV_Death_Benefits"].astype(float_dtype)
    elif "Death_Benefits" in projection.columns:
        pv_claims = _pv_from_raw("Death_Benefits", "discount_factor", "pv_claims")
    elif "Net_Death_Benefit" in projection.columns and "Reinsurance_Recovery" in projection.columns:
        # Documented fallback: if only net death benefit exists, reconstruct gross claims
        # as Net_Death_Benefit + Reinsurance_Recovery so that the BEL breakdown remains
        # fully explainable and the recovery remains shown separately.
        projection["pv_claims"] = (
            (projection["Net_Death_Benefit"].astype(float_dtype) + projection["Reinsurance_Recovery"].astype(float_dtype))
            * projection["discount_factor"].astype(float_dtype)
        ).astype(float_dtype)
        pv_claims = projection["pv_claims"]
    elif "Adjusted_Death_Benefits" in projection.columns:
        pv_claims = _pv_from_raw("Adjusted_Death_Benefits", "discount_factor", "pv_claims")
    else:
        required = ["Death_Benefits", "Net_Death_Benefit", "Adjusted_Death_Benefits"]
        raise ValueError(
            "BEL için claims cashflow bulunamadı. "
            f"Adaylar: {required}. cashflows.py çıktısı eksik olabilir."
        )

    # Surrender benefits (closing timing)
    if "PV_Surrender_Benefit" in projection.columns:
        pv_surrender_benefits = projection["PV_Surrender_Benefit"].astype(float_dtype)
    elif "Surrender_Benefit" in projection.columns:
        pv_surrender_benefits = _pv_from_raw("Surrender_Benefit", "discount_factor", "pv_surrender_benefits")
    elif "adjusted_surrender_benefit" in projection.columns:
        pv_surrender_benefits = _pv_from_raw("adjusted_surrender_benefit", "discount_factor", "pv_surrender_benefits")
    else:
        raise ValueError("BEL için eksik sütun: Surrender_Benefit / adjusted_surrender_benefit")

    # Operating expenses (closing timing)
    if "PV_Operating_Expenses" in projection.columns:
        pv_expenses = projection["PV_Operating_Expenses"].astype(float_dtype)
    elif "Operating_Expenses" in projection.columns:
        pv_expenses = _pv_from_raw("Operating_Expenses", "discount_factor", "pv_expenses")
    else:
        raise ValueError("BEL için eksik sütun: Operating_Expenses")

    # Reinsurance ceding (opening timing)
    if "PV_Reinsurance_Ceding" in projection.columns:
        pv_reinsurance_ceding = projection["PV_Reinsurance_Ceding"].astype(float_dtype)
    elif "Reinsurance_Ceding" in projection.columns:
        pv_reinsurance_ceding = _pv_from_raw("Reinsurance_Ceding", "discount_factor_opening", "pv_reinsurance_ceding")
    else:
        re_rate = float(getattr(config, "reinsurance_cost_rate", 0.0) or 0.0)
        if re_rate <= 0:
            raise ValueError("BEL için eksik sütun: Reinsurance_Ceding (ve config.reinsurance_cost_rate <= 0)")
        if "Gross_Premium_Inflow" not in projection.columns:
            raise ValueError("Reinsurance_Ceding fallback için Gross_Premium_Inflow gerekli")
        pv_reinsurance_ceding = (
            projection["Gross_Premium_Inflow"].astype(float_dtype)
            * projection["discount_factor_opening"].astype(float_dtype)
            * np.float32(re_rate)
        ).astype(float_dtype)

    # Reinsurance recovery (closing timing)
    if "PV_Reinsurance_Recovery" in projection.columns:
        pv_reinsurance_recovery = projection["PV_Reinsurance_Recovery"].astype(float_dtype)
    elif "Reinsurance_Recovery" in projection.columns:
        pv_reinsurance_recovery = _pv_from_raw("Reinsurance_Recovery", "discount_factor", "pv_reinsurance_recovery")
    else:
        re_rate = float(getattr(config, "reinsurance_cost_rate", 0.0) or 0.0)
        if re_rate <= 0:
            raise ValueError("BEL için eksik sütun: Reinsurance_Recovery (ve config.reinsurance_cost_rate <= 0)")
        if "Death_Benefits" not in projection.columns and "Adjusted_Death_Benefits" not in projection.columns:
            raise ValueError("Reinsurance_Recovery fallback için Death_Benefits veya Adjusted_Death_Benefits gerekli")
        death_base = projection["Death_Benefits"] if "Death_Benefits" in projection.columns else projection["Adjusted_Death_Benefits"]
        pv_reinsurance_recovery = (
            death_base.astype(float_dtype)
            * np.float32(re_rate)
            * projection["discount_factor"].astype(float_dtype)
        ).astype(float_dtype)

    # Counterparty default cost (closing timing)
    if "PV_Counterparty_Default_Cost" in projection.columns:
        pv_counterparty_default_cost = projection["PV_Counterparty_Default_Cost"].astype(float_dtype)
    elif "Counterparty_Default_Cost" in projection.columns:
        pv_counterparty_default_cost = _pv_from_raw("Counterparty_Default_Cost", "discount_factor", "pv_counterparty_default_cost")
    else:
        pd_default = float(getattr(config, "counterparty_pd", 0.0) or 0.0)
        lgd_default = float(getattr(config, "counterparty_lgd", 0.0) or 0.0)
        if pd_default <= 0 or lgd_default <= 0:
            raise ValueError("BEL için eksik sütun: Counterparty_Default_Cost (ve config.counterparty_pd/lgd <= 0)")
        pv_counterparty_default_cost = (
            pv_reinsurance_recovery.astype(float_dtype)
            * np.float32(pd_default)
            * np.float32(lgd_default)
        ).astype(float_dtype)

    # BEL breakdown per policy, using liability-positive convention.
    projection["pv_claims"] = pv_claims.astype(float_dtype)
    projection["pv_surrender_benefits"] = pv_surrender_benefits.astype(float_dtype)
    projection["pv_expenses"] = pv_expenses.astype(float_dtype)
    projection["pv_reinsurance_ceding"] = pv_reinsurance_ceding.astype(float_dtype)
    projection["pv_reinsurance_recovery"] = pv_reinsurance_recovery.astype(float_dtype)
    projection["pv_counterparty_default_cost"] = pv_counterparty_default_cost.astype(float_dtype)
    projection["pv_premiums"] = pv_premiums.astype(float_dtype)

    projection["pv_bel_outflows"] = (
        projection["pv_claims"]
        + projection["pv_surrender_benefits"]
        + projection["pv_expenses"]
        + projection["pv_reinsurance_ceding"]
        + projection["pv_counterparty_default_cost"]
    ).astype(float_dtype)

    projection["pv_bel_inflows"] = (
        projection["pv_premiums"]
        + projection["pv_reinsurance_recovery"]
    ).astype(float_dtype)

    projection["bel_per_policy"] = (
        projection["pv_bel_outflows"]
        - projection["pv_bel_inflows"]
    ).astype(float_dtype)

    # Optional compatibility alias for CSM / older downstream logic.
    projection["pv_death_benefits"] = projection["pv_claims"].astype(float_dtype)

    # Reconciliation check: BEL must equal outflows - inflows per policy.
    projection["bel_reconciliation_diff"] = (
        projection["bel_per_policy"]
        - (projection["pv_bel_outflows"] - projection["pv_bel_inflows"])
    ).astype(float_dtype)

    max_diff = float(np.abs(projection["bel_reconciliation_diff"].to_numpy(dtype=np.float64)).max(initial=0.0))
    if max_diff > float(tolerance):
        raise ValueError(
            f"BEL reconciliation failed: max diff={max_diff:.10f}, tolerance={float(tolerance):.10f}"
        )

    agg_map: dict[str, str] = {
        "bel_per_policy": "first",
        "pv_bel_outflows": "first",
        "pv_bel_inflows": "first",
        "pv_claims": "first",
        "pv_surrender_benefits": "first",
        "pv_expenses": "first",
        "pv_reinsurance_ceding": "first",
        "pv_reinsurance_recovery": "first",
        "pv_counterparty_default_cost": "first",
        "pv_premiums": "first",
        "pv_death_benefits": "first",
        "bel_reconciliation_diff": "first",
    }

    for extra in ("sum_assured", "coverage_years", "issue_age"):
        if extra in projection.columns:
            agg_map[extra] = "first"

    bel_result = (
        projection
        .groupby("policy_id", sort=False, as_index=False)
        .agg(agg_map)
    )

    bel_result["bel_sign_explanation"] = np.where(
        bel_result["bel_per_policy"] > 0,
        "Liability: PV outflows exceed PV inflows",
        "Asset-like: PV inflows exceed PV outflows",
    )

    # Keep the public interface clean and predictable.
    desired_order = [
        "policy_id",
        "bel_per_policy",
        "pv_bel_outflows",
        "pv_bel_inflows",
        "pv_claims",
        "pv_surrender_benefits",
        "pv_expenses",
        "pv_reinsurance_ceding",
        "pv_reinsurance_recovery",
        "pv_counterparty_default_cost",
        "pv_premiums",
        "pv_death_benefits",
        "bel_reconciliation_diff",
        "bel_sign_explanation",
    ]
    trailing_cols = [c for c in ("sum_assured", "coverage_years", "issue_age") if c in bel_result.columns]
    bel_result = bel_result[[c for c in desired_order if c in bel_result.columns] + trailing_cols]

    total_bel = float(bel_result["bel_per_policy"].sum())
    avg_bel = float(bel_result["bel_per_policy"].mean())
    asset_count = int((bel_result["bel_per_policy"] < 0).sum())
    liability_count = int((bel_result["bel_per_policy"] > 0).sum())

    logger.info(
        "✓ BEL hesaplandı (liability-positive): Total=%s, Avg=%s, Liability policies=%s, Asset-like policies=%s",
        f"{total_bel:,.2f}",
        f"{avg_bel:,.2f}",
        liability_count,
        asset_count,
    )

    if asset_count > 0:
        logger.info("ℹ %s poliçede net asset (BEL < 0) oluştu", asset_count)

    # Generate diagnostic BEL summary report (if enabled in config)
    enable_diagnostics = bool(getattr(config, "enable_bel_diagnostics", True))
    if enable_diagnostics:
        diagnostic_summary = build_bel_diagnostic_summary(
            bel_result,
            max_diff,
            float_dtype,
            run_type=run_type,
            scenario_name=scenario_name,
        )
        _report_bel_diagnostics(diagnostic_summary)

    return bel_result


# ==================================================
# BEL DIAGNOSTIC REPORTING
# ==================================================

def build_bel_diagnostic_summary(
    bel_result: pd.DataFrame,
    max_reconciliation_diff: float,
    float_dtype,
    run_type: str = "base",
    scenario_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a structured dictionary containing comprehensive BEL diagnostic metrics.

    This function aggregates all BEL diagnostics into a single structured output
    that can be logged, exported as JSON, or saved to audit reports.

    Args:
        bel_result: Output from calculate_bel()
        max_reconciliation_diff: Maximum absolute reconciliation difference
        float_dtype: numpy dtype (float32 or float64)
        run_type: Diagnostic context, typically "base" or "scenario"
        scenario_name: Scenario name when run_type == "scenario"

    Returns:
        dict: Comprehensive BEL diagnostic summary with keys:
            - total_bel, total_pv_outflows, total_pv_inflows
            - reconciliation_difference, max_abs_reconciliation_diff
            - total_policies, liability_like_count, asset_like_count, break_even_count
            - liability_like_percentage, asset_like_percentage, break_even_percentage
            - component_totals: dict with keys for claims, expenses, premiums, etc.
            - average_components_by_sign: dict with liability and asset subkeys
            - top_liability_policies: list of dicts (top 10 by positive BEL)
            - top_asset_policies: list of dicts (top 10 by negative BEL)
    """

    global _last_bel_diagnostic_summary

    # ==================================================
    # BASIC TOTALS
    # ==================================================

    total_bel = float(bel_result["bel_per_policy"].sum())
    total_outflows = float(bel_result["pv_bel_outflows"].sum())
    total_inflows = float(bel_result["pv_bel_inflows"].sum())
    reconciliation = total_outflows - total_inflows

    # ==================================================
    # POLICY COUNTS AND PERCENTAGES
    # ==================================================

    total_policies = len(bel_result)
    liability_count = int((bel_result["bel_per_policy"] > 0).sum())
    asset_count = int((bel_result["bel_per_policy"] < 0).sum())
    breakeven_count = int((bel_result["bel_per_policy"] == 0).sum())

    liability_pct = 100.0 * liability_count / total_policies if total_policies > 0 else 0.0
    asset_pct = 100.0 * asset_count / total_policies if total_policies > 0 else 0.0
    breakeven_pct = 100.0 * breakeven_count / total_policies if total_policies > 0 else 0.0

    # ==================================================
    # COMPONENT TOTALS
    # ==================================================

    component_totals = {}
    component_cols = ["pv_claims", "pv_expenses", "pv_surrender_benefits", "pv_counterparty_default_cost", "pv_reinsurance_ceding", "pv_premiums", "pv_reinsurance_recovery"]
    for col in component_cols:
        if col in bel_result.columns:
            component_totals[col] = float(bel_result[col].sum())

    # ==================================================
    # AVERAGE COMPONENTS BY BEL SIGN
    # ==================================================

    average_components = {"liability_like": {}, "asset_like": {}}

    if liability_count > 0:
        liability_subset = bel_result[bel_result["bel_per_policy"] > 0]
        for col in ["pv_claims", "pv_premiums", "pv_expenses"]:
            if col in liability_subset.columns:
                average_components["liability_like"][col] = float(liability_subset[col].mean())

    if asset_count > 0:
        asset_subset = bel_result[bel_result["bel_per_policy"] < 0]
        for col in ["pv_claims", "pv_premiums", "pv_expenses"]:
            if col in asset_subset.columns:
                average_components["asset_like"][col] = float(asset_subset[col].mean())

    # ==================================================
    # TOP POLICIES
    # ==================================================

    top_liability_list = []
    top_liability_policies = bel_result.nlargest(10, "bel_per_policy")
    for idx, row in top_liability_policies.iterrows():
        top_liability_list.append({
            "policy_id": int(row["policy_id"]),
            "bel_per_policy": float(row["bel_per_policy"]),
            "pv_bel_outflows": float(row["pv_bel_outflows"]),
            "pv_bel_inflows": float(row["pv_bel_inflows"]),
        })

    top_asset_list = []
    top_asset_policies = bel_result.nsmallest(10, "bel_per_policy")
    for idx, row in top_asset_policies.iterrows():
        top_asset_list.append({
            "policy_id": int(row["policy_id"]),
            "bel_per_policy": float(row["bel_per_policy"]),
            "pv_bel_outflows": float(row["pv_bel_outflows"]),
            "pv_bel_inflows": float(row["pv_bel_inflows"]),
        })

    # ==================================================
    # BUILD SUMMARY DICTIONARY
    # ==================================================

    summary = {
        "run_type": run_type,
        "scenario_name": scenario_name,
        "diagnostic_source": "calculate_bel",
        "bel_convention": "liability_positive",
        "formula": "BEL = PV(outflows) - PV(inflows)",
        "total_bel": total_bel,
        "total_pv_outflows": total_outflows,
        "total_pv_inflows": total_inflows,
        "reconciliation_difference": reconciliation,
        "max_abs_reconciliation_diff": max_reconciliation_diff,
        "total_policies": total_policies,
        "liability_like_count": liability_count,
        "asset_like_count": asset_count,
        "break_even_count": breakeven_count,
        "liability_like_percentage": liability_pct,
        "asset_like_percentage": asset_pct,
        "break_even_percentage": breakeven_pct,
        "component_totals": component_totals,
        "average_components_by_sign": average_components,
        "top_liability_policies": top_liability_list,
        "top_asset_policies": top_asset_list,
        "float_dtype": "float64" if float_dtype == np.float64 else "float32",
    }

    # Store globally for retrieval by outputs/audit modules
    _last_bel_diagnostic_summary = summary

    return summary


def _report_bel_diagnostics(diagnostic_summary: Dict[str, Any]) -> None:
    """
    Generate and log comprehensive BEL diagnostic summary using pre-computed dictionary.

    Logs:
    - Total and policy counts by sign
    - PV component totals (outflows, inflows)
    - Top 10 policies by positive/negative BEL
    - Average component values by BEL sign
    - Reconciliation status

    Args:
        diagnostic_summary: Pre-computed summary dict from build_bel_diagnostic_summary()
    """

    logger.info("=" * 80)
    logger.info("BEL DIAGNOSTIC SUMMARY REPORT")
    logger.info("=" * 80)

    # ==================================================
    # TOTALS AND COUNTS
    # ==================================================

    logger.info("SUMMARY TOTALS:")
    logger.info("  Total BEL (liability-positive): %s", f"{diagnostic_summary['total_bel']:,.2f}")
    logger.info("  Total PV Outflows: %s", f"{diagnostic_summary['total_pv_outflows']:,.2f}")
    logger.info("  Total PV Inflows: %s", f"{diagnostic_summary['total_pv_inflows']:,.2f}")
    logger.info("  BEL Reconciliation: %s", f"{diagnostic_summary['reconciliation_difference']:,.2f}")

    logger.info("POLICY COUNTS:")
    logger.info("  Total Policies: %d", diagnostic_summary['total_policies'])
    logger.info("  Liability-like (BEL > 0): %d (%.1f%%)", 
                diagnostic_summary['liability_like_count'],
                diagnostic_summary['liability_like_percentage'])
    logger.info("  Asset-like (BEL < 0): %d (%.1f%%)",
                diagnostic_summary['asset_like_count'],
                diagnostic_summary['asset_like_percentage'])
    logger.info("  Break-even (BEL = 0): %d (%.1f%%)",
                diagnostic_summary['break_even_count'],
                diagnostic_summary['break_even_percentage'])

    # ==================================================
    # COMPONENT PV TOTALS
    # ==================================================

    logger.info("COMPONENT PV TOTALS (Outflows):")
    for col in ["pv_claims", "pv_expenses", "pv_surrender_benefits", "pv_counterparty_default_cost", "pv_reinsurance_ceding"]:
        if col in diagnostic_summary['component_totals']:
            logger.info("  %s: %s", col, f"{diagnostic_summary['component_totals'][col]:,.2f}")

    logger.info("COMPONENT PV TOTALS (Inflows):")
    for col in ["pv_premiums", "pv_reinsurance_recovery"]:
        if col in diagnostic_summary['component_totals']:
            logger.info("  %s: %s", col, f"{diagnostic_summary['component_totals'][col]:,.2f}")

    # ==================================================
    # TOP 10 POLICIES BY BEL SIGN
    # ==================================================

    logger.info("TOP 10 POLICIES - HIGHEST POSITIVE BEL (Liability-like):")
    if len(diagnostic_summary['top_liability_policies']) > 0:
        for policy in diagnostic_summary['top_liability_policies']:
            logger.info(
                "  Policy %s: BEL=%s, Outflows=%s, Inflows=%s",
                policy['policy_id'],
                f"{policy['bel_per_policy']:,.2f}",
                f"{policy['pv_bel_outflows']:,.2f}",
                f"{policy['pv_bel_inflows']:,.2f}",
            )
    else:
        logger.info("  (No positive BEL policies)")

    logger.info("TOP 10 POLICIES - LOWEST NEGATIVE BEL (Asset-like):")
    if len(diagnostic_summary['top_asset_policies']) > 0:
        for policy in diagnostic_summary['top_asset_policies']:
            logger.info(
                "  Policy %s: BEL=%s, Outflows=%s, Inflows=%s",
                policy['policy_id'],
                f"{policy['bel_per_policy']:,.2f}",
                f"{policy['pv_bel_outflows']:,.2f}",
                f"{policy['pv_bel_inflows']:,.2f}",
            )
    else:
        logger.info("  (No negative BEL policies)")

    # ==================================================
    # AVERAGE COMPONENTS BY BEL SIGN
    # ==================================================

    logger.info("AVERAGE COMPONENTS BY BEL SIGN:")

    avg_by_sign = diagnostic_summary['average_components_by_sign']
    if len(avg_by_sign.get('liability_like', {})) > 0:
        logger.info("  Liability-like policies (avg):")
        for col, val in avg_by_sign['liability_like'].items():
            logger.info("    %s: %s", col, f"{val:,.2f}")
    else:
        logger.info("  Liability-like policies: (none)")

    if len(avg_by_sign.get('asset_like', {})) > 0:
        logger.info("  Asset-like policies (avg):")
        for col, val in avg_by_sign['asset_like'].items():
            logger.info("    %s: %s", col, f"{val:,.2f}")
    else:
        logger.info("  Asset-like policies: (none)")

    # ==================================================
    # RECONCILIATION CHECK
    # ==================================================

    logger.info("RECONCILIATION CHECK:")
    logger.info("  Max absolute reconciliation difference: %s", f"{diagnostic_summary['max_abs_reconciliation_diff']:.10e}")
    logger.info("  Precision mode: %s", diagnostic_summary['float_dtype'])

    max_diff = diagnostic_summary['max_abs_reconciliation_diff']
    if max_diff < 1e-5:
        logger.info("  ✓ Reconciliation passed (excellent precision)")
    elif max_diff < 1e-3:
        logger.info("  ✓ Reconciliation passed (good precision)")
    else:
        logger.warning("  ⚠ Reconciliation: check precision")

    logger.info("=" * 80)


# ==================================================
# BEL SENSITIVITY ANALYSIS
# ==================================================

# BEL'in duyarlılık analizi (mortalite, lapse, discount rate şokları).
def calculate_bel_sensitivity(
    projection: pd.DataFrame,
    config: ModelConfig,
    shock_scenarios: Optional[dict] = None
) -> pd.DataFrame:
    
    """
    BEL'in duyarlılık analizi (mortalite, lapse, discount rate şokları).
    
    Şok Senaryoları:
    1. Mortality +10%
    2. Lapse +20%
    3. Discount Rate -100 bps
    4. Combined shock
    
    Args:
        projection: Projection tablosu
        config: ModelConfig
        shock_scenarios: Custom şok senaryoları
        
    Returns:
        pd.DataFrame: Senaryo bazında BEL değerleri
    """
    
    # Default şok senaryoları
    if shock_scenarios is None:
        shock_scenarios = {
            # New-style keys (aligned with engine.scenarios.SCENARIOS)
            "base": {},
            "mortality_up_10": {"mortality_shock_multiplier": 1.10},
            "lapse_up_20": {"lapse_initial_rate_multiplier": 1.20},
            "rate_down_100bps": {"discount_rate_shift": -0.01},
        }
    
    sensitivity_results = [] #Her senaryo için BEL sonuçlarını depolamak için boş bir liste oluşturulur.
    
    # Her senaryo için BEL'i hesapla
    for scenario_name, shocks in shock_scenarios.items():
        proj_shock = projection.copy()

        # Backward-compatible interpretation of shocks:
        # - Prefer new-style keys used by engine.scenarios
        # - Fall back to legacy keys: mort_shock/lapse_shock/rate_shock
        scenario_updates: dict = {}

        if "discount_rate_shift" in shocks:
            scenario_updates["discount_rate_shift"] = float(shocks.get("discount_rate_shift") or 0.0)
        elif "rate_shock" in shocks:
            scenario_updates["discount_rate_shift"] = float(shocks.get("rate_shock") or 0.0)

        if "unit_expense_multiplier" in shocks:
            scenario_updates["unit_expense_multiplier"] = float(shocks.get("unit_expense_multiplier") or 1.0)

        # Config copy with scenario updates so that expense shocks apply in calculate_cashflows
        if hasattr(config, "model_copy"):
            cfg = config.model_copy(update=scenario_updates)
        else:
            from copy import deepcopy
            cfg = deepcopy(config)
            for k, v in scenario_updates.items():
                setattr(cfg, k, v)

        float_dtype = np.float64 if bool(getattr(cfg, "use_float64", False)) else np.float32

        # Mortality shock on qx (multiplier + optional additive)
        if "mortality_shock_multiplier" in shocks:
            mort_mult = float(shocks.get("mortality_shock_multiplier") or 1.0)
        else:
            mort_mult = 1.0 + float(shocks.get("mort_shock", 0.0) or 0.0)
        mort_add = float(shocks.get("mortality_shock", 0.0) or 0.0)

        # Lapse shock on lapse_rate (multiplier)
        if "lapse_initial_rate_multiplier" in shocks:
            lapse_mult = float(shocks.get("lapse_initial_rate_multiplier") or 1.0)
        else:
            lapse_mult = 1.0 + float(shocks.get("lapse_shock", 0.0) or 0.0)

        if "qx" in proj_shock.columns:
            proj_shock["qx"] = (proj_shock["qx"] * mort_mult + mort_add).clip(0, 1)
        if "lapse_rate" in proj_shock.columns:
            proj_shock["lapse_rate"] = (proj_shock["lapse_rate"] * lapse_mult).clip(0, 1)

        # Discount factors (flat rate curve assumption)
        effective_rate = float(cfg.discount_rate) + float(getattr(cfg, "discount_rate_shift", 0.0) or 0.0)
        if effective_rate <= -0.999:
            raise ValueError(f"discount_rate_shift çok büyük negatif: effective_rate={effective_rate}")

        v = 1.0 / (1.0 + effective_rate)
        t = proj_shock["Year"].astype(np.int32)
        proj_shock["discount_factor"] = (v ** t).astype(float_dtype)
        proj_shock["discount_factor_opening"] = (v ** (t - 1)).astype(float_dtype)

        # Recompute cashflows under shocked assumptions, then BEL
        from engine.cashflows import calculate_cashflows

        proj_shock = calculate_cashflows(proj_shock, cfg)
        bel_shock = calculate_bel(proj_shock, cfg)
        bel_shock["scenario"] = scenario_name
        
        sensitivity_results.append(bel_shock)
    
    # Tüm senaryo sonuçlarını birleştir
    sensitivity_df = pd.concat(sensitivity_results, ignore_index=True)
    
    # Loglama
    logger.info(f"✓ Sensitivity analysis tamamlandı: {len(shock_scenarios)} senaryo")
    
    return sensitivity_df #Senaryo bazında BEL sonuçlarını içeren DataFrame'i döndür.
