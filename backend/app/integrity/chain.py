"""Per-device hash chain, plus the edge agent that seals each reading."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .keys import load_private_key
from .signing import canonical_json, sign

GENESIS_HASH = "0" * 64


def chain_hash(prev_hash: str, canonical: str, signature_hex: str) -> str:
    return hashlib.sha256((prev_hash + canonical + signature_hex).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SealedRecord:
    seq: int
    payload: dict
    canonical: str
    signature: str
    prev_hash: str
    hash: str


class EdgeAgent:
    """Simulated edge agent: signs readings and links them into the chain.

    One agent per device. It holds the private key and the chain head, exactly
    what a real gateway would keep locally.
    """

    def __init__(self, device_id: str, private_key_hex: str, seq: int = 0, prev_hash: str = GENESIS_HASH):
        self.device_id = device_id
        self._key = load_private_key(private_key_hex)
        self.seq = seq
        self.prev_hash = prev_hash

    def seal(self, reading: dict) -> SealedRecord:
        seq = self.seq + 1
        payload = {**reading, "device_id": self.device_id, "seq": seq}
        canonical = canonical_json(payload)
        signature = sign(self._key, canonical)
        record_hash = chain_hash(self.prev_hash, canonical, signature)
        record = SealedRecord(seq, payload, canonical, signature, self.prev_hash, record_hash)
        self.seq, self.prev_hash = seq, record_hash
        return record

    def reset_head(self, seq: int, prev_hash: str) -> None:
        self.seq, self.prev_hash = seq, prev_hash
