"""Consumer investing experience. Read-only until broker integration is verified.

A consumer sees their actual connected positions only; no invented portfolio.
Admin access is controlled separately by the host identity layer and app gate.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import json
import os
import streamlit as st
from quantlab.console.charts import candlestick_figure,Candle
from quantlab.console.research_assistant import answer as answer_research_question
from quantlab.console.news_views import bucket_news
from quantlab.console.llm import build_research_model
from quantlab.console.alerts import alert_wav
from quantlab.market.kraken_rest import KrakenPublic,PAIRS,KrakenDataError
from quantlab.market.alpaca_data import AlpacaData,MarketDataError
from quantlab.universe.catalog import default_universe
from quantlab.console.integrations import integration_statuses

@st.cache_data(ttl=30,show_spinner=False)
def _crypto(pair:str,interval:str):
    return [{'start': item.start.isoformat(), 'open': item.open, 'high': item.high,
             'low': item.low, 'close': item.close, 'samples': item.samples,
             'volume': item.volume} for item in KrakenPublic().ohlc(pair,interval)]

@st.cache_data(ttl=60,show_spinner=False)
def _equity(symbol:str,interval:str):
    # Read keys on server and do not put them in cache arguments or return values.
    key=os.getenv('APCA_API_KEY_ID','');secret=os.getenv('APCA_API_SECRET_KEY','')
    tf={'1m':'1Min','5m':'5Min','15m':'15Min','1h':'1Hour','1d':'1Day'}[interval]
    result=AlpacaData(key,secret).bars(symbol,tf,days=20 if interval!='1d' else 120,limit=300)
    return [{'start': item.timestamp.isoformat(), 'open': item.open, 'high': item.high,
             'low': item.low, 'close': item.close, 'samples': 1,
             'volume': item.volume} for item in result]


@st.cache_data(ttl=120,show_spinner=False)
def _stock_news(symbol:str):
    key=os.getenv('APCA_API_KEY_ID','');secret=os.getenv('APCA_API_SECRET_KEY','')
    if not (key and secret):return []
    return [{'headline_id': item.headline_id, 'headline': item.headline,
             'summary': item.summary, 'url': item.url, 'symbols': list(item.symbols),
             'source': item.source, 'published_at': item.published_at.isoformat(),
             'provider': item.provider}
            for item in AlpacaData(key,secret).news([symbol],limit=50)]


def _candles(rows):
    return [Candle(datetime.fromisoformat(row['start']),row['open'],row['high'],row['low'],
                   row['close'],row.get('samples',1),row.get('volume')) for row in rows]


def _context_events(symbol:str,limit:int=500):
    database=os.getenv('QUANTLAB_EVENT_DB','artifacts/events.sqlite')
    if not database.startswith(('postgresql://','postgres://')) and not Path(database).exists():return []
    from quantlab.intelligence.events import EventJournal
    return [e for e in EventJournal(database).recent(limit) if symbol in e.get('symbols',[])]


def _alerts(max_lines:int=40):
    database=os.getenv('QUANTLAB_ALERT_DB','')
    if database:
        try:
            from quantlab.control.alert_store import AlertJournal
            return AlertJournal(database).recent(limit=max_lines)
        except Exception:
            return []
    path=Path(os.getenv('QUANTLAB_ALERTS_FILE','artifacts/alerts.jsonl'))
    if not path.is_file():return []
    # Cap memory usage and ignore badly formed lines.
    from collections import deque
    lines=deque(maxlen=max_lines)
    with path.open('r',encoding='utf-8') as stream:
        for line in stream:
            try:
                event=json.loads(line)
                if event.get('topic')=='quantlab/signals/alert':lines.append(event)
            except (ValueError,TypeError):continue
    return list(reversed(lines))


def render(theme:str='Deck'):
    st.markdown('<div class="ql-kicker">QUANTLAB / INVEST</div>',unsafe_allow_html=True)
    st.markdown('<div class="ql-hero"><div class="ql-status">Research mode · execution disabled</div><div class="ql-hero-title">Your market, with the evidence left visible.</div><div class="ql-hero-meta">Live observations, source-linked news, and scenario analysis without fabricated prices or hidden broker authority.</div></div>',unsafe_allow_html=True)
    tab1,tab2,tab3,tab4=st.tabs(['Markets','Portfolio','Signals','Integrations'])
    with tab1:
        universe=default_universe()
        asset=st.segmented_control('Asset class',['Stocks & ETFs','Crypto'],default='Stocks & ETFs')
        col1,col2,col3=st.columns([3,1,1])
        if asset=='Crypto':
            symbol=col1.selectbox('Market',list(PAIRS),format_func=lambda s:s+'  · Kraken spot')
        else:
            symbol=col1.selectbox('Market',list(universe),index=list(universe).index('NVDA') if 'NVDA' in universe else 0,
                format_func=lambda s:s+'  · '+universe[s].name)
        frame=col2.selectbox('Interval',['1m','5m','15m','1h','1d'],index=1)
        col3.metric('Feed','Kraken public' if asset=='Crypto' else 'Alpaca IEX')
        chart_controls=st.container(horizontal=True)
        show_volume=chart_controls.toggle('Volume',value=True)
        show_ema=chart_controls.toggle('Trend overlays',value=True)
        show_range=chart_controls.toggle('Range navigator',value=True)
        bars=[]
        try:
            if asset=='Crypto':bars=_candles(_crypto(symbol,frame));label='Kraken · exchange OHLC · last unfinished bar excluded'
            else:
                key=os.getenv('APCA_API_KEY_ID','');secret=os.getenv('APCA_API_SECRET_KEY','')
                if not (key and secret):raise MarketDataError('Alpaca API credentials not configured')
                bars=_candles(_equity(symbol,frame))
                label='Alpaca · IEX single-venue trades · not consolidated SIP'
            if bars:
                last=bars[-1]
                x,y,z=st.columns(3)
                x.metric('Latest completed close',f'${last.close:,.2f}')
                y.metric('Observed OHLC bars',len(bars))
                z.metric('Last bar (UTC)',last.start.strftime('%b %d %H:%M'))
                chart=candlestick_figure(bars,symbol,show_volume=show_volume,show_ema=show_ema,show_range=show_range)
                from quantlab.console.theme import THEMES
                p=THEMES[theme]
                chart.update_layout(paper_bgcolor=p['surface'],plot_bgcolor=p['surface'],font={'color':p['muted']})
                st.plotly_chart(chart,width='stretch',config={'displaylogo':False,'scrollZoom':True})
                st.caption(label+' · For execution, check a fresh top-of-book bid/ask; charts are not executable quotes.')
            else:st.info('Provider returned no completed market candles.')
        except (KrakenDataError,MarketDataError,ValueError) as exc:
            st.warning(f'Live source unavailable: {exc}. No sample price has been substituted.')
        st.subheader('Public news and filings')
        recent_news=[]
        context_events=[]
        try:
            if asset=='Stocks & ETFs':
                recent_news=_stock_news(symbol)
            context_events=_context_events(symbol,500)
            news_buckets=bucket_news([*recent_news,*context_events])
            window=st.segmented_control('News window',['today','7 days','14 days','31 days'],default='today')
            records=news_buckets[window]
            if records:
                st.dataframe([
                    {'Published':item.published_at.strftime('%Y-%m-%d %H:%M UTC'),
                     'Source':item.source,'Type':item.kind,'Headline':item.headline}
                    for item in records
                ],hide_index=True,width='stretch',height=280,
                column_config={'Published':st.column_config.TextColumn('Published'),
                               'Headline':st.column_config.TextColumn('Headline',width='large')})
                selected_index=st.selectbox('Open source detail',range(len(records)),
                    format_func=lambda i:records[i].headline,key='ql_news_detail')
                selected_story=records[selected_index]
                with st.container(border=True):
                    st.markdown('**'+selected_story.headline+'**')
                    st.caption(f'{selected_story.source} · {selected_story.published_at.strftime("%Y-%m-%d %H:%M UTC")} · {selected_story.kind}')
                    if selected_story.summary:st.write(selected_story.summary)
                    if selected_story.url.startswith('https://'):st.link_button('Open original source',selected_story.url)
            else:
                st.info('No timestamped news or filing records in this window.')
            if os.getenv('QUANTLAB_ENABLE_PUBLIC_NEWS_ARCHIVE','0')=='1':
                with st.expander('Long-history archive'):
                    archive=news_buckets['archive']
                    st.dataframe([{'Published':item.published_at.strftime('%Y-%m-%d %H:%M UTC'),
                                   'Source':item.source,'Type':item.kind,'Headline':item.headline}
                                  for item in archive],hide_index=True,width='stretch',height=320)
            else:
                st.caption('History older than 31 days is reserved for the Admin research view.')
        except Exception as exc:st.info('Current news unavailable: '+type(exc).__name__)
        st.caption('News classification does not prove claims or predictive price impact. X/Grok requires separate paid access.')
        st.divider()
        st.subheader('Ask the research assistant')
        model_configured=bool(os.getenv('QUANTLAB_LLM_BASE_URL') and os.getenv('QUANTLAB_LLM_API_KEY') and os.getenv('QUANTLAB_LLM_MODEL'))
        st.caption('Answers use only the selected instrument, observed candles, stored alerts, and verified disclosures. No orders or personalized advice.' + (' Configured model: evidence-bounded.' if model_configured else ' Deterministic fallback: no model configured.'))
        suggestions=['Is this a good trade?', 'What happened historically?', 'What is this asset used for?']
        if 'ql_research_messages' not in st.session_state:
            st.session_state['ql_research_messages']=[]
        for message in st.session_state['ql_research_messages'][-8:]:
            with st.chat_message(message['role']):
                st.write(message['content'])
        selected=st.pills('Try a question',suggestions,label_visibility='collapsed')
        prompt=st.chat_input('Ask about trade quality, history, or utility',key='ql_research_prompt')
        prompt=prompt or selected
        if prompt:
            st.session_state['ql_research_messages'].append({'role':'user','content':prompt})
            with st.chat_message('user'):
                st.write(prompt)
            evidence_events=context_events
            evidence_alerts=_alerts()
            research_model=build_research_model()
            response=answer_research_question(symbol,prompt,bars,
                asset=universe.get(symbol) if asset=='Stocks & ETFs' else None,
                events=evidence_events,alerts=evidence_alerts,news=recent_news,model=research_model)
            st.session_state['ql_research_messages'].append({'role':'assistant','content':response})
            with st.chat_message('assistant',avatar=':material/insights:'):
                st.write(response)
    with tab2:
        st.markdown('<div class="ql-kicker">HOLDINGS / ACCOUNT</div>',unsafe_allow_html=True)
        st.subheader('Connect a verified brokerage portfolio')
        st.info('No authenticated account balance or holdings are available in this view. Connect a read-only broker adapter before displaying positions or performance.')
        st.caption('No order is submitted from the consumer dashboard. A future order sheet must display verified buying power, estimate, stop, target and broker acknowledgment.')
    with tab3:
        st.markdown('<div class="ql-kicker">NOTIFICATIONS / TRADE PLANS</div>',unsafe_allow_html=True)
        col1,col2=st.columns([3,1])
        col1.caption('Plans include a proposed entry, stop and target; they are not guaranteed profitable. Sound may require user interaction per browser policy.')
        with col2:
            if st.button('Test audible alert'):
                st.audio(alert_wav(),format='audio/wav',autoplay=True)
        @st.fragment(run_every='5s')
        def live_alerts():
            alerts=_alerts()
            newest=(alerts[0].get('payload') or {}).get('signal',{}).get('signal_id') if alerts else None
            if newest and st.session_state.get('ql_last_signal') and st.session_state['ql_last_signal']!=newest:
                st.audio(alert_wav(),format='audio/wav',autoplay=True)
            if newest:st.session_state['ql_last_signal']=newest
            if not alerts:
                st.info('No verified alerts yet. Start the research daemon to ingest live market observations.')
            for event in alerts[:20]:
                payload=event.get('payload') or {}
                plan=payload.get('signal') if isinstance(payload.get('signal'),dict) else {}
                if plan:
                    st.markdown(f'**{plan.get("symbol","?")} · {plan.get("direction","NONE")}** · {plan.get("status","NO_TRADE")}')
                    st.caption('Entry '+str(plan.get('entry'))+' · Stop '+str(plan.get('stop'))+' · Target '+str(plan.get('take_profit')))
                    st.caption('Executed: NO · Candidate plan only, unverified against current broker quotes')
                else:st.json(payload)
                st.divider()
        live_alerts()
    with tab4:
        st.subheader('Connections')
        integrations=integration_statuses(os.environ)
        st.dataframe([{'Provider':i.name,'Type':i.category,'Status':i.status} for i in integrations],hide_index=True,use_container_width=True)
        st.caption('Configured means credentials/environment are present, NOT that API connectivity has been verified.')
