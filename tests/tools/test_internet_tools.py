import json

import pytest

from bilge.core.language import AssistantLanguage
from bilge.tools import web_fetch
from bilge.tools.base import ToolError
from bilge.tools.builtin import internet

TR, EN = AssistantLanguage.TURKISH, AssistantLanguage.ENGLISH


def fake_web(monkeypatch, pages):
    def get(url, language=TR, max_bytes=0):
        for prefix, body in pages.items():
            if url.startswith(prefix):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                return web_fetch.Response(url, 200, "application/json", data)
        raise web_fetch.WebFetchError("offline")

    monkeypatch.setattr(web_fetch, "get", get)


def test_weather_ignores_a_city_nobody_said():
    tool = internet.weather(TR, lambda: "İzmir")
    assert tool.refine({"city": "Ankara"}, "bugün hava nasıl")["city"] is None
    assert tool.refine({"city": "Ankara"}, "Ankara'da hava nasıl") == {"city": "Ankara"}


def test_weather_reads_the_forecast(monkeypatch):
    fake_web(
        monkeypatch,
        {
            "https://geocoding-api": {"results": [{"name": "İzmir", "latitude": 38.4, "longitude": 27.1}]},
            "https://api.open-meteo.com": {
                "current": {"temperature_2m": 21.4, "weather_code": 0},
                "daily": {
                    "time": ["a", "b"],
                    "weather_code": [0, 61],
                    "temperature_2m_max": [24, 19],
                    "temperature_2m_min": [15, 12],
                    "precipitation_probability_max": [0, 80],
                },
            },
        },
    )
    tool = internet.weather(TR, lambda: "İzmir")
    assert "İzmir'de" in tool.run({})
    tomorrow = tool.run({"day_offset": 1})
    assert "yarın" in tomorrow and "80" in tomorrow


def test_weather_without_a_connection_is_a_spoken_error(monkeypatch):
    fake_web(monkeypatch, {})
    with pytest.raises(ToolError, match="Hava durumu alınamadı"):
        internet.weather(TR, lambda: "İzmir").run({})


def test_english_exchange_defaults_to_the_dollar():
    tool = internet.exchange_rate(EN)
    assert tool.refine({"from": "EUR", "to": "TRY"}, "how much is the euro")["to"] == "USD"
    assert tool.refine({"from": "USD", "to": "TRY"}, "how much is the dollar")["to"] == "EUR"
    assert tool.refine({"from": "EUR", "to": "TRY"}, "euro in lira")["to"] == "TRY"


def test_exchange_rate_sentence(monkeypatch):
    fake_web(monkeypatch, {"https://api.frankfurter.app": {"rates": {"TRY": 4123.456}}})
    assert internet.exchange_rate(TR).run({"from": "USD", "amount": 100}) == "100 dolar 4.123,46 lira."


def test_news_reads_headlines(monkeypatch):
    rss = b"<rss><channel><item><title>Birinci</title></item><item><title>Ikinci.</title></item></channel></rss>"
    fake_web(monkeypatch, {"https://www.aa.com.tr": rss})
    assert internet.news(TR).run({}) == "Anadolu Ajansı'ndan son başlıklar. Birinci. Ikinci."


def test_web_page_is_untrusted():
    assert internet.read_web_page(TR).untrusted_output
    assert internet.news(TR).untrusted_output


@pytest.mark.parametrize(
    ("value", "expected"), [(1, 1), (1.0, 1), ("1", 1), (True, None), ("yarın", None), (1.5, None)]
)
def test_day_offsets_from_models_are_read_carefully(value, expected):
    assert internet._whole_number(value) == expected


@pytest.mark.parametrize("value", ["abc", "nan", "inf", -5, True])
def test_unreadable_amounts_are_spoken_errors(value):
    with pytest.raises(ToolError, match="Miktarı"):
        internet.exchange_rate(TR).run({"from": "USD", "amount": value})


def test_amount_with_a_decimal_comma(monkeypatch):
    fake_web(monkeypatch, {"https://api.frankfurter.app": {"rates": {"TRY": 61.8}}})
    assert internet.exchange_rate(TR).run({"from": "USD", "amount": "1,5"}) == "1,5 dolar 61,8 lira."


def test_cautioned_questions_are_spoken_sentences():
    assert (
        internet.read_web_page(TR).generic_question({"address": "example.com"})
        == "example.com adresindeki sayfayı açıp okuyayım mı?"
    )
    assert internet.read_web_page(EN).generic_question({"address": "bbc.com"}) == "Shall I open and read bbc.com?"
