"""Optional authenticated API shell. Never exposes submit_order endpoints.

For remote use terminate TLS at a trusted gateway, require identity-aware access,
rotate tokens, and enforce per-role permissions; token auth is a prototype only.
"""
from __future__ import annotations
import hmac
import os
from .contracts import StrategySpec


def create_app():
    from fastapi import FastAPI, Depends, Header, HTTPException
    from pydantic import BaseModel

    token=os.environ.get('QUANTLAB_OPERATOR_TOKEN','')
    if len(token)<24:
        raise RuntimeError('QUANTLAB_OPERATOR_TOKEN must be set to a long random token')
    app=FastAPI(title='QuantLab Control API',version='0.2.0',docs_url=None,redoc_url=None)
    def require_auth(authorization: str = Header(default='')):
        if not hmac.compare_digest(authorization, 'Bearer '+token):
            raise HTTPException(status_code=401,detail='unauthorized')
    class StrategyBody(BaseModel):
        spec: dict

    @app.get('/health',dependencies=[Depends(require_auth)])
    def health():return {'status':'ok','order_writes':False,'market_feed':False,'version':'0.2.0'}

    @app.post('/v1/strategies/validate',dependencies=[Depends(require_auth)])
    def validate(body:StrategyBody):
        try:
            spec=StrategySpec.from_dict(body.spec)
        except (ValueError,TypeError,KeyError) as exc:
            raise HTTPException(status_code=422,detail=str(exc)) from exc
        return {'valid':True,'fingerprint':spec.fingerprint,'mode':spec.mode.value,'order_writes':False}
    return app
