"""24/7 crypto research worker process."""
from __future__ import annotations

import asyncio
import logging
import os
from quantlab.market.kraken_rest import KrakenPublic
from quantlab.services.entry_worker import CryptoEntryWorker
from quantlab.services.publishers import build_publisher


LOG = logging.getLogger(__name__)


async def run_forever() -> None:
    pairs = tuple(x.strip() for x in os.getenv("QUANTLAB_CRYPTO_PAIRS", "BTC/USD,ETH/USD").split(",") if x.strip())
    delay = max(15, int(os.getenv("QUANTLAB_CRYPTO_POLL_SECONDS", "30")))
    backoff = 2
    while True:
        try:
            worker = CryptoEntryWorker(KrakenPublic(), build_publisher(), pairs)
            while True:
                await asyncio.to_thread(worker.cycle)
                backoff = 2
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("Crypto worker restarting after %s; retry in %ss", type(exc).__name__, backoff)
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()