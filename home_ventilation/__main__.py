import argparse
import asyncio
import logging
import sys
from pathlib import Path

from home_ventilation.config import load_config
from home_ventilation.daemon import run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="home-ventilation",
        description="Automated bathroom exhaust fan control based on CO2, humidity, and switches",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML config file (default: config.toml)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    try:
        config = load_config(args.config)
    except Exception as e:
        logging.error("Failed to load config: %s", e)
        sys.exit(1)

    logging.info("Config loaded from %s", args.config)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
