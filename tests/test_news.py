from datetime import datetime,timedelta,timezone
from quantlab.intelligence.events import EventFact
from quantlab.intelligence.news import RuleReasoner,TrustedRSS

now=datetime(2026,11,12,tzinfo=timezone.utc)

def test_reasoner_never_infers_direction_or_new_symbols():
    event=EventFact('wire','abc','OTHER_NEWS','NVDA announces acquisition',
         ('NVDA','INVALID'),now-timedelta(hours=1),now,'https://example.org/news')
    result=RuleReasoner().assess(event,frozenset({'NVDA'}))
    assert result.classification=='M_AND_A_CANDIDATE'
    assert result.symbols==('NVDA',)
    assert result.novelty=='unassessed'

def test_rss_rejects_http():
    try:TrustedRSS('http://example.org/rss','test',('NVDA',))
    except ValueError:pass
    else:assert False
