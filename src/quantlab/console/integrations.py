"""Non-secret connector observability. Configuration != authenticated connectivity."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class Integration:
    name: str
    category: str
    status: str
    details: str
    documentation: str

_CONNECTORS=(
    ("Public API", "Broker", ("PUBLIC_API_TOKEN","PUBLIC_ACCOUNT_ID"), "Orders, account and quotes", "https://public.com/api/docs"),
    ("Webull OpenAPI", "Broker", ("WEBULL_APP_KEY","WEBULL_APP_SECRET"), "Optional market and execution adapter", "https://developer.webull.com/apis/docs/"),
    ("Alpaca / MCP", "Broker", ("APCA_API_KEY_ID","APCA_API_SECRET_KEY"), "Optional execution / AI tool integration", "https://docs.alpaca.markets/"),
    ("SEC EDGAR", "Intelligence", ("SEC_USER_AGENT",), "Filings, disclosure events", "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"),
    ("Grok / X", "Intelligence", ("XAI_API_KEY",), "Event explanation and social context", "https://docs.x.ai/"),
    ("AWS SNS", "Notifications", ("QUANTLAB_SNS_TOPIC_ARN",), "Publish market alerts", "https://docs.aws.amazon.com/sns/"),
    ("AWS SQS", "Queue", ("QUANTLAB_SQS_QUEUE_URL",), "Durable work events (adapter only)", "https://docs.aws.amazon.com/sqs/"),
    ("MQTT", "Notifications", ("QUANTLAB_MQTT_HOST",), "Optional device notification transport", "https://mqtt.org/"),
    ("PostgreSQL / Neon", "Storage", ("DATABASE_URL",), "Durable research and audit records", "https://neon.com/docs"),
    ("Discord alerts", "Notifications", ("QUANTLAB_DISCORD_WEBHOOK_URL",), "Signal candidate and entry-plan notifications", "https://discord.com/developers/docs/resources/webhook"),
    ("Slack alerts", "Notifications", ("QUANTLAB_SLACK_WEBHOOK_URL",), "Optional team signals", "https://api.slack.com/messaging/webhooks"),
    ("SMTP email", "Notifications", ("QUANTLAB_EMAIL_HOST","QUANTLAB_EMAIL_USER","QUANTLAB_EMAIL_PASSWORD","QUANTLAB_EMAIL_FROM","QUANTLAB_EMAIL_TO"), "TLS-only mail delivery", "https://docs.python.org/3/library/smtplib.html"),
    ("SMS delivery", "Notifications", ("QUANTLAB_SMS_PROVIDER","QUANTLAB_SMS_TO"), "Transactional SMS via SNS or Twilio", "https://docs.aws.amazon.com/sns/latest/dg/sms_sending-overview.html"),
)

def integration_statuses(env: Mapping[str,str]) -> list[Integration]:
    result=[]
    for name,kind,keys,details,docs in _CONNECTORS:
        configured=all(bool(env.get(k, "").strip()) for k in keys)
        # Example SEC_USER_AGENT from .env.example does not constitute real setup.
        if name=="SEC EDGAR" and "example.com" in env.get("SEC_USER_AGENT", ""):
            configured=False
        result.append(Integration(name,kind,"Configured · unverified" if configured else "Not configured",details,docs))
    return result
