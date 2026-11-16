"""Conservative event interpretation without LLMs or token costs.

Detects *candidate topics* in public articles and filings; does not assert
that allegations, social posts, or scandals are true. Always keep citations.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import re

TOPICS={
 'earnings':('earnings','quarterly results','revenue','guidance','10-q','10-k'),
 'corporate_action':('stock split','reverse split','merger','acquisition','spin-off','tender offer'),
 'supply_chain':('foundry','wafer','packaging','rare earth','memory chip','export control','shipment'),
 'policy':('tariff','sanction','regulation','executive order','congress','doj','ftc'),
 'legal_risk':('lawsuit','investigation','subpoena','settlement','recall','allegation'),
 'capital':('buyback','secondary offering','convertible notes','debt issuance'),
}

@dataclass(frozen=True)
class InterpretedEvent:
    headline:str
    themes:tuple[str,...]
    verified:bool
    treatment:str
    explanation:str
    url:str
    published_at:datetime
    observed_at:datetime


def interpret(headline:str,body:str,source:str,url:str,published_at:datetime,observed_at:datetime,verified_source:bool)->InterpretedEvent:
    if any(t.tzinfo is None for t in (published_at,observed_at)) or observed_at<published_at:
        raise ValueError('point-in-time event timestamps required')
    normalized=re.sub(r'\s+',' ',headline+' '+body).lower()
    themes=tuple(t for t,keywords in TOPICS.items() if any(k in normalized for k in keywords))
    # Classification only. 'Verified source' means origin/timestamp is validated, not truth of assertions.
    provenance=bool(verified_source and url.startswith('https://') and source.strip())
    speculative=bool(re.search(r'\b(rumou?r|alleged|allegedly|unconfirmed|reportedly|sources say|may|could)\b',normalized))
    treatment='VERIFY_MANUALLY' if speculative or not provenance else 'PUBLIC_DISCLOSURE'
    explanation=('Unverified claims or attribution: collect an original corroborating source.' if treatment=='VERIFY_MANUALLY' else
                 'Public-source topic classification only; compare with price reaction before using as a feature.')
    return InterpretedEvent(headline[:500],themes,provenance,treatment,explanation,url,published_at,observed_at)
