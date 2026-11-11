"""Passkeys (WebAuthn) — the independent verification factor for step-up.

A passkey proves possession of a device key plus the user's fingerprint/face/PIN on that device, so it is
genuinely a second factor (unlike password + PIN). Registration and sign-in follow the WebAuthn standard
via the `webauthn` library; challenges are single-use and expire after 5 minutes.
"""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..config import settings
from ..models import Approval, Passkey, User

ORIGIN = settings.public_base_url.rstrip("/")
RP_ID = urlparse(ORIGIN).hostname or "localhost"
_challenges: dict[str, tuple[bytes, float]] = {}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _take(key: str) -> bytes:
    ch, exp = _challenges.pop(key, (None, 0))
    if not ch or time.time() > exp:
        raise ValueError("this request has expired — please try again")
    return ch


def registration_options(db: Session, user: User) -> dict:
    existing = db.scalars(select(Passkey).where(Passkey.user_id == user.id)).all()
    opts = generate_registration_options(
        rp_id=RP_ID, rp_name="ContextIQ", user_id=user.id.encode(), user_name=user.id, user_display_name=user.name,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=_unb64(p.credential_id)) for p in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.PREFERRED,
                                                               user_verification=UserVerificationRequirement.REQUIRED))
    _challenges[f"reg:{user.id}"] = (opts.challenge, time.time() + 300)
    return json.loads(options_to_json(opts))


def register(db: Session, user: User, credential: dict) -> dict:
    v = verify_registration_response(credential=credential, expected_challenge=_take(f"reg:{user.id}"),
                                     expected_origin=ORIGIN, expected_rp_id=RP_ID, require_user_verification=True)
    db.add(Passkey(credential_id=_b64(v.credential_id), user_id=user.id, public_key=_b64(v.credential_public_key),
                   sign_count=v.sign_count))
    return {"ok": True, "message": "Passkey saved. Next time we need to check it's you, use your fingerprint, face or device PIN."}


def has_passkey(db: Session, user_id: str) -> bool:
    return db.scalar(select(Passkey).where(Passkey.user_id == user_id).limit(1)) is not None


def auth_options(db: Session, user: User, approval_token: str) -> dict:
    keys = db.scalars(select(Passkey).where(Passkey.user_id == user.id)).all()
    if not keys:
        raise ValueError("no passkey set up")
    opts = generate_authentication_options(rp_id=RP_ID, user_verification=UserVerificationRequirement.REQUIRED,
                                           allow_credentials=[PublicKeyCredentialDescriptor(id=_unb64(k.credential_id)) for k in keys])
    _challenges[f"auth:{user.id}:{approval_token}"] = (opts.challenge, time.time() + 300)
    return json.loads(options_to_json(opts))


def verify_for_approval(db: Session, user: User, approval_token: str, credential: dict) -> dict:
    ap = db.get(Approval, approval_token)
    if not ap or ap.user_id != user.id:
        raise ValueError("no matching approval")
    key = db.get(Passkey, credential.get("id") or credential.get("rawId"))
    if not key or key.user_id != user.id:
        raise ValueError("unknown passkey")
    v = verify_authentication_response(credential=credential, expected_challenge=_take(f"auth:{user.id}:{approval_token}"),
                                       expected_origin=ORIGIN, expected_rp_id=RP_ID,
                                       credential_public_key=_unb64(key.public_key),
                                       credential_current_sign_count=key.sign_count, require_user_verification=True)
    key.sign_count = v.new_sign_count
    ap.step_up_passed = True
    return {"ok": True}
