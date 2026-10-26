"""Ed25519 keys: release engineering signs releases, each station signs what it records."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def generate(path: Path) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    )
    path.chmod(0o600)
    return key


def load_private(path: Path) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(path.read_bytes())


def public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def fingerprint(public: str) -> str:
    return hashlib.sha256(bytes.fromhex(public)).hexdigest()[:16]


def sign(key: Ed25519PrivateKey, message: bytes) -> str:
    return key.sign(message).hex()


def verify(public: str, message: bytes, signature: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(bytes.fromhex(signature), message)
        return True
    except (InvalidSignature, ValueError):
        return False
