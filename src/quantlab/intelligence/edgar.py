"""Official SEC EDGAR submissions poller. CIK mapping must be verified separately.

SEC imposes fair-access limits; use an identifying User-Agent and low-frequency
polls. Form description is not a substitute for reading the original filing.
"""
from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import urllib.request
from typing import Callable
from .events import EventFact, classify_event


def _parse_sec_time(raw:str)->datetime:
    dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=ZoneInfo('America/New_York'))
    return dt.astimezone(timezone.utc)


class SECSubmissions:
    def __init__(self, user_agent:str, opener:Callable|None=None):
        if '@' not in user_agent or len(user_agent)<12:
            raise ValueError('identify your application and contact email in SEC_USER_AGENT')
        self.user_agent=user_agent
        self.opener=opener or urllib.request.urlopen

    def filings(self,cik:int,symbol:str,now:datetime|None=None,limit:int=25)->list[EventFact]:
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:raise ValueError('timezone-aware now required')
        if not (1<=int(cik)<=9999999999): raise ValueError('invalid CIK')
        url=f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
        req=urllib.request.Request(url,headers={'User-Agent':self.user_agent,'Accept':'application/json'})
        with self.opener(req,timeout=15) as resp:
            doc=json.loads(resp.read().decode('utf-8'))
        recent=doc.get('filings',{}).get('recent',{})
        out=[]
        forms=recent.get('form',[])
        for i in range(min(limit,len(forms))):
            form=forms[i]
            if form not in {'8-K','10-K','10-Q','6-K','20-F','SC 13D','SC 13G','S-4'}:continue
            try:
                acceptance=(recent.get('acceptanceDateTime') or [])[i]
                accession=(recent.get('accessionNumber') or [])[i]
                primary=(recent.get('primaryDocument') or [])[i]
            except IndexError:
                continue
            published=_parse_sec_time(acceptance)
            if published>now:continue
            accession_dir=accession.replace('-','')
            source_url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_dir}/{primary}'
            desc=(recent.get('primaryDocDescription') or [])
            headline=desc[i] if i<len(desc) and desc[i] else f'{symbol} form {form}'
            out.append(EventFact('sec_edgar',accession, classify_event(form,headline),
                                 f'{symbol}: {form} — {headline}',(symbol,),published,now,source_url,
                                 evidence=f'Official SEC submission; form={form}. Verify document content before acting.'))
        return out


class CIKDirectory:
    """Resolve ticker → CIK via official SEC company_tickers.json at refresh time."""
    def __init__(self,user_agent:str,opener:Callable|None=None):
        if '@' not in user_agent:raise ValueError('valid SEC user agent needed')
        self.user_agent=user_agent
        self.opener=opener or urllib.request.urlopen

    def lookup(self,symbols:set[str])->dict[str,int]:
        req=urllib.request.Request('https://www.sec.gov/files/company_tickers.json',
              headers={'User-Agent':self.user_agent,'Accept':'application/json'})
        with self.opener(req,timeout=20) as resp:
            raw=json.loads(resp.read().decode())
        entries=raw.values() if isinstance(raw,dict) else raw
        result={str(e['ticker']).upper():int(e['cik_str']) for e in entries
                if str(e.get('ticker','')).upper() in symbols}
        return result
