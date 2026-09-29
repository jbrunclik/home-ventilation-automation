import argparse
import asyncio
import logging
import sys
from pathlib import Path

from home_ventilation.config import load_config
from home_ventilation.daemon import run

logger = logging.getLogger("home_ventilation")


def _httpx_debug_filter(record: logging.LogRecord) -> bool:
    """Downgrade httpx INFO messages to DEBUG so they only appear at DEBUG level."""
    if record.levelno == logging.INFO:
        record.levelno = logging.DEBUG
        record.levelname = "DEBUG"
    return True


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
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()

    level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # basicConfig leaves handler level at NOTSET; set it explicitly so the
    # filter-downgraded httpx records actually get filtered out.
    logging.root.handlers[0].setLevel(level)
    # Downgrade httpx per-request INFO logs to DEBUG to avoid log spam.
    logging.getLogger("httpx").addFilter(_httpx_debug_filter)

    try:
        config = load_config(args.config)
    # Missing file, bad TOML, or a missing/mistyped key — all fatal at startup.
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.error("Failed to load config: %s", e)
        sys.exit(1)

    logger.info("Config loaded from %s", args.config)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
