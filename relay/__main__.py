"""python -m relay  — menjalankan relay (biasanya oleh systemd: mqttc-relay.service)."""
import asyncio
import logging
import sys

from .config import load_config
from .server import Relay


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    config = load_config()
    if len(config.shared_secret) < 32:
        sys.exit("Set RELAY_SHARED_SECRET in .env (32+ random characters), the same value as for Django.")
    try:
        asyncio.run(Relay(config).serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
