from engine.asumptions import loadconfig
from engine.projection import (
    create_master_data, 
    create_master_data,
    create_projection_table,
    attach_mortality_and_lapse
)


def main() -> None:
    config = loadconfig("config/config.json")

    master = create_master_data(config)
    projection = create_projection_table(master, config)
    projection = attach_mortality_and_lapse(projection, config)

    print(master.head())
    print(projection.head())


if __name__ == "__main__":
    main()