#!/usr/bin/env python
import argparse
import time
import tracemalloc

from engine.assumptions import loadconfig
from engine.cashflows import calculate_cashflows
from engine.csm import calculate_csm_rollforward
from engine.curves import create_discount_curve
from engine.grouping import assign_ifrs17_groups
from engine.projection import create_master_data, create_projection_table, load_mortality_table
from engine.ra import calculate_risk_adjustment
from engine.bel import calculate_bel


def run_benchmark(policies: int, projection_years: int) -> dict:
    config = loadconfig("config/config.json")
    if hasattr(config, "model_copy"):
        config = config.model_copy(
            update={
                "n_policies": policies,
                "projection_years": projection_years,
                "run_scenarios": False,
                "excel_output": False,
            }
        )
    else:
        config.n_policies = policies
        config.projection_years = projection_years
        config.run_scenarios = False
        config.excel_output = False

    mortality_table = (
        load_mortality_table(config.mortality_table_path) if config.use_mortality_table else None
    )

    start = time.perf_counter()
    tracemalloc.start()

    master = create_master_data(config)
    projection = create_projection_table(master, config, mortality_table)
    curve = create_discount_curve(config)
    projection = projection.merge(curve, on="Year", how="left")
    projection = calculate_cashflows(projection, config)
    bel = calculate_bel(projection, config)
    ra = calculate_risk_adjustment(projection, config)
    csm = calculate_csm_rollforward(bel, ra, projection, config)
    groups = assign_ifrs17_groups(csm, projection, config)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = time.perf_counter() - start

    return {
        "policies": policies,
        "projection_years": projection_years,
        "runtime_sec": elapsed,
        "peak_memory_mb": peak / (1024 * 1024),
        "projection_rows": len(projection),
        "total_bel": float(bel["bel_per_policy"].sum()),
        "total_ra": float(ra["ra_per_policy"].sum()) if "ra_per_policy" in ra.columns else None,
        "total_csm_opening": (
            float(csm["csm_opening"].sum()) if "csm_opening" in csm.columns else None
        ),
        "group_rows": len(groups),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark IFRS 17 Term Life Engine")
    parser.add_argument("--policies", type=int, nargs="*", default=[10000, 50000, 100000])
    parser.add_argument("--projection-years", type=int, default=10)
    args = parser.parse_args()

    results = [run_benchmark(p, args.projection_years) for p in args.policies]

    print(
        "Policies,ProjectionYears,RuntimeSec,PeakMemoryMB,ProjectionRows,TotalBEL,TotalRA,TotalCSMOpening,GroupRows"
    )
    for r in results:
        print(
            f"{r['policies']},{r['projection_years']},{r['runtime_sec']:.2f},"
            f"{r['peak_memory_mb']:.2f},{r['projection_rows']},{r['total_bel']:.2f},"
            f"{r['total_ra']},{r['total_csm_opening']},{r['group_rows']}"
        )


if __name__ == "__main__":
    main()
