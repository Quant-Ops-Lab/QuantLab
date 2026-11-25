import asyncio
import threading

from quantlab.services.supervisor import (
    LOOP_NAMES,
    default_loops,
    live_orders_armed,
    run_edgar,
    run_equities,
    run_notifier,
    run_quotes,
    supervise,
)


def test_live_orders_flag_does_not_arm_the_supervisor(monkeypatch):
    monkeypatch.setenv("QUANTLAB_LIVE_ORDERS_ENABLED", "true")
    assert live_orders_armed() is False
    assert set(default_loops()) == set(LOOP_NAMES)
    assert "execution" not in default_loops()


def test_failed_loop_does_not_stop_its_sibling():
    stop = threading.Event()
    counts = {"good": 0, "bad": 0}

    async def good(flag):
        while not flag.is_set():
            counts["good"] += 1
            await asyncio.sleep(0.01)

    async def bad(flag):
        counts["bad"] += 1
        raise RuntimeError("boom")

    async def scenario():
        task = asyncio.create_task(
            supervise(
                stop,
                {"good": good, "bad": bad},
                backoff_seconds=0.02,
                max_backoff=0.05,
                poll_seconds=0.01,
            )
        )
        for _ in range(300):
            if counts["good"] >= 5 and counts["bad"] >= 2:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await task

    asyncio.run(asyncio.wait_for(scenario(), timeout=3))
    assert counts["good"] >= 5
    assert counts["bad"] >= 2


def test_unconfigured_loops_exit_when_stopped(monkeypatch, tmp_path):
    for key in (
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "SEC_USER_AGENT",
        "PUBLIC_API_TOKEN",
        "PUBLIC_ACCOUNT_ID",
        "QUANTLAB_DISCORD_WEBHOOK_URL",
        "QUANTLAB_SLACK_WEBHOOK_URL",
        "QUANTLAB_EMAIL_HOST",
        "QUANTLAB_SMS_PROVIDER",
        "QUANTLAB_NTFY_URL",
        "QUANTLAB_TELEGRAM_BOT_TOKEN",
        "QUANTLAB_TELEGRAM_CHAT_ID",
        "QUANTLAB_ALERT_DB",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("QUANTLAB_DELIVERY_DB", str(tmp_path / "delivery.sqlite"))
    stop = threading.Event()
    stop.set()

    async def run_all():
        await asyncio.gather(run_equities(stop), run_edgar(stop), run_quotes(stop), run_notifier(stop))

    asyncio.run(asyncio.wait_for(run_all(), timeout=3))


def test_quote_and_edgar_serve_do_not_poll_when_already_stopped(monkeypatch, tmp_path):
    from quantlab.intelligence.sec_monitor import serve as serve_edgar
    from quantlab.services.market_monitor import MarketPoller, serve as serve_quotes

    calls = []
    monkeypatch.setattr(MarketPoller, "cycle", lambda self, now=None: calls.append("quote") or {})
    monkeypatch.setenv("PUBLIC_API_TOKEN", "token")
    monkeypatch.setenv("PUBLIC_ACCOUNT_ID", "acct")
    monkeypatch.setenv("QUANTLAB_MARKET_DB", str(tmp_path / "market.sqlite"))
    monkeypatch.setenv("QUANTLAB_ALERTS_FILE", str(tmp_path / "alerts.jsonl"))
    serve_quotes(lambda: True)
    assert calls == []

    mapping = tmp_path / "cik.json"
    mapping.write_text('{"NVDA": 1045810}', encoding="utf-8")
    monkeypatch.setenv("QUANTLAB_CIK_MAP", str(mapping))
    monkeypatch.setenv("QUANTLAB_EVENT_DB", str(tmp_path / "events.sqlite"))
    monkeypatch.setenv("SEC_USER_AGENT", "QuantLabResearch test@example.com")
    monkeypatch.setenv("QUANTLAB_NEWS_FEEDS", str(tmp_path / "missing-feeds.json"))
    serve_edgar(lambda: True)
    assert calls == []
