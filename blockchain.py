from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, asdict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

from db import db_session, get_chain_height, get_latest_block_hash, sign_block_hash, utcnow_iso


load_dotenv()


@dataclass
class Transaction:
    type: str
    candidate_id: int
    candidate_name: str


def _block_hash(index: int, timestamp: str, previous_hash: str, nonce: int, transactions_json: str) -> str:
    payload = f"{index}|{timestamp}|{previous_hash}|{nonce}|{transactions_json}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_block_signature(block_hash: str, signature_b64: str) -> bool:
    if not signature_b64:
        return False
    try:
        from os import getenv

        seed_b64 = getenv("CHAIN_PRIVATE_KEY_B64", "").strip()
        if not seed_b64:
            return False
        seed = base64.b64decode(seed_b64)
        if len(seed) != 32:
            return False
        public_key = Ed25519PrivateKey.from_private_bytes(seed).public_key()
        public_key.verify(base64.b64decode(signature_b64), block_hash.encode("utf-8"))
        return True
    except Exception:
        return False


def add_vote_block(transaction: Transaction) -> str:
    with db_session() as conn:
        index = get_chain_height() + 1
        timestamp = utcnow_iso()
        previous_hash = get_latest_block_hash()
        transactions_json = json.dumps([asdict(transaction)], sort_keys=True)
        nonce = 0
        block_hash = _block_hash(index, timestamp, previous_hash, nonce, transactions_json)
        signature = sign_block_hash(block_hash)
        conn.execute(
            "INSERT INTO blocks (block_index, timestamp, previous_hash, hash, signature, nonce, transactions_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (index, timestamp, previous_hash, block_hash, signature, nonce, transactions_json),
        )
        return block_hash


def validate_chain(blocks) -> list[str]:
    errors: list[str] = []
    ordered = list(reversed(blocks))
    previous_hash = "0" * 64
    for block in ordered:
        expected = _block_hash(
            int(block["block_index"]),
            str(block["timestamp"]),
            previous_hash,
            int(block["nonce"]),
            str(block["transactions_json"]),
        )
        if expected != block["hash"]:
            errors.append(f"Block {block['block_index']} hash mismatch")
        elif not verify_block_signature(str(block["hash"]), str(block["signature"])):
            errors.append(f"Block {block['block_index']} signature invalid")
        previous_hash = str(block["hash"])
    return errors
