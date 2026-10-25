"""Canonical serialization and Ed25519 signatures over telemetry payloads."""
from __future__ import annotations

import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .keys import load_public_key


def canonical_json(payload: dict) -> str:
    """Sorted keys, no whitespace. Callers pre-round floats so this is stable."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(private_key: Ed25519PrivateKey, canonical: str) -> str:
    return private_key.sign(canonical.encode("utf-8")).hex()


def verify_signature(public_key: Ed25519PublicKey | str, canonical: str, signature_hex: str) -> bool:
    if isinstance(public_key, str):
        public_key = load_public_key(public_key)
    try:
        public_key.verify(bytes.fromhex(signature_hex), canonical.encode("utf-8"))
    except (InvalidSignature, ValueError):
        return False
    return True
