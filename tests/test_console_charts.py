from datetime import datetime,timezone,timedelta
from quantlab.console.charts import aggregate_quotes,demo_candles,candlestick_figure
from quantlab.console.research_assistant import answer
from quantlab.console.news_views import bucket_news
from quantlab.console.integrations import integration_statuses


def test_aggregation_is_ordered_and_does_not_invent_volume():
    rows=[dict(timestamp="2026-01-01T12:03:00Z",last='110'),dict(timestamp="2026-01-01T12:01:00Z",last='100'),dict(timestamp="2026-01-01T12:04:00Z",last='105')]
    c=aggregate_quotes(rows,'5m');assert len(c)==1
    assert (c[0].open,c[0].high,c[0].low,c[0].close,c[0].samples)==(100,110,100,105,3)


def test_reject_naive_and_invalid_quotes():
    assert aggregate_quotes([dict(timestamp='2026-01-01T12:01:00',last='100'),dict(timestamp='bad',last='2'),dict(timestamp='2026-01-01T12:01:00Z',last='-10')])==[]


def test_demo_is_deterministic_and_labeled():
    a=demo_candles('NVDA');b=demo_candles('NVDA');assert a==b
    fig=candlestick_figure(a,'NVDA',demo=True)
    assert 'SYNTHETIC' in fig.layout.annotations[0].text
    assert len(fig.data)>=2


def test_chart_exposes_range_controls_and_long_trend_overlay():
    fig=candlestick_figure(demo_candles('NVDA',60),'NVDA',show_volume=False,show_ema=True,show_range=True)
    assert fig.layout.xaxis.rangeslider.visible
    assert any(trace.name=='EMA 50 (indicative)' for trace in fig.data)


def test_research_assistant_refuses_trade_claim_without_execution_evidence():
    response=answer('NVDA','Is this a good trade?',demo_candles('NVDA',30))
    assert 'research view, not financial advice' in response.lower()
    assert 'spread' in response.lower() and 'broker preflight' in response.lower()


def test_news_windows_keep_recent_and_archive_consistent():
    now=datetime(2026,11,16,12,0,tzinfo=timezone.utc)
    records=[
        {'headline':'Today story','source':'SEC','source_url':'https://sec.example/today',
         'published_at':(now-timedelta(hours=2)).isoformat(),'kind':'FILING'},
        {'headline':'Older story','source':'RSS','source_url':'https://rss.example/old',
         'published_at':(now-timedelta(days=20)).isoformat(),'kind':'NEWS'},
    ]
    buckets=bucket_news(records,now)
    assert len(buckets['today'])==1 and len(buckets['14 days'])==1
    assert len(buckets['31 days'])==2 and len(buckets['archive'])==2


def test_research_assistant_reports_observed_high_and_low():
    response=answer('NVDA','What are the high and low?',demo_candles('NVDA',30))
    assert 'observed high' in response.lower() and 'observed low' in response.lower()


def test_integration_does_not_claim_live_connection():
    statuses=integration_statuses({'PUBLIC_API_TOKEN':'token','PUBLIC_ACCOUNT_ID':'account'})
    assert statuses[0].status=='Configured · unverified'
    assert statuses[1].status=='Not configured'
    assert not any('Connected' in i.status for i in statuses)
