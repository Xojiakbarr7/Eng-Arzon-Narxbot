import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import User


def validate_init_data(raw: str, token: str, ttl: int = 3600):
    if len(raw) > 12000 or not token:
        raise ValueError("Telegram autentifikatsiyasi mavjud emas")
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=50)
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("Takroriy Telegram maydonlari")
    data = dict(pairs)
    supplied = data.pop("hash", "")
    check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise ValueError("Telegram imzosi noto‘g‘ri")
    age = time.time() - int(data.get("auth_date", "0"))
    if age > ttl or age < -30:
        raise ValueError("Telegram sessiyasi eskirgan")
    user = json.loads(data["user"])
    if not isinstance(user, dict) or type(user.get("id")) is not int or not 0 < user["id"] < 2**63:
        raise ValueError("Telegram foydalanuvchisi noto‘g‘ri")
    return user


def require_internal(x_bot_token: str = Header(default="")):
    configured = get_settings().bot_internal_token
    if not configured or not hmac.compare_digest(configured.encode(), x_bot_token.encode()):
        raise HTTPException(401, "Bot avtorizatsiyasi talab qilinadi")


def current_user(
    db: Session = Depends(get_db),
    x_telegram_init_data: str = Header(default=""),
    x_bot_token: str = Header(default=""),
    x_telegram_user_id: str = Header(default=""),
):
    settings = get_settings()
    if x_telegram_init_data:
        try:
            info = validate_init_data(x_telegram_init_data, settings.bot_token, settings.init_data_ttl_seconds)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise HTTPException(401, "Telegram sessiyasi yaroqsiz yoki eskirgan")
        tid, name = str(info["id"]), str(info.get("first_name", "Foydalanuvchi"))[:160]
    elif x_bot_token or x_telegram_user_id:
        require_internal(x_bot_token)
        if not x_telegram_user_id.isascii() or not x_telegram_user_id.isdecimal() or len(x_telegram_user_id) > 20 or int(x_telegram_user_id) <= 0:
            raise HTTPException(401, "Telegram foydalanuvchi ID noto‘g‘ri")
        tid, name = x_telegram_user_id, "Telegram foydalanuvchi"
    elif settings.demo_mode:
        tid, name = "demo", "Demo foydalanuvchi"
    else:
        raise HTTPException(401, "Ilovani Telegram orqali oching")
    user = db.scalar(select(User).where(User.telegram_id == tid))
    if user is None:
        user = User(telegram_id=tid, first_name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def admin_ids():
    return {int(value.strip()) for value in get_settings().admin_telegram_ids.split(",")
            if value.strip().isascii() and value.strip().isdigit() and int(value.strip()) > 0}


def is_admin_user(user_id: int) -> bool:
    return bool(admin_ids()) and user_id in admin_ids()


def require_admin(
    authorization: str = Header(default=""),
    x_telegram_init_data: str = Header(default=""),
    x_bot_token: str = Header(default=""),
    x_telegram_user_id: str = Header(default=""),
):
    configured = get_settings().admin_token
    supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    if configured and supplied and hmac.compare_digest(configured.encode(), supplied.encode()):
        return True
    if x_telegram_init_data:
        try:
            user = validate_init_data(x_telegram_init_data, get_settings().bot_token, get_settings().init_data_ttl_seconds)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise HTTPException(401, "Telegram sessiyasi yaroqsiz")
        if is_admin_user(user["id"]):
            return True
    if x_bot_token or x_telegram_user_id:
        require_internal(x_bot_token)
        if x_telegram_user_id.isascii() and x_telegram_user_id.isdecimal() and is_admin_user(int(x_telegram_user_id)):
            return True
    raise HTTPException(403, "Admin huquqi talab qilinadi")
