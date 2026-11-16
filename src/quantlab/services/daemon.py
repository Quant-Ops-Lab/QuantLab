"""Local development supervisor for the isolated market worker processes."""
from __future__ import annotations
import asyncio
import logging
from quantlab.services.crypto_daemon import run_forever as crypto_forever
from quantlab.services.equity_daemon import run_forever as equity_forever

log=logging.getLogger(__name__)

async def crypto_loop():
    await crypto_forever()

async def equity_loop():
    await equity_forever()

async def main_async():
    await asyncio.gather(crypto_loop(),equity_loop())

def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async())

if __name__=='__main__':main()
