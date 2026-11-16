from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
from quantlab.intelligence.events import EventFact,EventJournal,classify_event
from quantlab.intelligence.edgar import SECSubmissions,CIKDirectory
from quantlab.intelligence.pipeline import IntelligencePipeline

NOW=datetime(2026,11,12,16,tzinfo=timezone.utc)

def fact(**changes):
    base=dict(source='sec',source_id='1',kind='MATERIAL_DISCLOSURE',headline='Company files 8-K',symbols=('NVDA',),published_at=NOW-timedelta(minutes=2),received_at=NOW,source_url='https://www.sec.gov/example')
    return EventFact(**(base|changes))

def test_event_journal_dedup(tmp_path):
    ledger=EventJournal(str(tmp_path/'events.sqlite'))
    assert ledger.append(fact()) is True
    assert ledger.append(fact()) is False
    assert len(ledger.recent())==1

def test_event_provenance():
    try:fact(published_at=NOW+timedelta(seconds=1))
    except ValueError:pass
    else:assert False
    assert classify_event('8-K','acquisition')=='M_AND_A_CANDIDATE'
    assert classify_event('10-Q')=='FINANCIAL_FILING'

class FakeHTTP:
    def __init__(self,payload): self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*a):return None
    def read(self):return json.dumps(self.payload).encode()

def test_sec_extracts_correct_timestamps_no_future():
    doc={'filings':{'recent':{'form':['8-K','10-Q'],
         'accessionNumber':['0001234567-26-000123','0001234567-26-000124'],
         'acceptanceDateTime':['2026-11-12T10:00:00','2026-11-13T10:00:00'],
         'primaryDocument':['primary.htm','next.htm'],
         'primaryDocDescription':['Strategic acquisition','Quarterly report']}}}
    client=SECSubmissions('QuantLab Test contact@example.com',opener=lambda req,timeout:FakeHTTP(doc))
    events=client.filings(1234567,'NVDA',now=NOW)
    assert len(events)==1
    assert events[0].kind=='M_AND_A_CANDIDATE'
    assert events[0].published_at.isoformat()=='2026-11-12T15:00:00+00:00'
    assert '000123456726000123/primary.htm' in events[0].source_url

def test_directory_matches_current_symbols():
    data={'0':{'ticker':'NVDA','cik_str':1045810},'1':{'ticker':'AMD','cik_str':2488}}
    client=CIKDirectory('QuantLab Test contact@example.com',opener=lambda req,timeout:FakeHTTP(data))
    assert client.lookup({'NVDA'})=={'NVDA':1045810}

def test_pipeline_dedups_and_survives_source_error(tmp_path):
    class Ok:
        def collect(self):return [fact()]
    class Bad:
        def collect(self):raise RuntimeError('busted')
    journal=EventJournal(str(tmp_path/'db.sqlite'))
    source=IntelligencePipeline([Ok(),Bad()],journal)
    a=source.cycle();b=source.cycle()
    assert a.inserted==1 and b.inserted==0 and a.errors
