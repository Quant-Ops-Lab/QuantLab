import json
import pytest
from quantlab.agents.experiment import EvidencePacket,trials,validate_proposal


def packet(outcome):
    return EvidencePacket('s','m','d','2026-11-12T00:00:00+00:00',
         ({'trade':'t','outcome':outcome},),{'slippage_bps':3.0})


@pytest.mark.parametrize('outcome',[-100.0,100.0])
def test_both_treatments_get_identical_packet(outcome):
    t=trials(packet(outcome))
    assert set(t)=={'preserve','challenge','neutral'}
    assert len({x['evidence_json'] for x in t.values()})==1
    assert len({x['evidence_sha256'] for x in t.values()})==1
    assert len({x['system_prompt'] for x in t.values()})==3


def test_output_cannot_authorize_order():
    proposal = validate_proposal(json.dumps({'verdict':'change_candidate',
        'claims':['check slippage'],'proposed_tests':['holdout cost sensitivity']}))
    assert 'allowed_to_trade' not in proposal
    with pytest.raises(ValueError):
        validate_proposal(json.dumps({'verdict':'change_candidate','claims':[],
           'proposed_tests':[],'submit_order':True}))
