import logging
import sys
from pathlib import Path
from typing import Optional

from engine.assumptions import loadconfig
from engine.bel import calculate_bel
from engine.cashflows import calculate_cashflows
from engine.csm import calculate_csm_rollforward
from engine.curves import create_discount_curve
from engine.grouping import assign_ifrs17_groups
from engine.outputs import save_outputs
from engine.projection import create_master_data, create_projection_table, load_mortality_table
from engine.ra import calculate_risk_adjustment
from engine.scenarios import run_scenarios


def _configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_console_encoding()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("engine.log", encoding="utf-8", mode="w"),
    ],
    force=True,
)
logger = logging.getLogger(__name__)


class EngineException(Exception):
    def __init__(
        self,
        message: str,
        *,
        step: Optional[str] = None,
        original: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.step = step
        self.original = original

    def __str__(self) -> str:
        if self.step:
            return f"[{self.step}] {super().__str__()}"
        return super().__str__()


def handle_error(step_name: str, error: Exception) -> None:
    logger.error(
        "Step %s failed: %s: %s",
        step_name,
        type(error).__name__,
        str(error),
        exc_info=True,
    )


def validate_config(config) -> bool:
    if config.n_policies <= 0:
        raise ValueError("n_policies must be greater than 0")
    if config.projection_years <= 0:
        raise ValueError("projection_years must be greater than 0")
    if config.discount_rate < 0 or config.discount_rate > 1:
        raise ValueError("discount_rate must be between 0 and 1")

    logger.info("Config validated")
    return True


def main() -> None:
    success = False
    try:
        logger.info("=" * 70)
        logger.info("Starting IFRS 17 Term Life Engine")
        logger.info("=" * 70)

        try:
            logger.info("1. Loading config")
            config = loadconfig("config/config.json")
            validate_config(config)
        except Exception as e:
            handle_error("CONFIG", e)
            raise EngineException("Config loading failed", step="CONFIG", original=e) from e

        mortality_table = None
        if config.use_mortality_table:
            try:
                logger.info("2. Loading mortality table")
                mortality_table = load_mortality_table(config.mortality_table_path)
            except Exception as e:
                logger.warning("Mortality table could not be loaded: %s", e)
                mortality_table = None

        try:
            logger.info("3. Creating master data")
            master_data = create_master_data(config)
        except Exception as e:
            handle_error("MASTER_DATA", e)
            raise EngineException("Master data creation failed", step="MASTER_DATA", original=e) from e

        try:
            logger.info("4. Creating discount curve")
            discount_curve = create_discount_curve(config)
        except Exception as e:
            handle_error("DISCOUNT_CURVE", e)
            raise EngineException("Discount curve creation failed", step="DISCOUNT_CURVE", original=e) from e

        try:
            logger.info("5. Creating projection")
            projection = create_projection_table(master_data, config, mortality_table)
            projection = projection.merge(discount_curve, on="Year", how="left")
        except Exception as e:
            handle_error("PROJECTION", e)
            raise EngineException("Projection creation failed", step="PROJECTION", original=e) from e

        try:
            logger.info("6. Calculating cashflows")
            if "coverage_years" not in projection.columns:
                fallback_term = int(getattr(config, "coverage_years", getattr(config, "projection_years", 1)) or 1)
                projection["coverage_years"] = fallback_term
            projection = calculate_cashflows(projection, config)
        except Exception as e:
            handle_error("CASHFLOWS", e)
            raise EngineException("Cashflow calculation failed", step="CASHFLOWS", original=e) from e

        try:
            logger.info("7. Calculating BEL")
            bel_result = calculate_bel(projection, config)
        except Exception as e:
            handle_error("BEL", e)
            raise EngineException("BEL calculation failed", step="BEL", original=e) from e

        try:
            logger.info("8. Calculating Risk Adjustment")
            ra_result = calculate_risk_adjustment(projection, config)
        except Exception as e:
            handle_error("RA", e)
            raise EngineException("Risk Adjustment calculation failed", step="RA", original=e) from e

        try:
            logger.info("9. Calculating CSM roll-forward")
            csm_result = calculate_csm_rollforward(bel_result, ra_result, projection, config)
        except Exception as e:
            handle_error("CSM", e)
            raise EngineException("CSM calculation failed", step="CSM", original=e) from e

        try:
            logger.info("10. Assigning IFRS 17 groups")
            group_result = assign_ifrs17_groups(csm_result, projection, config)
        except Exception as e:
            handle_error("GROUPING", e)
            raise EngineException("Grouping failed", step="GROUPING", original=e) from e

        try:
            if getattr(config, "run_scenarios", False):
                logger.info("11. Running scenario analysis")
                from engine.scenarios import SCENARIOS

                scenarios_dict = getattr(config, "scenarios", None)
                if not isinstance(scenarios_dict, dict):
                    scenarios_dict = SCENARIOS
                scenario_results = run_scenarios(
                    base_config=config,
                    scenarios=scenarios_dict,
                    mortality_table=mortality_table,
                )
            else:
                logger.info("11. Scenario analysis disabled")
                scenario_results = None
        except Exception as e:
            logger.warning("Scenario analysis failed: %s", e, exc_info=True)
            scenario_results = None

        try:
            logger.info("12. Saving outputs")
            save_outputs(
                projection=projection,
                bel_result=bel_result,
                ra_result=ra_result,
                csm_result=csm_result,
                scenario_results=scenario_results,
                output_dir=str(Path(config.output_path).parent),
                master=master_data,
                excel_output=bool(config.excel_output),
                excel_path=config.output_path,
                group_result=group_result,
                config=config,
            )
        except Exception as e:
            handle_error("OUTPUTS", e)
            raise EngineException("Output saving failed", step="OUTPUTS", original=e) from e

        logger.info("=" * 70)
        logger.info("IFRS 17 engine completed successfully")
        logger.info("=" * 70)
        success = True

    except EngineException as e:
        logger.critical("Engine error: %s", e)
        raise
    except Exception as e:
        logger.critical("Unexpected error: %s: %s", type(e).__name__, e, exc_info=True)
        raise
    finally:
        logger.info("Engine run finished")
        logging.shutdown()

        if not success:
            try:
                if Path("engine.log").exists():
                    lines = Path("engine.log").read_text(encoding="utf-8", errors="replace").splitlines()
                    print("\n".join(lines[-80:]))
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.critical("Unexpected error: %s", e, exc_info=True)
        sys.exit(1)
