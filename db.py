from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

from voting_data import DB_PATH, HARD_CODED_CANDIDATES


load_dotenv()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_private_key() -> Ed25519PrivateKey:
    key_b64 = os.getenv("CHAIN_PRIVATE_KEY_B64", "").strip()
    if not key_b64:
        raise RuntimeError("CHAIN_PRIVATE_KEY_B64 is missing from .env")
    seed = base64.b64decode(key_b64)
    if len(seed) != 32:
        raise RuntimeError("CHAIN_PRIVATE_KEY_B64 must decode to 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def sign_block_hash(block_hash: str) -> str:
    signature = _load_private_key().sign(block_hash.encode("utf-8"))
    return base64.b64encode(signature).decode("ascii")


def get_db_path() -> Path:
    return Path(DB_PATH)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS voters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                number TEXT NOT NULL,
                email TEXT NOT NULL,
                photo_blob BLOB,
                face_blob BLOB NOT NULL,
                created_at TEXT NOT NULL,
                voted INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                party TEXT NOT NULL,
                symbol TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voter_id INTEGER NOT NULL,
                candidate_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                FOREIGN KEY(voter_id) REFERENCES voters(id),
                FOREIGN KEY(candidate_id) REFERENCES candidates(id)
            );

            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                hash TEXT NOT NULL,
                signature TEXT NOT NULL DEFAULT '',
                nonce INTEGER NOT NULL,
                transactions_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rfid_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfid TEXT NOT NULL,
                source TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        existing = conn.execute("SELECT COUNT(*) AS count FROM candidates").fetchone()["count"]
        if existing == 0:
            conn.executemany(
                "INSERT INTO candidates (id, name, party, symbol) VALUES (?, ?, ?, ?)",
                [(c.id, c.name, c.party, c.symbol) for c in HARD_CODED_CANDIDATES],
            )

        block_count = conn.execute("SELECT COUNT(*) AS count FROM blocks").fetchone()["count"]
        if block_count == 0:
            genesis_transactions = [{"type": "genesis", "message": "Demo chain initialized"}]
            genesis_timestamp = utcnow_iso()
            genesis_payload = json.dumps(genesis_transactions, sort_keys=True)
            genesis_hash = hashlib.sha256(
                f"0|{genesis_timestamp}|{'0' * 64}|0|{genesis_payload}".encode("utf-8")
            ).hexdigest()
            genesis_signature = sign_block_hash(genesis_hash)
            conn.execute(
                "INSERT INTO blocks (block_index, timestamp, previous_hash, hash, signature, nonce, transactions_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (0, genesis_timestamp, "0" * 64, genesis_hash, genesis_signature, 0, genesis_payload),
            )

        cols = {row["name"] for row in conn.execute("PRAGMA table_info(blocks)").fetchall()}
        if "signature" not in cols:
            conn.execute("ALTER TABLE blocks ADD COLUMN signature TEXT NOT NULL DEFAULT ''")

        voter_cols = {row["name"] for row in conn.execute("PRAGMA table_info(voters)").fetchall()}
        if "photo_blob" not in voter_cols:
            conn.execute("ALTER TABLE voters ADD COLUMN photo_blob BLOB")

        for row in conn.execute("SELECT id, hash FROM blocks WHERE signature = ''").fetchall():
            conn.execute(
                "UPDATE blocks SET signature = ? WHERE id = ?",
                (sign_block_hash(str(row["hash"])), row["id"]),
            )

        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_voter_id ON votes(voter_id)")


def fetchall(query: str, params: Iterable[Any] = ()):
    with db_session() as conn:
        return conn.execute(query, tuple(params)).fetchall()


def fetchone(query: str, params: Iterable[Any] = ()):
    with db_session() as conn:
        return conn.execute(query, tuple(params)).fetchone()


def add_rfid_event(rfid: str, source: str) -> None:
    with db_session() as conn:
        active = conn.execute("SELECT COUNT(*) AS count FROM rfid_events WHERE consumed = 0").fetchone()["count"]
        overflow = max(0, int(active) - 1)
        if overflow > 0:
            conn.execute(
                "DELETE FROM rfid_events WHERE id IN (SELECT id FROM rfid_events WHERE consumed = 0 ORDER BY id ASC LIMIT ?)",
                (overflow,),
            )
        conn.execute(
            "INSERT INTO rfid_events (rfid, source, consumed, created_at) VALUES (?, ?, 0, ?)",
            (rfid.strip(), source, utcnow_iso()),
        )


def clear_rfid_events() -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM rfid_events")


def get_latest_rfid_event() -> sqlite3.Row | None:
    with db_session() as conn:
        return conn.execute(
            "SELECT * FROM rfid_events WHERE consumed = 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()


def get_active_rfid_events():
    return fetchall("SELECT * FROM rfid_events WHERE consumed = 0 ORDER BY id DESC")


def consume_rfid_event(event_id: int) -> None:
    with db_session() as conn:
        conn.execute("UPDATE rfid_events SET consumed = 1 WHERE id = ?", (event_id,))


def upsert_voter(rfid: str, name: str, number: str, email: str, face_blob: bytes, photo_blob: bytes | None = None) -> None:
    with db_session() as conn:
        row = conn.execute("SELECT id FROM voters WHERE rfid = ?", (rfid,)).fetchone()
        if row:
            conn.execute(
                "UPDATE voters SET name = ?, number = ?, email = ?, face_blob = ?, photo_blob = COALESCE(?, photo_blob), created_at = ? WHERE rfid = ?",
                (name, number, email, face_blob, photo_blob, utcnow_iso(), rfid),
            )
        else:
            conn.execute(
                "INSERT INTO voters (rfid, name, number, email, photo_blob, face_blob, created_at, voted) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (rfid, name, number, email, photo_blob, face_blob, utcnow_iso()),
            )


def get_voter_by_rfid(rfid: str):
    with db_session() as conn:
        return conn.execute("SELECT * FROM voters WHERE rfid = ?", (rfid,)).fetchone()


def mark_voted(voter_id: int) -> None:
    with db_session() as conn:
        conn.execute("UPDATE voters SET voted = 1 WHERE id = ?", (voter_id,))


def insert_vote(voter_id: int, candidate_id: int, tx_hash: str) -> int:
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO votes (voter_id, candidate_id, created_at, tx_hash) VALUES (?, ?, ?, ?)",
            (voter_id, candidate_id, utcnow_iso(), tx_hash),
        )
        return int(cur.lastrowid)


def get_candidates():
    return fetchall("SELECT * FROM candidates ORDER BY id")


def get_voters():
    return fetchall("SELECT * FROM voters ORDER BY id")


def update_voter(voter_id: int, rfid: str, name: str, number: str, email: str) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE voters SET rfid = ?, name = ?, number = ?, email = ? WHERE id = ?",
            (rfid.strip(), name.strip(), number.strip(), email.strip(), voter_id),
        )


def voter_vote_count(voter_id: int) -> int:
    row = fetchone("SELECT COUNT(*) AS count FROM votes WHERE voter_id = ?", (voter_id,))
    return int(row["count"] or 0)


def delete_voter(voter_id: int) -> None:
    with db_session() as conn:
        voter = conn.execute("SELECT rfid FROM voters WHERE id = ?", (voter_id,)).fetchone()
        if voter is None:
            return
        conn.execute("DELETE FROM rfid_events WHERE rfid = ?", (voter["rfid"],))
        conn.execute("DELETE FROM voters WHERE id = ?", (voter_id,))


def get_votes():
    return fetchall(
        """
        SELECT votes.*, candidates.name AS candidate_name, candidates.party AS candidate_party
        FROM votes
        JOIN candidates ON candidates.id = votes.candidate_id
        ORDER BY votes.id DESC
        """
    )


def get_blocks():
    return fetchall("SELECT * FROM blocks ORDER BY block_index DESC")


def get_chain_height() -> int:
    row = fetchone("SELECT MAX(block_index) AS height FROM blocks")
    return int(row["height"] or 0)


def get_latest_block_hash() -> str:
    row = fetchone("SELECT hash FROM blocks ORDER BY block_index DESC LIMIT 1")
    return str(row["hash"])


def get_vote_counts() -> list[sqlite3.Row]:
    return fetchall(
        """
        SELECT candidates.id, candidates.name, candidates.party, candidates.symbol, COUNT(votes.id) AS vote_count
        FROM candidates
        LEFT JOIN votes ON votes.candidate_id = candidates.id
        GROUP BY candidates.id, candidates.name, candidates.party, candidates.symbol
        ORDER BY candidates.id
        """
    )
