"""The former experimental controls must not appear on live Telegram keyboards."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.telegram_bot import MENU, keyboard, outdated_menu_button


def test_deprecated_buttons_are_hidden():
    buttons = [label for row in MENU for label in row]
    assert "🤖 AI xarid yordamchisi" in buttons
    assert not {"📸 Rasm bilan qidirish", "⚖️ AI bilan solishtirish",
                "⚖️ Mahsulot solishtirish", "📷 Shtrix-kod"} & set(buttons)


def test_old_keyboard_button_refreshes_menu():
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())
    asyncio.run(outdated_menu_button(message, state))
    state.clear.assert_awaited_once()
    assert message.answer.call_args.kwargs["reply_markup"] is keyboard
