"""Transactional DB connection helper. SQLite for one host, PostgreSQL for services.

Designed for event and quote journals; live broker order reservations need a
separate account-scoped lease and atomic buying-power reservations.
"""
from __future__ import annotations
import sqlite3


def is_postgres(dsn:str)->bool:
    return dsn.startswith(('postgresql://','postgres://'))


def connect(dsn:str):
    if is_postgres(dsn):
        try:import psycopg
        except ImportError as exc:raise RuntimeError("pip install '.[postgres]' is required") from exc
        return psycopg.connect(dsn)
    if dsn.startswith('sqlite:///'):
        dsn=dsn[len('sqlite:///'):]
    return sqlite3.connect(dsn)


def bind(dsn:str)->str:
    return '%s' if is_postgres(dsn) else '?'
