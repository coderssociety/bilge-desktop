"""Data from the internet: weather (Open-Meteo), exchange rates (European Central Bank via Frankfurter), news
headlines (Anadolu Ajansı / BBC) and reading a web page. None of these need an account or a key."""

import json
import logging
import math
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from bilge.brain.instructions import weekday_name
from bilge.core import text
from bilge.core.language import AssistantLanguage
from bilge.core.web import html_text, news_request, rss_headlines, weather_report
from bilge.core.web import news_article as article_reference
from bilge.tools import web_fetch
from bilge.tools.base import Tool, ToolError

log = logging.getLogger(__name__)
EN, TR = AssistantLanguage.ENGLISH, AssistantLanguage.TURKISH
HEADLINE_COUNT = 5
# Enough of the feed to go on with after the first few.
FEED_COUNT = 30
# Enough for a long article; the model only sees the start of a longer page.
PAGE_CHARACTERS = 12_000


def _json(url: str, language: AssistantLanguage) -> Any:
    response = web_fetch.get(url, language)
    if response.status != 200:
        raise web_fetch.WebFetchError(f"HTTP {response.status}")
    try:
        return json.loads(response.body)
    except ValueError as error:
        raise web_fetch.WebFetchError("Unexpected answer") from error


def weather(language: AssistantLanguage, default_city: Callable[[], str]) -> Tool:
    english = language is EN

    def refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        # A local model once filled in "Ankara" for "Bugün hava nasıl"; a city counts only if it was said.
        city = str(arguments.get("city") or "").strip()
        if not city:
            return arguments
        stem = text.folded(city)[: max(3, len(city) - 1)]
        said = any(word.startswith(stem) for word in text.folded(command).split())
        return arguments if said else {**arguments, "city": None}

    def run(arguments: dict[str, Any]) -> str:
        city = str(arguments.get("city") or "").strip() or default_city()
        day = _whole_number(arguments.get("day_offset"))
        try:
            places = _json(
                "https://geocoding-api.open-meteo.com/v1/search?"
                + urlencode({"name": city, "count": 1, "language": language.code}),
                language,
            )
            place = (places.get("results") or [None])[0]
            if not place:
                raise ToolError(
                    f"Couldn't find a place called '{city}'." if english else f"'{city}' diye bir yer bulamadım."
                )
            forecast = _json(
                "https://api.open-meteo.com/v1/forecast?"
                + urlencode(
                    {
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": "temperature_2m,weather_code",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "timezone": "auto",
                        "forecast_days": 7,
                    }
                ),
                language,
            )
        except web_fetch.WebFetchError as error:
            raise ToolError(
                ("Couldn't get the weather. " if english else "Hava durumu alınamadı. ") + str(error)
            ) from error
        daily = forecast["daily"]
        if not isinstance(day, int) or not 0 <= day < len(daily["time"]):
            current = forecast["current"]
            return weather_report.current(place["name"], current["temperature_2m"], current["weather_code"], language)
        return weather_report.daily(
            place["name"],
            _day_name(day, language),
            daily["temperature_2m_min"][day],
            daily["temperature_2m_max"][day],
            daily["weather_code"][day],
            daily["precipitation_probability_max"][day],
            language,
        )

    return Tool(
        "weather",
        "Weather for a city: now, today, tomorrow or the coming days."
        if english
        else "Bir şehrin hava durumunu söyler: şu an, bugün, yarın ya da önümüzdeki günler.",
        run=run,
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name only; leave empty if none was said"
                    if english
                    else "Şehir adı, eksiz: 'Ankara'da' → 'Ankara'; söylenmediyse boş bırak",
                },
                "day_offset": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 6,
                    "description": "Days from today: today 0, tomorrow 1; leave empty for right now"
                    if english
                    else "Kaç gün sonrası: bugün 0, yarın 1; 'şu an' ya da gün söylenmediyse boş bırak",
                },
            },
        },
        refine=refine,
    )


def _day_name(offset: int, language: AssistantLanguage) -> str:
    if offset == 0:
        return "today" if language is EN else "bugün"
    if offset == 1:
        return "tomorrow" if language is EN else "yarın"
    weekday = weekday_name(datetime.now() + timedelta(days=offset), language)
    return f"on {weekday}" if language is EN else text.lowercased(weekday)


CURRENCIES = {
    "TRY": ("lira", "lira"), "USD": ("dolar", "dollar"), "EUR": ("euro", "euro"), "GBP": ("sterlin", "pound"),
    "CHF": ("İsviçre frangı", "Swiss franc"), "JPY": ("yen", "yen"), "CNY": ("yuan", "yuan"),
    "CAD": ("Kanada doları", "Canadian dollar"), "AUD": ("Avustralya doları", "Australian dollar"),
    "SEK": ("İsveç kronu", "Swedish krona"), "NOK": ("Norveç kronu", "Norwegian krone"), "DKK": ("Danimarka kronu", "Danish krone"),
}  # fmt: skip


def exchange_rate(language: AssistantLanguage) -> Tool:
    english = language is EN

    def name(code: str) -> str:
        return CURRENCIES[code][1 if english else 0]

    def refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        # An unsaid target means lira to a Turkish speaker; in English the dollar (or the euro for dollars) is meant.
        if not english or arguments.get("to") not in (None, "TRY"):
            return arguments
        words = text.folded(command).split()
        if any(w in words for w in ("lira", "try", "tl", "turkish")):
            return arguments
        return {**arguments, "to": "EUR" if arguments.get("from") == "USD" else "USD"}

    def run(arguments: dict[str, Any]) -> str:
        source, target = arguments.get("from"), arguments.get("to") or ("USD" if english else "TRY")
        if source not in CURRENCIES or target not in CURRENCIES or source == target:
            raise ToolError(
                "I couldn't tell which currencies to convert."
                if english
                else "Hangi para birimini çevireceğimi anlayamadım."
            )
        amount = _amount(arguments.get("amount"))
        if amount is None:
            raise ToolError("I didn't get the amount." if english else "Miktarı anlayamadım.")
        try:
            data = _json(
                "https://api.frankfurter.app/latest?" + urlencode({"from": source, "to": target, "amount": amount}),
                language,
            )
        except web_fetch.WebFetchError as error:
            raise ToolError(
                ("Couldn't get the exchange rate. " if english else "Döviz kuru alınamadı. ") + str(error)
            ) from error
        value = (data.get("rates") or {}).get(target)
        if value is None:
            raise ToolError("That rate isn't available." if english else "Bu kur bulunamadı.")
        return f"{_number(amount, language)} {name(source)} {_number(value, language)} {name(target)}."

    codes = sorted(CURRENCIES)
    return Tool(
        "exchangeRate",
        "Exchange rates and currency conversion: 'how much is the dollar in lira', '100 euros in dollars' (ECB rates)."
        if english
        else "Döviz kurunu ve para çevirisini söyler: 'dolar kaç lira', '100 euro kaç TL' (Avrupa Merkez Bankası kurları).",
        run=run,
        parameters={
            "type": "object",
            "properties": {
                "from": {"type": "string", "enum": codes},
                "to": {
                    "type": "string",
                    "enum": codes,
                    "description": "Target; leave empty if not said"
                    if english
                    else "Hedef para birimi; söylenmediyse TRY",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount; leave empty if not said" if english else "Miktar; söylenmediyse boş bırak",
                },
            },
            "required": ["from"],
        },
        refine=refine,
    )


def _whole_number(value: Any) -> int | None:
    """Models send numbers as 1, 1.0 or "1"; anything else (including true/false) means not given."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number == int(number) else None


def _amount(value: Any) -> float | None:
    if value is None or value == "":
        return 1.0
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _number(value: float, language: AssistantLanguage) -> str:
    """Up to two decimals, Turkish separators in Turkish: 1.234,5 / 1,234.5."""
    formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
    if language is TR:
        formatted = formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return formatted


NEWS_FEEDS = {
    TR: {c: f"https://www.aa.com.tr/tr/rss/default?cat={slug}" for c, slug in
         {"general": "guncel", "economy": "ekonomi", "sports": "spor", "world": "dunya", "technology": "bilim-teknoloji"}.items()},
    EN: {c: f"https://feeds.bbci.co.uk/{path}" for c, path in
         {"general": "news/rss.xml", "economy": "news/business/rss.xml", "sports": "sport/rss.xml",
          "world": "news/world/rss.xml", "technology": "news/technology/rss.xml"}.items()},
}  # fmt: skip


# As each feed names its topic.
NEWS_TOPIC_NAMES = {
    TR: {"economy": "ekonomi", "sports": "spor", "world": "dünya", "technology": "bilim-teknoloji"},
    EN: {"economy": "business", "sports": "sport", "world": "world", "technology": "technology"},
}


def _news_introduction(kind: news_request.Kind, category: str, language: AssistantLanguage) -> str:
    name = NEWS_TOPIC_NAMES[language].get(category)
    if language is EN:
        if kind is news_request.Kind.NEXT:
            return "The next headlines. "
        if kind is news_request.Kind.AGAIN:
            return "Nothing new since I last read them; the latest are still these. "
        return f"Latest {name} headlines from BBC News. " if name else "Latest headlines from BBC News. "
    if kind is news_request.Kind.NEXT:
        return "Sıradaki başlıklar. "
    if kind is news_request.Kind.AGAIN:
        return "Son okuduğumdan beri yeni başlık yok; en son başlıklar yine şunlar. "
    return f"Anadolu Ajansı'ndan son {name} başlıkları. " if name else "Anadolu Ajansı'ndan son başlıklar. "


class NewsReading:
    """The headlines read out while Bilge runs, shared by the news and the tool that opens one of them."""

    def __init__(self) -> None:
        self._memory = news_request.HeadlineMemory()
        self._lock = threading.Lock()

    def recent_topic(self) -> str | None:
        with self._lock:
            return self._memory.recent_topic(datetime.now())

    def next(self, items: list[rss_headlines.Item], topic: str, count: int) -> news_request.Reading:
        with self._lock:
            return self._memory.next(items, topic, count, datetime.now())

    def article(self, words: str, asked: bool = False) -> article_reference.Request | None:
        with self._lock:
            last, heard = self._memory.heard_items(datetime.now())
        return article_reference.find(words, last, heard, asked=asked)

    def was_read(self, link: str) -> rss_headlines.Item | None:
        with self._lock:
            _, heard = self._memory.heard_items(datetime.now())
        return next((item for item in heard if item.link == link), None)


def news(language: AssistantLanguage, reading: NewsReading | None = None) -> Tool:
    english = language is EN
    reading = reading or NewsReading()

    def refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        """A topic said in the command wins over the model's choice; "bu kadar mı" goes on with the topic just read."""
        named = news_request.topic(command)
        if named is None and news_request.is_continuation(command):
            named = reading.recent_topic()
        return {**arguments, "category": named} if named else arguments

    def run(arguments: dict[str, Any]) -> str:
        category = arguments.get("category") or "general"
        if category not in NEWS_FEEDS[language]:
            category = "general"
        try:
            feed = rss_headlines.items(web_fetch.get(NEWS_FEEDS[language][category], language).body, FEED_COUNT)
        except web_fetch.WebFetchError as error:
            raise ToolError(("Couldn't get the news. " if english else "Haberler alınamadı. ") + str(error)) from error
        if not feed:
            raise ToolError("No headlines found." if english else "Haber başlığı bulunamadı.")
        read = reading.next(feed, category, HEADLINE_COUNT)
        return _news_introduction(read.kind, category, language) + " ".join(
            h if h.endswith(".") else h + "." for h in read.headlines
        )

    return Tool(
        "news",
        "Reads the latest headlines: general, economy, sports, world or technology (BBC News)."
        if english
        else "Son haber başlıklarını okur: gündem, ekonomi, spor, dünya ya da bilim-teknoloji (Anadolu Ajansı).",
        run=run,
        parameters={
            "type": "object",
            "properties": {"category": {"type": "string", "enum": list(NEWS_FEEDS[language])}},
        },
        refine=refine,
        untrusted_output=True,
        spoken_action=lambda _: (
            "Shall I read the latest headlines?" if english else "Son haber başlıklarını okuyayım mı?"
        ),
    )


def news_article(
    language: AssistantLanguage, reading: NewsReading, open_link: Callable[[str], None] | None = None
) -> Tool:
    """ "Claude'un keşfettiği buluşu aç", "üçüncü haberi anlat": one of the headlines just read, fetched for the model
    to tell in short; "aç" also shows it in the browser."""
    english = language is EN

    def refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        # The user's own words first; the model's paraphrase of them when those don't point at a headline.
        found = reading.article(command) or reading.article(str(arguments.get("headline") or ""), asked=True)
        if found is None:
            return {key: value for key, value in arguments.items() if key != "link"}
        return {**arguments, "link": found.item.link, "open": found.in_browser or bool(arguments.get("open"))}

    def run(arguments: dict[str, Any]) -> str:
        item = reading.was_read(str(arguments.get("link") or ""))
        if item is None or item.link is None:
            raise ToolError(
                "I couldn't tell which story to open; could you name one of the headlines I read?"
                if english
                else "Hangi haberi açacağımı bulamadım; okuduğum başlıklardan birini söyler misin?"
            )
        opened = False
        if arguments.get("open") and open_link is not None:
            try:
                open_link(item.link)
                opened = True
            except Exception:  # noqa: BLE001 - without a browser the story is still told
                log.info("Could not open the story in the browser", exc_info=True)
        try:
            response = web_fetch.get(item.link, language)
            if not 200 <= response.status < 300:
                # A paywall, a bot block or a missing page is not the story.
                raise web_fetch.WebFetchError(f"HTTP {response.status}")
        except web_fetch.WebFetchError as error:
            if opened:
                return f"Opened in the browser: {item.title}" if english else f"Haberi tarayıcıda açtım: {item.title}"
            raise ToolError(("Couldn't open the story. " if english else "Haber açılamadı. ") + str(error)) from error
        body = html_text.extract(response.text())[:PAGE_CHARACTERS]
        note = ("(Opened in the browser.)\n" if english else "(Haber tarayıcıda açıldı.)\n") if opened else ""
        return f"{'Story' if english else 'Haber'}: {item.title}\n{note}\n{body}"

    return Tool(
        "newsArticle",
        "Opens one of the headlines just read out by the news tool and reads the story, to tell what it says."
        if english
        else "Haberler aracının az önce okuduğu başlıklardan birini açıp haberin kendisini okur; ne anlattığını söylemek için.",
        run=run,
        parameters={
            "type": "object",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "Which headline, as the user said it: its words or its place ('third', 'last')"
                    if english
                    else "Hangi başlık, kullanıcının dediği gibi: kelimeleri ya da sırası ('üçüncü', 'sonuncu')",
                },
                "open": {
                    "type": "boolean",
                    "description": "Also open it in the browser" if english else "Tarayıcıda da açılsın mı",
                },
            },
            "required": ["headline"],
        },
        refine=refine,
        untrusted_output=True,
        spoken_action=lambda _: "Shall I open that story?" if english else "Bu haberi açıp okuyayım mı?",
    )


def read_web_page(language: AssistantLanguage) -> Tool:
    english = language is EN

    def run(arguments: dict[str, Any]) -> str:
        address = str(arguments.get("address") or "").strip()
        if not address:
            raise ToolError("Which page?" if english else "Hangi sayfa?")
        url = address if "://" in address else f"https://{address}"
        try:
            response = web_fetch.get(url, language)
        except web_fetch.LocalAddressError as error:
            raise ToolError(
                "I don't open addresses on the local network." if english else "Yerel ağdaki adresleri açmıyorum."
            ) from error
        except web_fetch.WebFetchError as error:
            raise ToolError(("Couldn't open the page. " if english else "Sayfa açılamadı. ") + str(error)) from error
        page = response.text()
        title = html_text.title(page)
        body = html_text.extract(page)[:PAGE_CHARACTERS]
        return f"{title}\n\n{body}" if title else body

    return Tool(
        "readWebPage",
        "Downloads and reads a web page at the given address, to summarize it or answer a question about it."
        if english
        else "Söylenen web adresindeki sayfayı indirip okur; özetlemek ya da soruyu yanıtlamak için.",
        run=run,
        parameters={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Web address, e.g. 'bbc.com'" if english else "Web adresi, örn. 'ntv.com.tr'",
                }
            },
            "required": ["address"],
        },
        untrusted_output=True,
        spoken_action=lambda a: (
            f"Shall I open and read {a.get('address') or 'the page'}?"
            if english
            else f"{a.get('address') or 'Sayfayı'} adresindeki sayfayı açıp okuyayım mı?"
        ),
    )
