import json
from quantlab.agents.experiment import EvidencePacket
from quantlab.agents.review_store import ReviewStore


def test_agent_journal_integrity_and_detection(tmp_path):
    packet = EvidencePacket('s','m','d','2026-11-12T00:00:00+00:00',
           ({'result':'loss'},),{'costs_bps':2})
    path = tmp_path / 'reviews.sqlite'
    store = ReviewStore(path)
    for role in ('preserve','challenge','neutral'):
        store.append(packet,role,json.dumps({'verdict':'investigate',
              'claims':['possible overfit'],'proposed_tests':['walkforward']}))
    assert store.verify_chain()
    store.conn.execute("UPDATE review_events SET proposal_json='tampered' WHERE seq=2")
    store.conn.commit()
    assert not store.verify_chain()
    store.close()
