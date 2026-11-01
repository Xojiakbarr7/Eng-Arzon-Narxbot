"""Regression tests for simultaneous first-use requests from Telegram Mini App."""
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import User
from app.security import current_user


def _unique_conflict():
    return IntegrityError(
        "INSERT INTO users (telegram_id) VALUES (:telegram_id)",
        {"telegram_id": "7001"},
        Exception("UNIQUE constraint failed: users.telegram_id"),
    )


def test_first_login_race_recovers_existing_user(monkeypatch):
    monkeypatch.setattr(get_settings(), "bot_internal_token", "test-internal-token")
    existing = User(id=24, telegram_id="7001", first_name="Existing")
    db = Mock()
    db.scalar.side_effect = [None, existing]
    db.commit.side_effect = _unique_conflict()

    result = current_user(
        db=db, x_telegram_init_data="", x_bot_token="test-internal-token",
        x_telegram_user_id="7001",
    )

    assert result is existing
    db.rollback.assert_called_once_with()
    assert db.scalar.call_count == 2
    db.refresh.assert_not_called()


def test_unrelated_integrity_failure_still_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "bot_internal_token", "test-internal-token")
    db = Mock()
    db.scalar.side_effect = [None, None]
    db.commit.side_effect = _unique_conflict()

    with pytest.raises(IntegrityError):
        current_user(
            db=db, x_telegram_init_data="", x_bot_token="test-internal-token",
            x_telegram_user_id="7001",
        )

    db.rollback.assert_called_once_with()
