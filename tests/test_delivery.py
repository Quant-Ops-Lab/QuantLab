"""No external calls: real provider APIs are represented by in-memory fakes."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest

from quantlab.delivery.channels import (Message,DiscordChannel,SlackChannel,
    SNSSMSChannel,TwilioSMSChannel,SMTPEmailChannel,NtfyChannel,TelegramChannel,
    channels_from_environment)
from quantlab.delivery.dispatcher import (AlertReader,DeliveryLedger,
    NotificationDispatcher,message_from_event)
from quantlab.control.notifications import JsonlPublisher
from quantlab.control.alert_store import AlertJournal

NOW=datetime(2026,11,12,15,0,tzinfo=timezone.utc)


def candidate(now=NOW,direction='LONG'):
    return {'kind':'TRADE_CANDIDATE','execution':'NOT_AUTHORIZED',
        'signal':{'signal_id':'example-signal','symbol':'AMD','direction':direction,'status':'CANDIDATE',
                  'entry':'100','stop':'98' if direction=='LONG' else '102',
                  'take_profit':'105' if direction=='LONG' else '95',
                  'risk_dollars':'5','asof':now.isoformat(),
                  'evidence':['SEC:10-Q:https://sec.gov/filing']}}


def event(payload=None):
    return {'topic':'quantlab/signals/alert','payload':candidate() if payload is None else payload}


class FakeChannel:
    def __init__(self,name='discord',fail=False):
        self.name=name;self.fail=fail;self.sent=[]
    def send(self,message):
        self.sent.append(message)
        if self.fail:raise ConnectionError('provider offline')


def test_signal_message_types_and_suppress_stale():
    m=message_from_event(event(),NOW)
    assert m.symbol=='AMD' and m.entry=='100' and m.evidence_count==1
    assert 'RESEARCH ONLY' in m.short() and 'stop 98' in m.short()
    assert message_from_event(event(),NOW+timedelta(minutes=12)) is None
    assert message_from_event(event(candidate(NOW+timedelta(hours=1))),NOW) is None
    assert message_from_event({'topic':'quantlab/intelligence/event','payload':candidate()},NOW) is None
    p=candidate();p['signal']['status']='NO_TRADE';assert message_from_event(event(p),NOW) is None
    p=candidate();p['execution']='AUTHORIZED';assert message_from_event(event(p),NOW) is None
    p=candidate();p['signal']['stop']='110';assert message_from_event(event(p),NOW) is None
    p=candidate();p['signal']['entry']='NaN';assert message_from_event(event(p),NOW) is None
    p=candidate();p['signal']['symbol']='AMD\n@everyone';assert message_from_event(event(p),NOW) is None
    assert message_from_event(event(candidate(direction='SHORT')),NOW).direction=='SHORT'


def test_jsonl_dispatch_dedup_and_rerun(tmp_path):
    j=JsonlPublisher(tmp_path/'alerts.jsonl')
    j.publish('quantlab/signals/alert',candidate())
    j.publish('quantlab/signals/alert',candidate())
    j.publish('quantlab/intelligence/event',{'headline':'Rumor'})
    channels=[FakeChannel('discord'),FakeChannel('sms'),FakeChannel('email'),FakeChannel('slack')]
    dispatch=NotificationDispatcher(AlertReader(None,tmp_path/'alerts.jsonl'),
                     DeliveryLedger(str(tmp_path/'deliveries.sqlite')),channels)
    result=dispatch.run_once(NOW)
    assert result['eligible']==2 and result['sent']==4
    assert len(channels[0].sent)==1
    assert dispatch.run_once(NOW)['sent']==0
    assert sum(r['count'] for r in dispatch.ledger.summary())==4


def test_sql_journal_dispatch_and_failure_recovery(tmp_path):
    sql=str(tmp_path/'alerts.sqlite')
    j=AlertJournal(sql);j.publish('quantlab/signals/alert',candidate())
    # The SQL journal persists actual receipt time: align test time with receipt clock.
    now=datetime.now(timezone.utc)
    j2=AlertJournal(str(tmp_path/'alerts2.sqlite'))
    p=candidate(now);j2.publish('quantlab/signals/alert',p)
    failing=FakeChannel(fail=True)
    reader=AlertReader(str(tmp_path/'alerts2.sqlite'))
    ledger=DeliveryLedger(str(tmp_path/'deliveries.sqlite'))
    d=NotificationDispatcher(reader,ledger,[failing])
    assert d.run_once(now)['failed']==1
    failing.fail=False
    assert d.run_once(now)['sent']==0   # backoff, not immediate retry
    assert d.run_once(now+timedelta(seconds=31))['sent']==1
    assert d.run_once(now+timedelta(seconds=32))['sent']==0
    assert len(failing.sent)==2


def test_lease_atomic_claim_and_expiry(tmp_path):
    ledger=DeliveryLedger(str(tmp_path/'db.sqlite'))
    eid='a'*64
    first=ledger.claim(eid,'discord',NOW)
    assert first and ledger.claim(eid,'discord',NOW) is None
    second=ledger.claim(eid,'discord',NOW+timedelta(seconds=61))
    assert second and second!=first
    with pytest.raises(RuntimeError):ledger.finish(eid,'discord',first,True,NOW)
    ledger.finish(eid,'discord',second,True,NOW)
    assert ledger.claim(eid,'discord',NOW+timedelta(minutes=10)) is None


def test_channel_https_domain_and_no_mentions():
    sent=[]
    class Response:
        status=204
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def open_req(request,timeout):
        sent.append((request.full_url,json.loads(request.data)))
        assert timeout==10
        return Response()
    m=Message('a'*64,'AMD','SHORT','100','102','95','5',NOW.isoformat(),1)
    DiscordChannel('https://discord.com/api/webhooks/111/TOKEN',open_req).send(m)
    assert sent[0][1]['allowed_mentions']=={'parse':[]}
    SlackChannel('https://hooks.slack.com/services/T/B/C',open_req).send(m)
    assert 'WATCH SHORT AMD' in sent[1][1]['text']
    with pytest.raises(ValueError):DiscordChannel('https://evil.com/api/webhooks/1/2',open_req).send(m)
    with pytest.raises(ValueError):SlackChannel('http://hooks.slack.com/services/1',open_req).send(m)


def test_sns_send_fake():
    class FakeSNS:
        def __init__(self):self.kw=None
        def publish(self,**kw):self.kw=kw;return {'MessageId':'ok'}
    sms=FakeSNS()
    m=Message('a'*64,'AMD','LONG','100','98','106','5',NOW.isoformat(),0)
    SNSSMSChannel('+16145551234',sms).send(m)
    assert sms.kw['PhoneNumber']=='+16145551234'
    assert 'RESEARCH ONLY' in sms.kw['Message']
    with pytest.raises(ValueError):SNSSMSChannel('614-555-1234',sms)


def test_twilio_send_fake():
    class Resp:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'{"sid":"SM123"}'
    calls=[]
    def opener(req,timeout):calls.append(req);return Resp()
    sid='AC'+'a'*32
    c=TwilioSMSChannel(sid,'token','+16145550123','+16145551234',opener)
    c.send(Message('b'*64,'AMD','LONG','100','98','106','5',NOW.isoformat(),0))
    assert calls[0].full_url.startswith('https://api.twilio.com/')
    assert calls[0].get_header('Authorization').startswith('Basic ')


def test_email_tls_fake():
    class FakeSMTP:
        def __init__(self,*args,**kwargs):self.auth=None;self.email=None
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def login(self,user,password):self.auth=(user,password)
        def send_message(self,msg):self.email=msg
    f=FakeSMTP()
    c=SMTPEmailChannel('smtp.example.com',465,'user','secret','alerts@example.com','me@example.com',
                       ssl_factory=lambda *args,**kwargs:f)
    c.send(Message('c'*64,'AMD','LONG','100','98','105','5',NOW.isoformat(),2))
    assert f.email['To']=='me@example.com'
    assert f.email['Subject'].startswith('[QuantLab research]')
    assert 'Verified corroborating items: 2' in f.email.get_content()
    with pytest.raises(ValueError):SMTPEmailChannel('bad',25,'user','secret','alerts@example.com','me@example.com')


def test_no_accidental_sending_without_credentials():
    assert channels_from_environment({})==[]
    with pytest.raises(ValueError):
        NotificationDispatcher(AlertReader(),DeliveryLedger(':memory:'),[FakeChannel('sms'),FakeChannel('sms')])


def _brief(when=NOW):
    return {'kind':'OPPORTUNITY_REPORT_READY','data_asof':'2026-11-23','observed_bars':22,
            'generated_at':when.isoformat(),'title':'QuantLab daily brief 2026-11-23',
            'summary':'Session 2026-11-23\nAAA +1.20%\nResearch only. Not a trade instruction.'}


def _brief_message():
    return Message('d'*64,'MARKET','','','','','',NOW.isoformat(),22,'BRIEF',
                   'QuantLab daily brief 2026-11-23',
                   'Session 2026-11-23\nResearch only. Not a trade instruction.')


def test_brief_goes_to_discord_and_not_sms(tmp_path):
    path=tmp_path/'alerts.jsonl'
    journal=JsonlPublisher(path)
    journal.publish('quantlab/ops/audit',_brief())
    journal.publish('quantlab/ops/audit',_brief(NOW-timedelta(hours=30)))
    journal.publish('quantlab/signals/alert',candidate())
    discord=FakeChannel('discord')
    discord.accepts=lambda kind: kind in ('CANDIDATE','CHANNEL_TEST','BRIEF')
    sms=FakeChannel('sms')
    result=NotificationDispatcher(AlertReader(None,path),DeliveryLedger(str(tmp_path/'d.sqlite')),
                                  [discord,sms]).run_once(NOW)
    assert result['sent']==3
    assert [m.kind for m in discord.sent]==['CANDIDATE','BRIEF']
    assert [m.kind for m in sms.sent]==['CANDIDATE']
    assert message_from_event({'topic':'quantlab/ops/audit','payload':_brief(NOW-timedelta(hours=2))},NOW).kind=='BRIEF'
    assert message_from_event({'topic':'quantlab/signals/alert','payload':_brief()},NOW) is None


def test_discord_brief_is_an_embed_and_sms_refuses_it():
    sent=[]
    class Response:
        status=204
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def open_req(request,timeout):
        sent.append(json.loads(request.data))
        return Response()
    DiscordChannel('https://discord.com/api/webhooks/111/TOKEN',open_req).send(_brief_message())
    embed=sent[0]['embeds'][0]
    assert embed['title'].startswith('QuantLab daily brief')
    assert 'Research only' in embed['footer']['text']
    assert 'content' not in sent[0]
    assert sent[0]['allowed_mentions']=={'parse':[]}
    calls=[]
    def opener(req,timeout):
        calls.append(req)
        raise AssertionError('network')
    sid='AC'+'a'*32
    with pytest.raises(RuntimeError,match='briefs'):
        TwilioSMSChannel(sid,'token','+16145550123','+16145551234',opener).send(_brief_message())
    assert calls==[]


def test_ntfy_and_telegram_are_optional_push_channels():
    token='12345678:'+'A'*35
    sent=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def open_req(request,timeout):
        sent.append((request.full_url,request.get_header('Authorization'),json.loads(request.data)))
        return Response()
    secret='ntfy-secret-token'
    NtfyChannel('https://ntfy.sh/quantlab',secret,open_req).send(_brief_message())
    assert sent[0][0]=='https://ntfy.sh/quantlab'
    assert sent[0][1]=='Bearer '+secret
    assert secret not in json.dumps(sent[0][2])
    assert sent[0][2]['title'].startswith('QuantLab daily brief')
    def boom(request,timeout):
        raise OSError(request.full_url)
    with pytest.raises(RuntimeError,match='telegram delivery failed') as err:
        TelegramChannel(token,'4242',boom).send(_brief_message())
    assert token not in str(err.value)
    env={'QUANTLAB_NTFY_URL':'https://ntfy.sh/quantlab','QUANTLAB_TELEGRAM_BOT_TOKEN':token,
         'QUANTLAB_TELEGRAM_CHAT_ID':'4242'}
    names=[channel.name for channel in channels_from_environment(env)]
    assert names==['ntfy','telegram']
    assert 'sms' not in names
