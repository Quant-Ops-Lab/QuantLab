"""Calendar-aware equity monitoring process."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from quantlab.services.market_schedule import equity_service_open, seconds_until_equity_boundary
from quantlab.services.stock_stream import main_async as equities


LOG = logging.getLogger(__name__)


async def run_forever() -> None:
    if not (os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY")):
        raise RuntimeError("Alpaca market-data credentials required")
    while True:
        now = datetime.now(timezone.utc)
        if not equity_service_open(now):
            await asyncio.sleep(seconds_until_equity_boundary(now))
            continue
        try:
            await asyncio.wait_for(equities(), timeout=seconds_until_equity_boundary(now))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("Equity stream restarting after %s", type(exc).__name__)
            await asyncio.sleep(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()