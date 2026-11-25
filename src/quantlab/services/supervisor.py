"""One process for the research workers.

Paper and research only. This process does not construct an executor and
cannot arm live orders. QUANTLAB_LIVE_ORDERS_ENABLED is not an arming switch.
Each loop is independent: one failure restarts that loop only.

The web console stays a separate process. deploy/render.single-process.yaml
is a proposal and is not the blueprint Render applies.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading


LOG = logging.getLogger("quantlab.supervisor")
LOOP_NAMES = ("crypto", "equities", "edgar", "quotes", "notifier", "research")


def live_orders_armed() -> bool:
    """Always false. No environment variable arms live trading from here."""
    return False


async def _wait(stop: threading.Event, seconds: float | None = None) -> None:
    if seconds is None:
        await asyncio.to_thread(stop.wait)
        return
    await asyncio.to_thread(stop.wait, max(0.0, seconds))


async def _until_stop(stop: threading.Event, factory) -> None:
    """Run an async worker until stop is set. A crash is raised to the supervisor."""
    task = asyncio.create_task(factory())
    waiter = asyncio.create_task(asyncio.to_thread(stop.wait))
    try:
        done, _pending = await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        task.cancel()
        waiter.cancel()
        raise
    if stop.is_set() or waiter in done:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return
    waiter.cancel()
    exc = task.exception()
    if exc is not None:
        raise exc


async def run_crypto(stop: threading.Event) -> None:
    from quantlab.services.crypto_daemon import run_forever

    await _until_stop(stop, run_forever)


async def run_equities(stop: threading.Event) -> None:
    if not (os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY")):
        LOG.info("equities disabled; Alpaca market-data keys are not set")
        await _wait(stop)
        return
    from quantlab.services.equity_daemon import run_forever

    await _until_stop(stop, run_forever)


async def run_edgar(stop: threading.Event) -> None:
    if not (os.getenv("SEC_USER_AGENT") or "").strip():
        LOG.info("edgar disabled; SEC_USER_AGENT is not set")
        await _wait(stop)
        return
    from quantlab.intelligence.sec_monitor import serve

    await asyncio.to_thread(serve, stop.is_set)


async def run_quotes(stop: threading.Event) -> None:
    if not (os.getenv("PUBLIC_API_TOKEN") and os.getenv("PUBLIC_ACCOUNT_ID")):
        LOG.info("quotes disabled; Public API credentials are not set")
        await _wait(stop)
        return
    from quantlab.services.market_monitor import serve

    await asyncio.to_thread(serve, stop.is_set)


async def run_notifier(stop: threading.Event) -> None:
    from quantlab.services.alert_dispatcher import build

    dispatch = build()
    if not dispatch.channels:
        LOG.info("notifier disabled; no delivery channels configured")
        await _wait(stop)
        return
    while not stop.is_set():
        try:
            await asyncio.to_thread(dispatch.run_once)
        except Exception as exc:
            LOG.warning("notifier cycle failed: %s", type(exc).__name__)
        await _wait(stop, 5)


async def run_research(stop: threading.Event) -> None:
    from quantlab.services.research_daemon import run_once, seconds_until_run

    while not stop.is_set():
        remaining = seconds_until_run()
        while remaining > 0 and not stop.is_set():
            step = min(30.0, remaining)
            await _wait(stop, step)
            remaining -= step
        if stop.is_set():
            return
        try:
            session = await asyncio.to_thread(run_once)
        except Exception as exc:
            LOG.warning("research cycle failed: %s", type(exc).__name__)
            continue
        LOG.info("research session %s", session.isoformat())


def default_loops() -> dict:
    return {
        "crypto": run_crypto,
        "equities": run_equities,
        "edgar": run_edgar,
        "quotes": run_quotes,
        "notifier": run_notifier,
        "research": run_research,
    }


async def supervise(stop: threading.Event, loops: dict, *, backoff_seconds: float = 2.0,
                    max_backoff: float = 60.0, poll_seconds: float = 0.2) -> None:
    """Restart a finished loop without cancelling the others."""
    if live_orders_armed():
        raise RuntimeError("supervisor refuses to run with live orders armed")
    if not loops:
        raise ValueError("no loops to supervise")
    tasks: dict[str, asyncio.Task | None] = {name: None for name in loops}
    delay = {name: backoff_seconds for name in loops}
    ready_at = {name: 0.0 for name in loops}
    clock = asyncio.get_running_loop()
    try:
        while not stop.is_set():
            now = clock.time()
            for name, fn in loops.items():
                task = tasks[name]
                if task is not None and task.done():
                    exc = task.exception()
                    if exc is not None:
                        LOG.warning("%s restarting after %s", name, type(exc).__name__)
                    ready_at[name] = now + delay[name]
                    delay[name] = min(max_backoff, max(delay[name] * 2, backoff_seconds))
                    tasks[name] = None
                    task = None
                if task is None and now >= ready_at[name]:
                    tasks[name] = asyncio.create_task(fn(stop), name=f"quantlab-{name}")
            await asyncio.sleep(poll_seconds)
    finally:
        pending = [task for task in tasks.values() if task is not None and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if live_orders_armed():
        raise SystemExit("live orders are not permitted")
    LOG.info("QuantLab supervisor starting; live orders off; loops=%s", ",".join(LOOP_NAMES))
    stop = threading.Event()

    def halt(*_):
        stop.set()

    signal.signal(signal.SIGINT, halt)
    signal.signal(signal.SIGTERM, halt)
    asyncio.run(supervise(stop, default_loops()))


if __name__ == "__main__":
    main()
