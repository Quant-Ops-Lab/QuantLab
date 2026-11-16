"""Single-writer SQLite journal of untrusted agent review proposals.

This is a research audit log, NOT an order ledger or multi-process execution DB.
SQLite transactions and chained hashes provide basic corruption/tamper detection,
not protection against a privileged adversary rewriting the entire database.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from .experiment import EvidencePacket, trials, validate_proposal


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class ReviewStore:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS review_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_sha TEXT NOT NULL, role TEXT NOT NULL,
            prompt_sha TEXT NOT NULL, proposal_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL
        )""")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def append(self, packet: EvidencePacket, role: str, proposal_json: str) -> str:
        if role not in ('preserve', 'challenge', 'neutral'):
            raise ValueError('unsupported review role')
        validated = validate_proposal(proposal_json)
        normalized = json.dumps(validated, sort_keys=True, separators=(',', ':'), allow_nan=False)
        prompt_sha = digest(trials(packet)[role]['system_prompt'])
        with self.conn:
            previous_row = self.conn.execute(
                'SELECT record_hash FROM review_events ORDER BY seq DESC LIMIT 1'
            ).fetchone()
            prev = previous_row[0] if previous_row else 'GENESIS'
            body = json.dumps([packet.sha256, role, prompt_sha, normalized, prev],
                              separators=(',', ':'))
            record_hash = digest(body)
            self.conn.execute("""INSERT INTO review_events
                (evidence_sha,role,prompt_sha,proposal_json,previous_hash,record_hash)
                VALUES (?,?,?,?,?,?)""",
                (packet.sha256,role,prompt_sha,normalized,prev,record_hash))
        return record_hash

    def verify_chain(self) -> bool:
        prev = 'GENESIS'
        rows = self.conn.execute("""SELECT evidence_sha,role,prompt_sha,
                  proposal_json,previous_hash,record_hash
                  FROM review_events ORDER BY seq""").fetchall()
        for evidence,role,prompt,proposal,claimed_prev,claimed_hash in rows:
            body = json.dumps([evidence,role,prompt,proposal,prev], separators=(',', ':'))
            if claimed_prev != prev or digest(body) != claimed_hash:
                return False
            prev = claimed_hash
        return True
