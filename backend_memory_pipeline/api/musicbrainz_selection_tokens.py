from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

class SelectionTokenError(ValueError):
    pass

def _secret() -> bytes:
    value=os.getenv("API_AUTH_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("API_AUTH_SECRET must contain at least 32 characters.")
    return value.encode("utf-8")

def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))

def create_selection_token(payload: dict[str, Any], ttl_seconds: int = 900) -> str:
    claims={**payload, "exp": int(time.time()) + ttl_seconds}
    body=_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature=_encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"

def verify_selection_token(token: str) -> dict[str, Any]:
    try:
        body, supplied=token.split(".", 1)
        expected=_encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise SelectionTokenError("Invalid MusicBrainz selection token.")
        claims=json.loads(_decode(body))
    except SelectionTokenError:
        raise
    except Exception as exc:
        raise SelectionTokenError("Invalid MusicBrainz selection token.") from exc
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), int) or claims["exp"] < int(time.time()):
        raise SelectionTokenError("This MusicBrainz selection has expired. Please repeat your message.")
    return claims
