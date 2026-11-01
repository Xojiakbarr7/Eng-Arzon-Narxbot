import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from bot import main as bot_main
from bot.main import Api, ApiError, money, miniapp, watch, unwatch, show_products, barcode_command, catalog, basket, basket_input, parse_basket_items, current_miniapp_url


def test_unavailable_offer_is_not_zero_price():
    assert money(None) == "Yangilangan taklif yo‘q"
    assert money(0) == "0 so‘m"
    assert money(1_250_000) == "1 250 000 so‘m"


def test_miniapp_requires_https_and_preserves_query(monkeypatch, tmp_path):
    monkeypatch.setattr(bot_main, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("MINI_APP_URL", "http://localhost:5173")
    assert miniapp() is None
    monkeypatch.setenv("MINI_APP_URL", "https://example.com/?lang=uz")
    link = miniapp("basket").inline_keyboard[0][0].web_app.url
    assert link == "https://example.com/?lang=uz&view=basket"


def test_api_auth_is_server_only_and_error_is_readable():
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(401, json={"detail": "Token yaroqsiz"})
    async def run():
        async with httpx.AsyncClient(base_url="https://backend.local", transport=httpx.MockTransport(handle)) as client:
            api = Api(client, "internal-secret")
            with pytest.raises(ApiError, match="Token yaroqsiz"):
                await api.call("GET", "/api/profile", 1234)
    asyncio.run(run())
    assert seen[0].headers["X-Bot-Token"] == "internal-secret"
    assert seen[0].headers["X-Telegram-User-Id"] == "1234"
    assert "secret" not in str(seen[0].url)


def test_watch_validation_does_not_create_alert():
    message = SimpleNamespace(text="/watch 1 -100", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api, state = SimpleNamespace(call=AsyncMock()), SimpleNamespace(clear=AsyncMock())
    asyncio.run(watch(message, state, api))
    api.call.assert_not_called()
    assert "Format" in message.answer.call_args.args[0]


def test_watch_creates_target_for_telegram_user():
    message = SimpleNamespace(text="/watch 1 3000000", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api, state = SimpleNamespace(call=AsyncMock()), SimpleNamespace(clear=AsyncMock())
    asyncio.run(watch(message, state, api))
    api.call.assert_awaited_once_with("POST", "/api/alerts", 7, json={"product_id": 1, "target_price": 3000000})


def test_unwatch_is_scoped_to_telegram_user():
    message = SimpleNamespace(text="/unwatch 9", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api, state = SimpleNamespace(call=AsyncMock()), SimpleNamespace(clear=AsyncMock())
    asyncio.run(unwatch(message, state, api))
    api.call.assert_awaited_once_with("DELETE", "/api/alerts/9", 7)


def test_product_text_escapes_html_and_marks_demo():
    message = SimpleNamespace(answer=AsyncMock())
    product = {"id": 1, "name": "<b>Injection</b>", "min_price": None, "store_count": 0, "is_demo": True}
    asyncio.run(show_products(message, [product]))
    text = message.answer.call_args.args[0]
    assert "&lt;b&gt;Injection&lt;/b&gt;" in text
    assert "Demo" in text and "Yangilangan taklif yo‘q" in text


def test_barcode_input_cannot_change_backend_path():
    message = SimpleNamespace(text="/barcode ../profile", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api, state = SimpleNamespace(call=AsyncMock()), SimpleNamespace(clear=AsyncMock())
    asyncio.run(barcode_command(message, state, api))
    api.call.assert_not_called()
    assert "raqamdan" in message.answer.call_args.args[0]


def test_miniapp_url_reload_does_not_need_bot_restart(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(bot_main, "ENV_FILE", env_file)
    monkeypatch.setenv("MINI_APP_URL", "https://old.example")
    env_file.write_text("MINI_APP_URL=https://first.example\n", encoding="utf-8")
    assert miniapp().inline_keyboard[0][0].web_app.url == "https://first.example?view=catalog"
    env_file.write_text("MINI_APP_URL=https://second.example\n", encoding="utf-8")
    assert current_miniapp_url() == "https://second.example"
    env_file.write_text("MINI_APP_URL=\n", encoding="utf-8")
    assert miniapp() is None


def test_catalog_without_miniapp_shows_real_api_products(monkeypatch):
    monkeypatch.setattr(bot_main, "current_miniapp_url", lambda: "")
    message = SimpleNamespace(text="🛍 Katalog", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    product = {"id": 12, "name": "Phone", "min_price": 100000, "store_count": 2, "is_demo": True}
    api = SimpleNamespace(call=AsyncMock(return_value={"items": [product], "total": 20}))
    state = SimpleNamespace(clear=AsyncMock())
    asyncio.run(catalog(message, state, api))
    api.call.assert_awaited_once_with("GET", "/api/products", 7, params={"page": 1, "page_size": 6, "sort": "price_asc"})
    texts = [call.args[0] for call in message.answer.call_args_list]
    assert any("Phone" in text and "Demo" in text for text in texts)
    assert any("/catalog 2" in text for text in texts)
    assert not any("administrator" in text for text in texts)


def test_catalog_page_validation_never_calls_api(monkeypatch):
    monkeypatch.setattr(bot_main, "current_miniapp_url", lambda: "")
    message = SimpleNamespace(text="/catalog ../profile", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api, state = SimpleNamespace(call=AsyncMock()), SimpleNamespace(clear=AsyncMock())
    asyncio.run(catalog(message, state, api))
    api.call.assert_not_called()


@pytest.mark.parametrize("text", ["", "../profile", "-1", "1x0", "1x21", "1x20,1", "1,2,3,4,5,6,7,8,9", "1.5", "١"])
def test_basket_rejects_invalid_ids_and_quantities(text):
    with pytest.raises(ValueError):
        parse_basket_items(text)


def test_basket_merges_duplicate_ids_and_understands_quantity():
    assert parse_basket_items("1x2, 3, 1") == [{"product_id": 1, "quantity": 3}, {"product_id": 3, "quantity": 1}]


def test_text_basket_uses_profile_region_and_real_optimizer():
    message = SimpleNamespace(text="/basket 1x2,3", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    result = {
        "is_demo": True,
        "stores": [{"store_id": 2, "store_name": "Store <B>", "delivery_fee": 15000, "total": 315000}],
        "items": [{"store_id": 2, "name": "Phone <A>", "quantity": 2, "subtotal": 200000}, {"store_id": 2, "name": "Book", "quantity": 1, "subtotal": 100000}],
        "total": 315000, "single_store_total": 315000, "savings": 0,
    }
    api = SimpleNamespace(call=AsyncMock(side_effect=[{"region": "andijan"}, result]))
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    asyncio.run(basket(message, state, api))
    assert api.call.await_args_list[0].args == ("GET", "/api/profile", 7)
    assert api.call.await_args_list[1].args == ("POST", "/api/basket/optimize", 7)
    assert api.call.await_args_list[1].kwargs["json"] == {"items": [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 1}], "region": "andijan"}
    text = message.answer.call_args.args[0]
    assert "315 000 so‘m" in text and "Demo" in text
    assert "Store &lt;B&gt;" in text and "Phone &lt;A&gt;" in text


def test_basket_menu_asks_for_ids_when_miniapp_missing(monkeypatch):
    monkeypatch.setattr(bot_main, "current_miniapp_url", lambda: "")
    message = SimpleNamespace(text="🧺 Eng arzon savatcha", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api = SimpleNamespace(call=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    asyncio.run(basket(message, state, api))
    api.call.assert_not_called()
    assert "1,2,3,4,5" in message.answer.call_args.args[0]
    state.set_state.assert_awaited_once_with(bot_main.Flow.basket)


def test_invalid_basket_state_keeps_retry_and_does_not_call_api():
    message = SimpleNamespace(text="1x99", answer=AsyncMock(), from_user=SimpleNamespace(id=7))
    api = SimpleNamespace(call=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    asyncio.run(basket_input(message, state, api))
    api.call.assert_not_called()
    state.clear.assert_not_called()
    state.set_state.assert_awaited_once_with(bot_main.Flow.basket)

def test_unfinished_features_are_hidden_from_telegram_keyboard():
    from bot.main import MENU, keyboard
    labels = [label for row in MENU for label in row]
    assert "🤖 AI xarid yordamchisi" in labels
    assert not any(label in labels for label in (
        "📸 Rasm bilan qidirish",
        "⚖️ AI bilan solishtirish",
        "⚖️ Mahsulot solishtirish",
        "📷 Shtrix-kod",
    ))
    assert [button.text for row in keyboard.keyboard for button in row] == labels
