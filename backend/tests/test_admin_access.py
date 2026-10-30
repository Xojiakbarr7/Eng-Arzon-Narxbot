"""Admin access needs either bearer token or a verified, allowlisted Telegram identity."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from app.config import get_settings
from app.security import is_admin_user, require_admin


def signed_telegram(user_id: int, token: str) -> str:
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": user_id})}
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    checked = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    fields["hash"] = hmac.new(secret, checked.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_admin_authorization(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "admin_telegram_ids", "123, 456")
    monkeypatch.setattr(s, "admin_token", "a-secret-token-with-32-characters")
    monkeypatch.setattr(s, "bot_token", "unit-test-telegram-token")
    monkeypatch.setattr(s, "bot_internal_token", "another-long-internal-token")
    assert is_admin_user(123)
    assert not is_admin_user(124)
    blank = dict(authorization="", x_telegram_init_data="", x_bot_token="", x_telegram_user_id="")
    assert require_admin(**{**blank, "authorization": "Bearer a-secret-token-with-32-characters"})
    assert require_admin(**{**blank, "x_telegram_init_data": signed_telegram(123, s.bot_token)})
    assert require_admin(**{**blank, "x_bot_token": s.bot_internal_token, "x_telegram_user_id": "123"})
    for headers in (
        {},
        {"x_telegram_init_data": signed_telegram(124, s.bot_token)},
        {"x_bot_token": s.bot_internal_token, "x_telegram_user_id": "124"},
        {"authorization": "Bearer wrong-token"},
    ):
        with pytest.raises(HTTPException):
            require_admin(**{**blank, **headers})
