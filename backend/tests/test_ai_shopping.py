"""AI shopping questions never replace verified database prices with model guesses."""
import asyncio
from datetime import datetime, timezone

import httpx

from app.ai_shopping import (
    fallback_answer, parse_budget, parse_response_text, search_terms,
    ai_explanation,
)
from app.config import get_settings


def test_budget_parser_and_search_terms():
    assert parse_budget("3.5 milliongacha telefon") == 3_500_000
    assert parse_budget("3,5 mln gacha Redmi") == 3_500_000
    assert parse_budget("500 minggacha kitob") == 500_000
    assert parse_budget("2 500 000 so‘mga telefon") == 2_500_000
    assert parse_budget("byudjet yo'q") is None
    aliases, brands, terms = search_terms("Samsung va Redmi telefonlarini solishtir")
    assert len(brands) == 2 and "samsung" in brands and "redmi" in brands
    assert "smartfon" in aliases
    assert all(t not in ("va", "solishtir") for t in terms)
    a2, _, t2 = search_terms("3 million so‘mgacha eng arzon telefonni topib ber")
    assert "smartfon" in a2 and not t2
    a3, _, t3 = search_terms("Eng arzon noutbukni ko‘rsat")
    assert "laptop" in a3 and not t3


def test_fallback_price_is_real_observed_number():
    rows = [
        {"product_id": 3, "name": "Telefon B", "price": 2_000_000, "store": "Olcha", "url": "https://olcha.uz/x"},
        {"product_id": 4, "name": "Telefon A", "price": 1_800_000, "store": "IDEA", "url": "https://idea.uz/x"},
    ]
    answer = fallback_answer(rows, "Qaysi telefon arzon, solishtir", 3_000_000)
    assert "Telefon A" in answer and "1 800 000" in answer and "IDEA" in answer
    assert "Pastdagi" in answer
    assert fallback_answer([], "telefon", None).startswith("Hozirgi")


def test_openai_response_parser_ignores_non_text():
    assert parse_response_text({"output": [{"type": "reasoning"}, {"type": "message", "content": [
        {"type": "output_text", "text": "Katalog bilan taqqoslash mumkin."},
        {"type": "refusal", "refusal": "unused"},
    ]}]}) == "Katalog bilan taqqoslash mumkin."
    assert parse_response_text({"output": []}) == ""


def test_api_is_opt_in_and_no_ai_call_without_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert asyncio.run(ai_explanation("telefon", [
        {"name": "Telefon A", "price": 100000, "store": "Olcha"}
    ])) is None


def test_optional_openai_uses_catalogue_context_but_never_returns_generated_prices(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "fake-provider-key")
    monkeypatch.setattr(settings, "ai_model", "gpt-6-luna")
    captured = []
    response_text = ["Bu takliflarni katalog asosida taqqoslab ko‘ring. Do‘konda yakuniy narxni tekshiring."]

    def reply(request):
        captured.append(request)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers.get("authorization") == "Bearer fake-provider-key"
        body = __import__("json").loads(request.content)
        assert body["store"] is False
        assert body["model"] == "gpt-6-luna"
        assert "150000" in body["input"]
        return httpx.Response(200, json={"output": [{"type": "message", "content": [
            {"type": "output_text", "text": response_text[0]}
        ]}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.ai_shopping.httpx.AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(reply), **kwargs))
    rows = [{"name": "Real catalog telefon", "price": 150000, "store": "Olcha"}]
    answer = asyncio.run(ai_explanation("eng arzon telefon qaysi", rows))
    assert "Bu takliflarni" in answer
    response_text[0] = "Narxi 999 so‘m"  # model-invented values are rejected
    assert asyncio.run(ai_explanation("eng arzon telefon qaysi", rows)) is None
    assert len(captured) == 2



def test_gemini_parser_extracts_only_candidate_text():
    from app.ai_shopping import parse_gemini_text
    assert parse_gemini_text({"candidates":[{"content":{"role":"model","parts":[
        {"text":"Bularning narxlari katalogda ko‘rsatilgan."},
        {"inlineData":{"mimeType":"text/plain","data":"ignored"}}
    ]}}]}) == "Bularning narxlari katalogda ko‘rsatilgan."
    assert parse_gemini_text({"candidates":[]}) == ""
    assert parse_gemini_text({"error":{"message":"quota exhausted"}}) == ""


def test_gemini_requires_explicit_key_and_opt_in(monkeypatch):
    from app.ai_shopping import configured_ai_provider
    cfg = get_settings()
    monkeypatch.setattr(cfg, "ai_provider", "gemini")
    monkeypatch.setattr(cfg, "gemini_api_key", "")
    monkeypatch.setattr(cfg, "ai_enabled", True)
    assert configured_ai_provider() is None
    assert asyncio.run(ai_explanation("telefon", [{
        "name": "Telefon A", "price": 100000, "store": "Olcha"
    }])) is None
    monkeypatch.setattr(cfg, "gemini_api_key", "fake-key")
    assert configured_ai_provider() == "gemini"
    monkeypatch.setattr(cfg, "ai_enabled", False)
    assert configured_ai_provider() is None


def test_gemini_rest_sends_only_catalog_data_and_never_generates_prices(monkeypatch):
    from app.ai_shopping import configured_ai_provider
    cfg = get_settings()
    monkeypatch.setattr(cfg, "ai_enabled", True)
    monkeypatch.setattr(cfg, "ai_provider", "gemini")
    monkeypatch.setattr(cfg, "gemini_api_key", "test-gemini-auth-key")
    monkeypatch.setattr(cfg, "gemini_model", "gemini-2.5-flash-lite")
    assert configured_ai_provider() == "gemini"
    calls = []
    returned = ["Variantlarni katalogdagi narxlari bo‘yicha solishtiring. Xarid oldidan do‘konda tekshiring."]

    def reply(request):
        calls.append(request)
        assert request.method == "POST"
        assert str(request.url) == (
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
        )
        assert request.headers.get("x-goog-api-key") == "test-gemini-auth-key"
        assert "test-gemini-auth-key" not in str(request.url)
        data = __import__("json").loads(request.content)
        assert "catalogue_candidates" in data["contents"][0]["parts"][0]["text"]
        assert "150000" in data["contents"][0]["parts"][0]["text"]
        assert "faqat" in data["systemInstruction"]["parts"][0]["text"].lower()
        assert not data.get("tools")
        return httpx.Response(200, json={"candidates":[{"content":{"role":"model","parts":[{"text":returned[0]}]}}]})

    original = httpx.AsyncClient
    monkeypatch.setattr("app.ai_shopping.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(reply), **kwargs))
    rows = [{"name": "Smartfon A", "price": 150000, "store": "Olcha"}]
    answer = asyncio.run(ai_explanation("eng arzon telefon", rows))
    assert "Variantlarni katalogdagi" in answer
    returned[0] = "Narxi 987 000 so‘m"  # Invented Gemini price cannot escape SQL.
    assert asyncio.run(ai_explanation("eng arzon telefon", rows)) is None
    assert len(calls) == 2


def test_gemini_quota_or_denial_falls_back_to_catalogue(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "ai_enabled", True)
    monkeypatch.setattr(cfg, "ai_provider", "gemini")
    monkeypatch.setattr(cfg, "gemini_api_key", "test-gemini-auth-key")
    calls = []
    def reply(request):
        calls.append(1)
        return httpx.Response(429, json={"error":{"message":"rate limit"}})
    original = httpx.AsyncClient
    monkeypatch.setattr("app.ai_shopping.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(reply), **kwargs))
    assert asyncio.run(ai_explanation("telefon", [{
        "name":"Real smartfon", "price":150000, "store":"Olcha"
    }])) is None
    assert calls == [1]


def test_gemini_rejects_unknown_models_without_dialing_custom_hosts(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "ai_enabled", True)
    monkeypatch.setattr(cfg, "ai_provider", "gemini")
    monkeypatch.setattr(cfg, "gemini_api_key", "test-gemini-auth-key")
    monkeypatch.setattr(cfg, "gemini_model", "https://evil.example/steal")
    called = []
    def reply(request):
        called.append(str(request.url))
        return httpx.Response(200, json={"candidates":[]})
    original = httpx.AsyncClient
    monkeypatch.setattr("app.ai_shopping.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(reply), **kwargs))
    assert asyncio.run(ai_explanation("telefon", [{
        "name":"Real smartfon", "price":150000, "store":"Olcha"
    }])) is None
    assert called == ["https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"]
