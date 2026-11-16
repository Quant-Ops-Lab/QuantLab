import csv
import io
import json
import pytest
from quantlab.market.massive_eod import EODProviderError,append_bars,fetch_market_day

class Response:
    def __init__(self,doc):self.doc=doc
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self):return json.dumps(self.doc).encode()


def test_adjusted_grouped_day():
    doc={'status':'OK','adjusted':True,'resultsCount':2,'results':[
         {'T':'AAA','c':23.5,'v':100000},{'T':'BBB','c':42.1,'v':200000}]}
    def op(req,timeout):
        assert 'Bearer fake' == req.get_header('Authorization')
        assert 'adjusted=true' in req.full_url
        return Response(doc)
    data=fetch_market_day('2026-11-13','fake',opener=op)
    assert [a.symbol for a in data]==['AAA','BBB']
    assert data[0].adjusted_close==23.5


def test_no_weekend_results():
    assert fetch_market_day('2026-11-14','fake',opener=lambda *_ ,**__: Response({'status':'OK','resultsCount':0}))==[]


def test_bad_schema_and_auth_missing():
    with pytest.raises(ValueError):fetch_market_day('2026-11-13','')
    with pytest.raises(EODProviderError):fetch_market_day('2026-11-13','fake',opener=lambda *_ ,**__: Response({'status':'ERROR','message':'bad auth'}))


def test_idempotent_append(tmp_path):
    data=fetch_market_day('2026-11-13','fake',opener=lambda *_ ,**__: Response({'status':'OK','resultsCount':1,'adjusted':True,'results':[{'T':'AAA','c':10,'v':20000}]}))
    p=tmp_path/'prices.csv'
    assert append_bars(p,data)==1
    assert append_bars(p,data)==0
    with p.open() as f:assert len(list(csv.DictReader(f)))==1
