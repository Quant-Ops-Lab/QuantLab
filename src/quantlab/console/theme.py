"""NullPoint-inspired shared design tokens for Streamlit applications."""
THEMES={
'Neon':{'bg':'#071018','surface':'#0b1821','surface2':'#102631','text':'#ecfeff','muted':'#8eb6bf','accent':'#56f6ff','edge':'#1a5964','positive':'#b7ff72','negative':'#ff6bd6','mono':False},
'Deck':{'bg':'#0b100e','surface':'#141c17','surface2':'#1a241e','text':'#e8f0ea','muted':'#8fa398','accent':'#c4a574','edge':'#30443a','positive':'#2ec27e','negative':'#e85d5d','mono':False},
'Standard':{'bg':'#eef2f7','surface':'#ffffff','surface2':'#f2f6fa','text':'#16233a','muted':'#5d6b80','accent':'#1668e3','edge':'#d5deea','positive':'#1f9d55','negative':'#d53a38','mono':False},
'Terminal':{'bg':'#030804','surface':'#05130a','surface2':'#07190d','text':'#b8ffd1','muted':'#55d886','accent':'#35f57d','edge':'#10361d','positive':'#35f57d','negative':'#ff5f56','mono':True},
'Blackout':{'bg':'#050505','surface':'#0a0a0a','surface2':'#101010','text':'#f2f2f2','muted':'#9a9a9a','accent':'#d8d8d8','edge':'#222222','positive':'#2ec27e','negative':'#ff5f56','mono':False},
}

def css(name:str)->str:
    if name not in THEMES:raise ValueError('unknown theme')
    p=THEMES[name]
    family="'SF Mono',Menlo,Consolas,monospace" if p['mono'] else "'Avenir Next','Segoe UI',sans-serif"
    return f'''<style>
    :root {{--ql-bg:{p['bg']};--ql-surface:{p['surface']};--ql-surface2:{p['surface2']};--ql-text:{p['text']};--ql-muted:{p['muted']};--ql-accent:{p['accent']};--ql-edge:{p['edge']};}}
    [data-testid="stAppViewContainer"]{{background:var(--ql-bg)!important;color:var(--ql-text)!important;font-family:{family}!important;}}
    [data-testid="stSidebar"]{{background:var(--ql-surface)!important;border-right:1px solid var(--ql-edge)!important;}}
    [data-testid="stMetric"],.ql-card{{background:var(--ql-surface)!important;border:1px solid var(--ql-edge)!important;border-radius:6px!important;box-shadow:0 0 0 1px color-mix(in srgb,var(--ql-accent) 8%,transparent),0 0 24px color-mix(in srgb,var(--ql-accent) 8%,transparent);}}
    [data-testid="stMetricValue"],h1,h2,h3{{color:var(--ql-text)!important;}}
    [data-testid="stMetricLabel"],small,.ql-muted{{color:var(--ql-muted)!important;}}
    .ql-kicker{{font-family:{family};font-size:0.7rem;letter-spacing:.15em;text-transform:uppercase;color:var(--ql-accent)!important;font-weight:700;}}
    [data-testid="stTabs"] button[aria-selected="true"]{{color:var(--ql-accent)!important;border-color:var(--ql-accent)!important;}}
    button[kind="primary"]{{background:var(--ql-accent)!important;color:var(--ql-bg)!important;border-radius:4px!important;}}
    [data-testid="stDataFrame"],input{{border-radius:4px!important;}}
    .ql-card{{padding:14px;margin:0 0 12px;}}
    .ql-hero{{background:linear-gradient(115deg,color-mix(in srgb,var(--ql-accent) 16%,var(--ql-surface)),var(--ql-surface2));border:1px solid var(--ql-edge);border-radius:10px;padding:22px 24px;margin:0 0 18px;box-shadow:0 0 32px color-mix(in srgb,var(--ql-accent) 12%,transparent);}}
    .ql-hero-title{{font-size:1.75rem;font-weight:750;letter-spacing:-.03em;color:var(--ql-text);}}
    .ql-hero-meta{{color:var(--ql-muted);font-size:.84rem;margin-top:5px;}}
    .ql-status{{display:inline-block;color:var(--ql-positive);border:1px solid var(--ql-positive);border-radius:999px;padding:3px 9px;font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;}}
    </style>'''
