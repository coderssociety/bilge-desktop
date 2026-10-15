"""Opening a website or a search page in the browser for the user to read; nothing is read back."""

from enum import StrEnum
from typing import Any
from urllib.parse import urlencode, urlsplit

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import Opener
from bilge.desktop.process import DesktopError
from bilge.tools.base import Tool, ToolError
from bilge.tools.desktop.common import choice, failure, obj, string_argument, text


class SearchService(StrEnum):
    GOOGLE = "google"
    YOUTUBE = "youtube"
    MAPS = "maps"
    WIKIPEDIA = "wikipedia"


_TEXTS = {
    AssistantLanguage.TURKISH: {
        "search": "Kullanıcı açıkça aramamı istediğinde ('Google'da ara', 'YouTube'da bul') tarayıcıda arama sayfasını açar. Soruları yanıtlamak için kullanılmaz.",
        "query": "Aranacak ifade",
        "service": "Arama yapılacak servis",
        "no_query": "Ne arayacağımı anlayamadım.",
        "searched": "Tarayıcıda '{query}' araması açıldı.",
        "open": "Bilinen bir web sitesini tarayıcıda açar. Örnek: 'github.com', 'sahibinden.com'.",
        "address": "Alan adı veya tam adres, örn. 'github.com'",
        "bad_address": "'{address}' geçerli bir web adresi değil.",
        "opened": "{host} açıldı.",
        "browser_failed": "Tarayıcı açılamadı.",
    },
    AssistantLanguage.ENGLISH: {
        "search": "When the user explicitly asks to search ('search Google for', 'find on YouTube'), opens the search page in the browser. Not for answering questions.",
        "query": "What to search for",
        "service": "Where to search",
        "no_query": "I didn't get what to search for.",
        "searched": "Opened a search for '{query}' in the browser.",
        "open": "Opens a known website in the browser, e.g. 'github.com', 'bbc.co.uk'.",
        "address": "A domain or a full address, e.g. 'github.com'",
        "bad_address": "'{address}' is not a valid web address.",
        "opened": "Opened {host}.",
        "browser_failed": "The browser didn't open.",
    },
}


def web_url(address: str) -> str | None:
    """Only http(s) addresses with a host that has a dot; file:, javascript: and app schemes are refused."""
    trimmed = address.strip().replace(" ", "")
    candidate = trimmed if "://" in trimmed else f"https://{trimmed}"
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host or "." not in host:
        return None
    return candidate


def search_url(service: SearchService, query: str, language: AssistantLanguage) -> str:
    if service is SearchService.YOUTUBE:
        return "https://www.youtube.com/results?" + urlencode({"search_query": query})
    if service is SearchService.MAPS:
        return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})
    if service is SearchService.WIKIPEDIA:
        return f"https://{language.code}.wikipedia.org/w/index.php?" + urlencode({"search": query})
    return "https://www.google.com/search?" + urlencode({"q": query})


def web_tools(opener: Opener, language: AssistantLanguage) -> list[Tool]:
    texts = _TEXTS[language]

    def open_in_browser(url: str) -> None:
        try:
            opener.open(url)
        except DesktopError as error:
            raise failure(error, language, texts["browser_failed"]) from error

    def search(arguments: dict[str, Any]) -> str:
        query = string_argument(arguments, "query")
        if not query:
            raise ToolError(texts["no_query"])
        try:
            service = SearchService(string_argument(arguments, "service") or SearchService.GOOGLE)
        except ValueError:
            service = SearchService.GOOGLE
        open_in_browser(search_url(service, query, language))
        return texts["searched"].format(query=query)

    def open_website(arguments: dict[str, Any]) -> str:
        address = string_argument(arguments, "address")
        url = web_url(address)
        if url is None:
            raise ToolError(texts["bad_address"].format(address=address))
        open_in_browser(url)
        return texts["opened"].format(host=urlsplit(url).hostname)

    return [
        Tool(
            "searchWeb",
            texts["search"],
            run=search,
            parameters=obj(
                ["query"],
                query=text(texts["query"]),
                service=choice(SearchService, texts["service"]),
            ),
        ),
        Tool(
            "openWebsite", texts["open"], run=open_website, parameters=obj(["address"], address=text(texts["address"]))
        ),
    ]
