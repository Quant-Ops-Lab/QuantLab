"""SMS / Discord / email / Slack adapters. No credentials in source or payloads.

Provider acceptance does NOT prove handset or inbox delivery. Alerts are
research notices, not instructions to execute a trade. No LLM tokens used.
"""
from __future__ import annotations
from dataclasses import dataclass
from email.message import EmailMessage
from datetime import datetime, timezone
from typing import Protocol
import json
import os
import re
import smtplib
import ssl
import urllib.request
from urllib.parse import urlparse


@dataclass(frozen=True)
class Message:
    event_id: str
    symbol: str
    direction: str
    entry: str
    stop: str
    target: str
    risk: str
    asof: str
    evidence_count: int
    kind: str = 'CANDIDATE'

    def __post_init__(self):
        if self.kind not in ('CANDIDATE', 'CHANNEL_TEST'):
            raise ValueError('unsupported notification kind')
        if self.kind == 'CANDIDATE' and (self.direction not in ('LONG','SHORT') or not re.fullmatch(r'[A-Z0-9./_-]{1,28}', self.symbol)):
            raise ValueError('invalid signal label')

    def short(self) -> str:
        if self.kind == 'CHANNEL_TEST':
            return 'QuantLab CHANNEL TEST. No market signal and no order.'
        return (f'QuantLab WATCH {self.direction} {self.symbol} | entry {self.entry} | '
                f'stop {self.stop} | target {self.target} | risk ${self.risk}. '
                f'RESEARCH ONLY; execution unverified. #{self.event_id[:10]}')[:600]

    def detailed(self) -> str:
        if self.kind == 'CHANNEL_TEST':
            return self.short()
        return (f'{self.short()}\nObserved: {self.asof}\n'
                f'Verified corroborating items: {self.evidence_count}\n'
                'Candidate plan, not a broker quote or fill. Check liquidity, age, '
                'fees, account permissions, corporate actions and market session.')


class Channel(Protocol):
    name: str
    def send(self, message: Message) -> None: ...


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post_json(url: str, data: dict, allowed_hosts: set[str], opener=None) -> None:
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in allowed_hosts or parsed.username or parsed.password or parsed.port:
        raise ValueError('webhook must use approved HTTPS provider')
    raw=json.dumps(data,allow_nan=False).encode('utf-8')
    req=urllib.request.Request(url,raw,headers={'Content-Type':'application/json','User-Agent':'QuantLab/0.6'},method='POST')
    open_func=opener or urllib.request.build_opener(_NoRedirects()).open
    with open_func(req,timeout=10) as response:
        status=getattr(response,'status',getattr(response,'code',200))
        if not 200<=status<300:
            raise RuntimeError('webhook returned non-success status')


class DiscordChannel:
    name='discord'
    def __init__(self, url:str, opener=None):
        if not url:raise ValueError('Discord URL missing')
        self.url=url;self.opener=opener
    def send(self, message:Message) -> None:
        _post_json(self.url,{'username':'QuantLab Research','content':message.detailed()[:1900],
                      'allowed_mentions':{'parse':[]}}, {'discord.com','discordapp.com'},self.opener)


class SlackChannel:
    name='slack'
    def __init__(self, url:str, opener=None):
        if not url:raise ValueError('Slack URL missing')
        self.url=url;self.opener=opener
    def send(self, message:Message) -> None:
        # Plain text with no special mentions or user-controlled hyperlinks.
        _post_json(self.url,{'text':message.detailed()[:2700]}, {'hooks.slack.com'},self.opener)


class SNSSMSChannel:
    name='sms'
    def __init__(self,phone_number:str,client=None):
        if not re.fullmatch(r'\+[1-9]\d{7,14}',phone_number):raise ValueError('SMS number must be E.164')
        if client is None:
            import boto3
            client=boto3.client('sns')
        self.number=phone_number;self.client=client
    def send(self,message:Message)->None:
        # A returned MessageId confirms SNS acceptance, not handset delivery.
        result=self.client.publish(PhoneNumber=self.number,Message=message.short()[:450],
                                   MessageAttributes={'AWS.SNS.SMS.SMSType': {'DataType':'String','StringValue':'Transactional'}})
        if not result.get('MessageId'):raise RuntimeError('SNS publish not acknowledged')


class TwilioSMSChannel:
    name='sms'
    def __init__(self, account_sid:str,auth_token:str,from_number:str,to_number:str,opener=None):
        if not re.fullmatch(r'AC[a-fA-F0-9]{32}',account_sid):raise ValueError('invalid Twilio SID')
        if not auth_token:raise ValueError('missing Twilio credential')
        if not all(re.fullmatch(r'\+[1-9]\d{7,14}',v) for v in (from_number,to_number)):
            raise ValueError('SMS numbers must be E.164')
        self.sid=account_sid;self.token=auth_token;self.sender=from_number;self.to=to_number
        self.opener=opener
    def send(self,message:Message)->None:
        import base64
        from urllib.parse import urlencode
        address=f'https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json'
        body=urlencode({'From':self.sender,'To':self.to,'Body':message.short()[:450]}).encode()
        auth=base64.b64encode(f'{self.sid}:{self.token}'.encode()).decode()
        req=urllib.request.Request(address,body,headers={'Authorization':'Basic '+auth,
                         'Content-Type':'application/x-www-form-urlencoded'},method='POST')
        open_func=self.opener or urllib.request.build_opener(_NoRedirects()).open
        with open_func(req,timeout=10) as res:
            data=json.loads(res.read(4096))
            if not data.get('sid'):raise RuntimeError('Twilio submission not acknowledged')


class SMTPEmailChannel:
    name='email'
    def __init__(self,host:str,port:int,username:str,password:str,from_address:str,to_address:str,
                 ssl_factory=None,starttls_factory=None):
        if not host or not 1<=port<=65535:raise ValueError('SMTP host/port missing')
        if '\n' in host or '\r' in host:raise ValueError('invalid SMTP host')
        for x in (from_address,to_address):
            if '\n' in x or '\r' in x or '@' not in x:raise ValueError('invalid email address')
        if not username or not password:raise ValueError('SMTP login required')
        if port not in (465,587):raise ValueError('use SSL port 465 or STARTTLS port 587')
        self.host,self.port,self.username,self.password=host,port,username,password
        self.sender,self.recipient=from_address,to_address
        self.ssl_factory=ssl_factory or smtplib.SMTP_SSL
        self.starttls_factory=starttls_factory or smtplib.SMTP
    def send(self,message:Message)->None:
        email=EmailMessage()
        email['From']=self.sender;email['To']=self.recipient
        email['Subject']='[QuantLab TEST]' if message.kind=='CHANNEL_TEST' else f'[QuantLab research] {message.symbol} {message.direction}'
        email.set_content(message.detailed())
        tls=ssl.create_default_context()
        if self.port==465:
            with self.ssl_factory(self.host,self.port,timeout=15,context=tls) as server:
                server.login(self.username,self.password)
                server.send_message(email)
        else:
            with self.starttls_factory(self.host,self.port,timeout=15) as server:
                server.ehlo();server.starttls(context=tls);server.ehlo()
                server.login(self.username,self.password)
                server.send_message(email)


def channels_from_environment(env=None)->list[Channel]:
    env=os.environ if env is None else env
    channels=[]
    if env.get('QUANTLAB_DISCORD_WEBHOOK_URL'):
        channels.append(DiscordChannel(env['QUANTLAB_DISCORD_WEBHOOK_URL']))
    if env.get('QUANTLAB_SLACK_WEBHOOK_URL'):
        channels.append(SlackChannel(env['QUANTLAB_SLACK_WEBHOOK_URL']))
    if env.get('QUANTLAB_EMAIL_HOST'):
        channels.append(SMTPEmailChannel(env['QUANTLAB_EMAIL_HOST'],int(env.get('QUANTLAB_EMAIL_PORT','587')),
            env['QUANTLAB_EMAIL_USER'],env['QUANTLAB_EMAIL_PASSWORD'],env['QUANTLAB_EMAIL_FROM'],env['QUANTLAB_EMAIL_TO']))
    provider=env.get('QUANTLAB_SMS_PROVIDER','').lower()
    if provider=='sns':
        channels.append(SNSSMSChannel(env['QUANTLAB_SMS_TO']))
    elif provider=='twilio':
        channels.append(TwilioSMSChannel(env['TWILIO_ACCOUNT_SID'],env['TWILIO_AUTH_TOKEN'],
            env['TWILIO_FROM_NUMBER'],env['QUANTLAB_SMS_TO']))
    elif provider:
        raise ValueError('unknown SMS provider')
    return channels
