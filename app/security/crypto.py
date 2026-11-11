"""SHIFT-inspired message security for ContextIQ-originated messages (QR sessions, agent handshakes).

Ed25519 signatures + timestamp + single-use nonce = authenticity, integrity, freshness, replay
protection. PayPal's own traffic is protected by PayPal (OAuth, webhook verification); this
layer protects messages ContextIQ itself creates.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from ..config import DATA_DIR, settings
from ..models import UsedNonce

_KEY_FILE = DATA_DIR / "ed25519_signing_key.pem"


def _load_key() -> Ed25519PrivateKey:
    if _KEY_FILE.exists():
        return serialization.load_pem_private_key(_KEY_FILE.read_bytes(), password=None)  # type: ignore[return-value]
    key = Ed25519PrivateKey.generate()
    _KEY_FILE.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()))
    return key


_PRIVATE = _load_key()
PUBLIC: Ed25519PublicKey = _PRIVATE.public_key()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def public_key_b64() -> str:
    return _b64(PUBLIC.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def sign_message(payload: dict, ttl: int | None = None) -> str:
    body = dict(payload)
    body["iat"] = int(time.time())
    body["exp"] = body["iat"] + (ttl or settings.qr_ttl_seconds)
    body["nonce"] = secrets.token_urlsafe(12)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return f"ciq1.{_b64(raw)}.{_b64(_PRIVATE.sign(raw))}"


class TokenError(Exception):
    pass


def verify_message(db: Session, token: str, consume: bool = True) -> dict:
    try:
        prefix, body_b64, sig_b64 = token.split(".")
        assert prefix == "ciq1"
        raw, sig = _unb64(body_b64), _unb64(sig_b64)
    except Exception as exc:  # noqa: BLE001
        raise TokenError("malformed token") from exc
    try:
        PUBLIC.verify(sig, raw)
    except Exception as exc:  # noqa: BLE001
        raise TokenError("bad signature: token was altered or not issued by ContextIQ") from exc
    body = json.loads(raw)
    if time.time() > body["exp"]:
        raise TokenError("expired")
    if db.get(UsedNonce, body["nonce"]):
        raise TokenError("replay detected: this QR/session token was already used")
    if consume:
        db.add(UsedNonce(value=body["nonce"]))
        db.commit()
    return body


def hmac_token(*parts: str) -> str:
    msg = "|".join(parts).encode()
    return hmac.new(settings.server_secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
