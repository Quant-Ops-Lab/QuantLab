"""QuantLab Command: candlestick-first, read-only research operator console.

The UI deliberately has NO direct broker order submission endpoints. Workers,
API and UI must be independently deployed; the browser is never a market feed.
"""
from __future__ import annotations
import hmac
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import streamlit as st
from quantlab.console.charts import aggregate_quotes, candlestick_figure, demo_candles, TIMEFRAMES
from quantlab.console.integrations import integration_statuses
from quantlab.control.planner import draft
from quantlab.control.contracts import StrategySpec, SignalObservation
from quantlab.control.notifications import JsonlPublisher
from quantlab.control.sdk import QuantLabClient
from quantlab.intelligence.events import EventJournal
from quantlab.portfolio.policy import Position, HarvestPolicy, evaluate_position
from quantlab.services.market_monitor import QuoteJournal
from quantlab.universe.catalog import default_universe, RESEARCH_ONLY

st.set_page_config(page_title='QuantLab / COMMAND',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
ROOT = Path.cwd()
EVENTS=Path(os.getenv('QUANTLAB_ALERTS_FILE','artifacts/alerts.jsonl'))
MARKET_DSN=os.getenv('QUANTLAB_MARKET_DB','artifacts/market.sqlite')
EVENT_DSN=os.getenv('QUANTLAB_EVENT_DB','artifacts/events.sqlite')
UNIVERSE=default_universe()

st.markdown('''<style>
:root{--ink:#090e16;--panel:#111c29;--line:#273544;--cyan:#8bf8eb;--lime:#b8fb75;--purple:#be9dff}
[data-testid="stAppViewContainer"]{background:radial-gradient(900px 460px at 82% -24%,rgba(75,61,161,.22),transparent),#080d15;color:#dee9f3}
[data-testid="stSidebar"]{background:#0b1420;border-right:1px solid #243347}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"]{display:none}
.block-container{padding-top:1.4rem;max-width:1580px}
[data-testid="stMetric"]{padding:17px;border-radius:13px;border:1px solid #26394b;background:linear-gradient(145deg,#111d2a,#0c1520)}
[data-testid="stMetricLabel"]{color:#9db3c5;font-size:.79rem}
[data-testid="stMetricValue"]{color:var(--cyan);letter-spacing:-.04em}
h1,h2,h3{letter-spacing:-.035em!important;color:#f0f8ff!important}
.stButton>button{border-radius:9px;border-color:#314457}
.stButton>button[kind="primary"]{background:#8bf8eb!important;color:#09131e!important;border:none!important;font-weight:700}
[data-testid="stDataFrame"]{border:1px solid #283747;border-radius:12px;overflow:hidden}
.q-eyebrow{font-size:.67rem;letter-spacing:.2em;text-transform:uppercase;color:#8bf8eb;font-weight:750}
.q-intro{color:#a5b9cd;font-size:.92rem;max-width:860px}
.q-band{background:linear-gradient(92deg,#0f2230,#12232b);border:1px solid #2c4b51;border-radius:12px;padding:1rem 1.3rem}
.q-chip{display:inline-block;border:1px solid #3a5362;border-radius:999px;padding:2px 10px;color:#9eb9cc;font-size:11px;letter-spacing:.06em}
.q-warning{border-left:2px solid #ffc16b;background:#1d1b1a;padding:12px 15px;color:#e5ccb2;border-radius:4px}
.q-quiet{color:#8aa2b5;font-size:.79rem}
.q-card{background:#101b28;border:1px solid #293b4b;border-radius:13px;padding:15px 19px;margin-bottom:10px}
.q-card-title{font-weight:650;color:#ecf8ff;font-size:.93rem}
.q-card-sub{font-size:.76rem;color:#9fb3c4;margin-top:5px}
</style>''',unsafe_allow_html=True)


def require_operator_password():
    # All public/Render deployments MUST set both of these variables.
    required=os.getenv('QUANTLAB_REQUIRE_AUTH','0').strip()=='1'
    if not required:return
    secret=os.getenv('QUANTLAB_CONSOLE_PASSWORD','')
    if len(secret)<16:
        st.error('Command center unavailable: QUANTLAB_CONSOLE_PASSWORD must be configured (16+ characters).')
        st.stop()
    if st.session_state.get('quantlab_authenticated',False):return
    st.title('◈ QUANTLAB / AUTHENTICATE')
    password=st.text_input('Operator passphrase',type='password')
    if st.button('Unlock command center',type='primary'):
        if hmac.compare_digest(password,secret):
            st.session_state['quantlab_authenticated']=True
            st.rerun()
        else:st.error('Invalid credentials')
    st.stop()


def observed_quotes(symbol:str,limit:int=500):
    if not MARKET_DSN.startswith(('postgresql://','postgres://')) and not Path(MARKET_DSN).exists():
        return []
    return QuoteJournal(MARKET_DSN).history(symbol,limit)


def observed_events(limit=30):
    if not EVENT_DSN.startswith(('postgresql://','postgres://')) and not Path(EVENT_DSN).exists():
        return []
    return EventJournal(EVENT_DSN).recent(limit)


def fmt_snapshot(row:dict):
    try:
        price=float(row['last']);bid=float(row['bid']);ask=float(row['ask'])
        return f'${price:,.2f}',f'${bid:,.2f} / ${ask:,.2f}'
    except (TypeError,ValueError,KeyError):
        return 'Unavailable','Unavailable'

require_operator_password()

# Two role-separated experiences. A UI switch does not grant administrative
# privileges: the Admin workspace is locked unless the server has a secret.
from quantlab.console.theme import THEMES,css
with st.sidebar:
    st.markdown('### ◈ QuantLab')
    theme=st.selectbox('Appearance',list(THEMES),index=list(THEMES).index(st.session_state.get('ql_theme','Deck')))
    st.session_state['ql_theme']=theme
    workspace=st.segmented_control('Experience',['Consumer','Admin'],default='Consumer')
st.markdown(css(theme),unsafe_allow_html=True)
if workspace=='Consumer':
    from quantlab.console.consumer import render as render_consumer
    render_consumer(theme)
    st.stop()

admin_secret=os.getenv('QUANTLAB_ADMIN_PASSWORD','')
if len(admin_secret)<16:
    st.warning('Admin is unavailable until QUANTLAB_ADMIN_PASSWORD (16+ characters) is configured on the server.')
    st.stop()
if not st.session_state.get('ql_admin_verified',False):
    st.title('QuantLab · Administrator access')
    password=st.text_input('Administrator passphrase',type='password')
    if st.button('Enter Admin workspace',type='primary'):
        if hmac.compare_digest(password,admin_secret):
            st.session_state['ql_admin_verified']=True
            st.rerun()
        else:st.error('Invalid administrator credentials')
    st.stop()

with st.sidebar:
    st.markdown('## ◈ QUANTLAB')
    st.markdown('<div class="q-eyebrow">QUANT-OPS-LAB / COMMAND</div>',unsafe_allow_html=True)
    st.caption('QUANTLAB / v0.7.0')
    page=st.radio('Navigation',[
        'Market Terminal','Opportunity Intelligence','Intelligence','Universe','Portfolio Lab',
        'Strategy Studio','Signals & AI','Integrations','Alert Delivery','Audit & Operations','Execution Consent'],
        label_visibility='collapsed')
    st.divider()
    st.markdown('<div class="q-eyebrow">EXECUTION STATE</div>',unsafe_allow_html=True)
    st.warning('Live engine NOT ARMED')
    st.caption('Charts use observed Public quote snapshots or visibly labeled synthetic preview data.')

if page=='Market Terminal':
    st.markdown('<div class="q-eyebrow">MARKET OPERATIONS / HOME</div>',unsafe_allow_html=True)
    left,right=st.columns([3,1])
    with left:
        st.title('Your market. One command center.')
        st.markdown('<p class="q-intro">AI compute, semiconductor manufacturing, software, energy, metals and defensive instruments — screened through a verifiable intelligence pipeline.</p>',unsafe_allow_html=True)
    with right:
        st.markdown('<div class="q-band"><div class="q-eyebrow">STATE</div><b>Research / monitoring</b><div class="q-quiet">No connected brokerage account confirmed</div></div>',unsafe_allow_html=True)
    symbols=list(UNIVERSE)
    col_sym,col_frame,col_mode=st.columns([2,1,1.5])
    symbol=col_sym.selectbox('Instrument',symbols,index=symbols.index('NVDA') if 'NVDA' in symbols else 0,
                              format_func=lambda s:f'{s} · {UNIVERSE[s].name}')
    timeframe=col_frame.selectbox('Interval',list(TIMEFRAMES),index=1)
    show_demo=col_mode.toggle('Synthetic design preview',value=False,
                              help='Explicitly synthetic candles for UI design; never used for ML or orders')
    try:
        history=observed_quotes(symbol)
        bars=aggregate_quotes(history,timeframe)
        snap=history[-1] if history else None
        last_time=snap.get('timestamp') if snap else None
    except Exception as exc:
        history=[];bars=[];snap=None;last_time=None
        st.warning(f'Quote store unavailable ({type(exc).__name__}); showing no authenticated market data.')
    if show_demo:
        bars=demo_candles(symbol)
        provenance='SYNTHETIC DESIGN PREVIEW — NOT REAL PRICES'
    else:
        provenance='SAMPLED PUBLIC QUOTES — INDICATIVE OHLC (NOT EXCHANGE BARS)' if bars else 'NO LIVE OR HISTORICAL QUOTES CONNECTED'
    a,b,c,d=st.columns(4)
    a.metric('Instrument',symbol)
    b.metric('Last sampled quote',fmt_snapshot(snap)[0] if snap and not show_demo else 'Not shown')
    c.metric('Spread (bid/ask)',fmt_snapshot(snap)[1] if snap and not show_demo else 'Unavailable')
    d.metric('Observed samples',len(history) if not show_demo else 'Demo')
    st.markdown(f'<div class="q-eyebrow">{provenance}</div>',unsafe_allow_html=True)
    if len(bars)<2 and not show_demo:
        st.info('Not enough verified quotes for a candlestick series. Configure PUBLIC_API_TOKEN and run the quotes worker, or switch on synthetic design preview.')
    else:
        st.plotly_chart(candlestick_figure(bars,symbol,demo=show_demo),width='stretch',config={'displaylogo':False})
    if last_time and not show_demo:st.caption(f'Last observed quote at {last_time} · aggregation can miss unsampled intrabar highs/lows · no traded volume available')
    st.divider()
    x,y=st.columns([1.35,1])
    with x:
        st.subheader('Watch clusters')
        themes=sorted({t for a_ in UNIVERSE.values() for t in a_.themes})
        active=st.selectbox('Sector lens',themes,index=themes.index('ai_compute') if 'ai_compute' in themes else 0)
        assets=[a_ for a_ in UNIVERSE.values() if active in a_.themes]
        st.dataframe([{'Symbol':a_.symbol,'Company / Fund':a_.name,'Type':a_.kind.value} for a_ in assets],hide_index=True,width='stretch')
    with y:
        st.subheader('Latest intelligence')
        try:
            events=observed_events(5)
        except Exception:events=[]
        if not events:st.info('No ingested events yet. Connect SEC EDGAR for verified filings.')
        for ev in events:
            st.markdown(f'**{ev.get("kind","EVENT")}** · {", ".join(ev.get("symbols",[])) or "General"}')
            st.write(ev.get('headline','No headline'))
            if ev.get('source_url'):st.link_button('Original disclosure',ev['source_url'])
            st.divider()
        st.caption('AI may summarize evidence, but events are not automatic trades.')
elif page=='Opportunity Intelligence':
    st.markdown('<div class="q-eyebrow">RESEARCH / MARKET AUTOPSY</div>',unsafe_allow_html=True)
    st.title('Opportunity Intelligence')
    st.caption('What moved across the observed market, and what did QuantLab know before it moved? Rankings are hindsight, not trading profits.')
    report_path=Path(os.getenv('QUANTLAB_OPPORTUNITY_REPORT','artifacts/opportunity/latest.json'))
    if not report_path.is_file():
        st.info('No verified broad-market report has been ingested. This screen does not invent movers.')
        st.code('quantlab-eod --start 2026-10-01 --end 2026-11-13 --output artifacts/opportunity/daily_bars.csv\nquantlab-opportunity --bars artifacts/opportunity/daily_bars.csv',language='bash')
        st.caption('Requires MASSIVE_API_KEY and historical prices. Historical model decisions and watchlist snapshots must be separately recorded to classify missed opportunities.')
    else:
        try:
            report=json.loads(report_path.read_text(encoding='utf-8'))
            if report.get('schema_version')!='1.0' or report.get('mode')!='observed_inputs_only':
                raise ValueError('Unrecognized report schema or data provenance')
            metrics=st.columns(4)
            metrics[0].metric('As of',str(report['data_asof']))
            metrics[1].metric('Observed price rows',f"{report['observed_bars']:,}")
            metrics[2].metric('Historic decisions',f"{report['decisions']:,}")
            metrics[3].metric('Coverage snapshots',f"{report['coverage_snapshots']:,}")
            st.caption('Feed sources: '+', '.join(report.get('data_sources',[])))
            market=st.segmented_control('Asset class',['equity','crypto'],default='equity')
            tab_day,tab_week,tab_month=st.tabs(['1 session','1 week','1 month'])
            for tab,window in zip((tab_day,tab_week,tab_month),('day','week','month')):
                with tab:
                    rows=report['movers'][market][window]
                    if rows:
                        st.dataframe(rows,hide_index=True,width='stretch',use_container_width=False)
                        st.caption('Raw equity bars may contain unverified corporate-action distortions. No listed return represents hypothetical executable P&L.')
                    else:
                        st.info('No complete historical window in this data set.')
                    missing=report['missing_start_bars'][market][window]
                    if missing:st.warning(f'{missing} instruments lacked a starting bar and were excluded.')
            with st.expander('All outsized movers — independent of top-N ranking'):
                inv=report.get('outsized_move_inventory',{}).get(market,{})
                w=st.selectbox('Return horizon',('day','week','month'),key='ql_opportunity_window')
                records=inv.get(w,[])
                if records:st.dataframe(records,hide_index=True,width='stretch')
                else:st.info('No observed price moves exceeded the configured retrospective threshold.')
            with st.expander('Data integrity and interpretation limits'):
                for warning in report['warnings']:st.write('• '+warning)
            st.download_button('Download JSON audit',report_path.read_bytes(),file_name='market_autopsy.json',mime='application/json')
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as exc:
            st.error('Report is unreadable or corrupt: '+type(exc).__name__)

elif page=='Intelligence':
    st.markdown('<div class="q-eyebrow">EVENTS / DISCLOSURES</div>',unsafe_allow_html=True)
    st.title('Event Intelligence')
    st.caption('M&A, splits, earnings, supplier announcements and SEC filings with publication and ingestion timestamps.')
    try:events=observed_events(150)
    except Exception as exc:
        events=[];st.error(f'Journal unavailable: {type(exc).__name__}')
    kinds=sorted({ev.get('kind','OTHER') for ev in events})
    selected_kinds=st.multiselect('Event types',kinds,default=kinds)
    shown=[ev for ev in events if ev.get('kind','OTHER') in selected_kinds]
    st.metric('Verified-source events stored',len(events))
    if shown:
        st.dataframe([{'Type':e.get('kind'),'Headline':e.get('headline'),'Symbols':', '.join(e.get('symbols',[])),
            'Published':e.get('published_at'),'Received':e.get('received_at'),'Source':e.get('source')} for e in shown],
            hide_index=True,width='stretch')
        idx=st.selectbox('Inspect original disclosure',range(len(shown)),format_func=lambda i:shown[i].get('headline','Event'))
        st.link_button('View source',shown[idx]['source_url'])
    else:st.info('No verified event records for this filter. Event processing begins when the EDGAR or configured RSS worker runs.')
elif page=='Universe':
    st.markdown('<div class="q-eyebrow">DISCOVERY / RESEARCH UNIVERSE</div>',unsafe_allow_html=True)
    st.title('Thematic Watch Universe')
    themes=sorted({t for a in UNIVERSE.values() for t in a.themes})
    selected=st.multiselect('Themes',themes,default=themes)
    query=st.text_input('Find tickers, companies, ETFs').lower().strip()
    rows=[a for a in UNIVERSE.values() if set(a.themes)&set(selected) and
          (not query or query in a.symbol.lower() or query in a.name.lower())]
    st.metric('Research candidates',len(rows))
    st.dataframe([{'Ticker':a.symbol,'Name':a.name,'Theme':', '.join(a.themes),'Asset':a.kind.value}
                  for a in rows],width='stretch',hide_index=True)
    st.caption('Research-only context, not broker instruments: '+', '.join(a.name for a in RESEARCH_ONLY))
elif page=='Portfolio Lab':
    st.markdown('<div class="q-eyebrow">PORTFOLIO / POLICIES</div>',unsafe_allow_html=True)
    st.title('Core ownership + tactical profit harvesting')
    st.caption('Policy simulator. Values are operator-entered, not reconciled to a brokerage account.')
    a,b,c,d=st.columns(4)
    shares=a.number_input('Shares',0.001,100000.0,10.0)
    basis=b.number_input('Average basis',0.01,100000.0,100.0)
    peak=c.number_input('High-water mark',0.01,100000.0,150.0)
    price=d.number_input('Current reference price',0.01,100000.0,140.0)
    e,f,g=st.columns(3)
    take=e.slider('Profit threshold %',5,95,20)
    trim=f.slider('Trim shares %',5,90,25)
    trail=g.slider('Peak decline threshold %',5,60,30)
    policy=HarvestPolicy(Decimal(take)/100,Decimal(trim)/100,Decimal(trail)/100)
    try:
        result=evaluate_position(Position('SANDBOX',Decimal(str(shares)),Decimal(str(basis)),Decimal(str(peak))),Decimal(str(price)),policy)
        st.metric('Policy candidate',result.action)
        st.write(f'**{result.shares} shares** · {result.reason}')
    except Exception as exc:st.error(f'Invalid position: {exc}')
    st.warning('Partial sales are taxable dispositions. 30% drawdown is from the observed peak, not a guaranteed execution loss cap. No actual orders are placed here.')
elif page=='Strategy Studio':
    st.markdown('<div class="q-eyebrow">RESEARCH / STRATEGY FACTORY</div>',unsafe_allow_html=True)
    st.title('Describe → Compile → Review')
    st.caption('Deterministic draft schema. External AI strategy compilation is not configured.')
    with st.form('draft_strategy'):
        description=st.text_area('Describe the market condition',value='Alert me if bearish movement is independently confirmed in liquid AI equities.',height=120)
        symbols_raw=st.text_input('Allowed symbols',value='NVDA, AMD, MU')
        a,b,c=st.columns(3)
        direction=a.selectbox('Context',['bearish','long'])
        mode=b.selectbox('Operation',['alert_only','approval_required'])
        threshold=c.number_input('Movement threshold (bps)',1,1000,30)
        compile_draft=st.form_submit_button('Compile draft',type='primary')
    if compile_draft:
        try:
            spec=draft(description,[v.strip().upper() for v in symbols_raw.split(',')],direction,mode,int(threshold))
            st.session_state['draft_json']=json.dumps(spec.to_dict(),indent=2)
            st.session_state['draft_sha']=spec.fingerprint
        except Exception as exc:st.error(f'Cannot compile draft: {exc}')
    if 'draft_json' in st.session_state:
        st.success('Schema valid · not statistically approved · not deployed')
        st.code(st.session_state['draft_json'],language='json')
        st.caption('Fingerprint: '+st.session_state['draft_sha'])
        st.download_button('Export strategy.json',st.session_state['draft_json'],file_name='strategy.json')
elif page=='Signals & AI':
    st.markdown('<div class="q-eyebrow">MODEL INTELLIGENCE / READ ONLY</div>',unsafe_allow_html=True)
    st.title('Signal review & explanation')
    st.caption('AI reasoning is an evidence layer. No configured external LLM or brokerage execution authority in this release.')
    st.markdown('<div class="q-band"><b>Research assistant</b><div class="q-quiet">Connect a model provider to explain verified market and event evidence. It cannot submit orders.</div></div>',unsafe_allow_html=True)
    raw=st.text_area('Strategy JSON',value=st.session_state.get('draft_json',''),height=190)
    a,b,c=st.columns(3)
    symbol=a.text_input('Symbol',value='NVDA')
    change=b.number_input('Operator-supplied change (bps)',value=-45.0)
    confirmed=c.checkbox('Independent confirmation',value=True)
    if st.button('Evaluate observation (no order)',type='primary'):
        try:
            spec=StrategySpec.from_dict(json.loads(raw))
            now=datetime.now(timezone.utc)
            observation=SignalObservation(symbol.upper(),now,float(change),confirmed,'streamlit-manual','operator_input')
            decision=QuantLabClient(JsonlPublisher(EVENTS)).run_once(spec,observation,now)
            st.metric('Decision',decision.status)
            st.write(decision.explanation)
            st.json(decision.to_dict())
        except Exception as exc:st.error(f'Observation rejected: {exc}')
    st.caption('Typed changes are not broker-authenticated. A real signal requires point-in-time market provenance and independent evaluation.')
elif page=='Integrations':
    st.markdown('<div class="q-eyebrow">CONNECTIVITY / OPERATIONS</div>',unsafe_allow_html=True)
    st.title('Integrations & data sources')
    st.caption('Configuration visibility only. Never display secret keys or claim a provider is connected without an authenticated health check.')
    rows=integration_statuses(os.environ)
    configured=sum(i.status.startswith('Configured') for i in rows)
    a,b,c=st.columns(3)
    a.metric('Available connector contracts',len(rows))
    b.metric('Configured · unverified',configured)
    c.metric('Verified authenticated connections','0')
    st.divider()
    for integration in rows:
        x,y=st.columns([4,1])
        with x:
            st.markdown(f'<div class="q-card"><div class="q-card-title">{integration.name}</div><div class="q-card-sub">{integration.category} · {integration.details}</div></div>',unsafe_allow_html=True)
        with y:
            st.caption(integration.status)
            st.link_button('Documentation',integration.documentation)
    st.warning('Public is the planned first broker adapter. Existing API keys never grant the AI trading authority. Broker setup and actual connectivity are separate steps.')
elif page=='Alert Delivery':
    st.markdown('<div class="q-eyebrow">OPERATIONS / NOTIFICATIONS</div>',unsafe_allow_html=True)
    st.title('Alert delivery')
    st.caption('Send candidate entry/stop/target notices to your own configured channels. Test notices never contain trades.')
    from quantlab.delivery.dispatcher import DeliveryLedger
    from quantlab.delivery.channels import Message,channels_from_environment
    import time
    names=[]
    sms_provider=os.getenv('QUANTLAB_SMS_PROVIDER','')
    try:
        if os.getenv('QUANTLAB_DISCORD_WEBHOOK_URL'):names.append('Discord')
        if os.getenv('QUANTLAB_SLACK_WEBHOOK_URL'):names.append('Slack')
        if os.getenv('QUANTLAB_EMAIL_HOST'):names.append('Email')
        if sms_provider:names.append('SMS via '+sms_provider.upper())
        st.metric('Notification channels configured',len(names))
        st.caption('Configured is not verified delivery. Active: '+(', '.join(names) if names else 'None'))
        dsn=os.getenv('QUANTLAB_DELIVERY_DB') or os.getenv('QUANTLAB_ALERT_DB') or 'artifacts/notifications.sqlite'
        if dsn.startswith(('postgres://','postgresql://')) or Path(dsn).exists():
            st.dataframe(DeliveryLedger(dsn).summary(),hide_index=True,use_container_width=True)
        st.markdown('### Outbound test')
        checked=st.checkbox('I authorize one real test message to each configured destination.')
        last=st.session_state.get('ql_last_notify_test_time',0.)
        remaining=max(0,int(60-(time.time()-last)))
        if remaining:st.caption(f'Next test allowed in {remaining} seconds.')
        if st.button('Send test notifications',type='primary',disabled=not checked or remaining>0 or not names):
            st.session_state['ql_last_notify_test_time']=time.time()
            try:
                adapters=channels_from_environment()
                test=Message('admin-test','NONE','','','','','','',0,'CHANNEL_TEST')
                for target in adapters:
                    try:
                        target.send(test)
                        st.success(f'{target.name.upper()}: provider accepted message')
                    except Exception as exc:
                        st.error(f'{target.name.upper()}: {type(exc).__name__} — check provider configuration and logs')
            except Exception as exc:
                st.error('Notification configuration invalid: '+type(exc).__name__)
    except Exception as exc:
        st.warning('Delivery ledger unavailable: '+type(exc).__name__)
    st.code('quantlab-notify --check\nquantlab-notify --once\nquantlab-notify --send-test --confirm-send',language='bash')
    st.caption('Provider acceptance is not verified handset/inbox delivery. Worker never accepts inbound order commands.')
elif page=='Audit & Operations':
    st.markdown('<div class="q-eyebrow">OPERATIONS / OBSERVABILITY</div>',unsafe_allow_html=True)
    st.title('Audit & Deployment')
    st.caption('Research events, alert history and engineering state.')
    if EVENTS.exists():
        rows=[]
        for line in EVENTS.read_text().splitlines()[-100:]:
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:continue
        if rows:st.dataframe(rows,hide_index=True,width='stretch')
        else:st.info('No alert events yet.')
    else:st.info('No alerts saved. This is normal before a verified feed is running.')
    st.code('docker compose -f deploy/docker-compose.yml up --build -d\npytest -q\nquantlab-quotes\nquantlab-edgar',language='bash')
    st.warning('A GitHub push does not create Render resources. Connect the Render Blueprint and configure protected secrets and console authentication.')
    st.caption('Read docs/AI_DEV_CHECKPOINT.md before modifying strategy logic or deploying.')

elif page=='Execution Consent':
    from quantlab.execution.consent import ConsentStore
    st.title('Strategy execution consent')
    st.caption('Grants authorize a scoped strategy for up to 24 hours. This release does NOT connect these grants to a running order-placement worker.')
    account=st.text_input('Account alias / ID',value='')
    strategy=st.text_input('Approved strategy ID',value='')
    notional=st.number_input('Maximum order notional ($)',min_value=1.0,max_value=10000.0,value=100.0)
    hours=st.number_input('Authorization duration (hours)',min_value=1,max_value=24,value=1)
    checked=st.checkbox('I authorize this named account and strategy within this notional and time limit')
    if st.button('Grant scoped permission',type='primary',disabled=not checked):
        from datetime import timedelta
        try:
            state=Path(os.getenv('QUANTLAB_CONSENT_DB','artifacts/consent.sqlite'))
            state.parent.mkdir(parents=True,exist_ok=True)
            grant=ConsentStore(str(state)).approve('admin',account,strategy,Decimal(str(notional)),timedelta(hours=hours))
            st.success('Scoped consent stored: '+grant.grant_id)
            st.caption('No live orders have been enabled or submitted. Integrate a broker-reconciled execution worker first.')
        except (ValueError,OSError) as exc:st.error(str(exc))
