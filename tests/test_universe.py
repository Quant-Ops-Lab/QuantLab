from quantlab.universe.catalog import default_universe,by_theme,RESEARCH_ONLY,AssetKind

def test_watch_universe_covers_ai_chips_software_materials_metals():
    watch=default_universe()
    assert len(watch)>=35
    for symbol in ('NVDA','AMD','MU','SNDK','MSFT','ENTG','MTRN','GLD','SLV','MP','REMX','SMH','TLT'):
        assert symbol in watch
    assert len(by_theme('ai_compute'))>=6
    assert len({a.symbol for a in watch.values()})==len(watch)

def test_nonmarketable_not_tradeable():
    assert all(not item.intraday_candidate for item in RESEARCH_ONLY)
    assert {item.kind for item in RESEARCH_ONLY}=={AssetKind.SAVINGS_BOND,AssetKind.PRIVATE}
