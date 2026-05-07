import logging

from engine.asumptions import loadconfig
from engine.curves import create_discount_curve, get_exponential_lapse


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
	config = loadconfig("config/config.json")

	logger.info("✓ Config loaded and validated")
	logger.info("✓ Policies: %s", f"{config.n_policies:,}")
	logger.info("✓ Projection years: %s", config.projection_years)

	discount_curve = create_discount_curve(config)
	lapse_curve = get_exponential_lapse(
		years=discount_curve["Year"].to_numpy(),
		initial_rate=config.lapse_base_rate,
		decay=config.lapse_decay,
	)

	logger.info("✓ Discount curve created")
	logger.info("\n%s", discount_curve.head())

	logger.info("✓ Lapse curve created")
	logger.info("\n%s", lapse_curve[:5])


if __name__ == "__main__":
	main()
