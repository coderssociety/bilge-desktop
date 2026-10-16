"""Which of the headlines just read a request points at: "üçüncü haberi aç", "Claude'un keşfettiği buluşu açar mısın",
"tell me more about the second one". Recognizers misspell names ("Cloud'un" for "Claude'un"), so words match
loosely; a request has to point at a headline clearly, or "Telegram'ı aç" after a headline about Telegram would read
the news instead of opening the app."""

from dataclasses import dataclass

from bilge.core import text
from bilge.core.web import news_request
from bilge.core.web.rss_headlines import Item

_LAST = -1
# Turkish ones take endings ("üçüncüsünü"); "ilk" only short ones, not "ilkbahar".
_ORDINALS = (("ilk", 1), ("birinci", 1), ("ikinci", 2), ("ucuncu", 3), ("dorduncu", 4), ("besinci", 5),
             ("sonuncu", _LAST))  # fmt: skip
_ENGLISH_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": _LAST}
_OPEN_WORDS = ("acar", "acin", "acip", "acsan", "acabil", "aciver", "acmak", "open")
_BROWSER_WORDS = frozenset(
    {"tarayici", "tarayicida", "safari", "safaride", "chrome", "firefox", "firefoxta", "browser"}
)
_CUE_WORDS = ("anlat", "detay", "ayrinti", "oku", "ozetle", "icerig", "hakkinda", "read", "tell", "detail", "summar",
              "more")  # fmt: skip
_NEWS_WORDS = ("haber", "basli", "makale", "news", "headline", "story", "article")
_LIST_WORDS = ("haberler", "basliklar", "headlines")
# Said around a request without telling which headline it means.
_FILLERS = frozenset({
    "misin", "musun", "misiniz", "bana", "biraz", "daha", "bilgi", "simdi", "lutfen", "sunu", "bunu", "onu", "olan",
    "hangi", "icin", "gibi", "kadar", "neler", "nedir", "ne", "mi", "mu", "da", "de", "bu", "su", "o", "about",
    "please", "that", "this", "with", "from", "what", "says", "the", "one", "it", "me", "a", "an", "of", "to",
})  # fmt: skip


@dataclass(frozen=True)
class Request:
    item: Item
    # "Aç", "open": also shown in the browser, not only told.
    in_browser: bool


def find(command: str, last_reading: list[Item], heard: list[Item], asked: bool = False) -> Request | None:
    """`asked`: already known to be about one article (the model called for it), so no "aç" or "anlat" is needed."""
    words = _words(command)
    if not heard or not (asked or _asks_for_article(words)):
        return None
    place = next((p for p in map(_ordinal, words) if p is not None), None)
    # "Haberleri oku", "son başlıkları anlat" ask for the headlines themselves.
    if place is None and any(word.startswith(w) for word in words for w in _LIST_WORDS):
        return None
    opens = any(_is_open_word(word) or word in _BROWSER_WORDS for word in words)
    names_news = any(word.startswith(w) for word in words for w in _NEWS_WORDS)
    named = [w for w in words if _ordinal(w) is None and not news_request.is_topic_word(w) and _is_named(w)]
    # "İkincisini aç", "the second one"; not "ikinci sekmeyi aç" or "open the last tab".
    if place is not None and (names_news or not named):
        index = len(last_reading) - 1 if place == _LAST else place - 1
        return Request(last_reading[index], opens) if 0 <= index < len(last_reading) else None
    content = [word for word in named if len(word) >= 4]
    scored = [(sum(any(matches(w, t) for t in _words(item.title)) for w in content), item) for item in heard]
    best = max(scored, key=lambda pair: pair[0], default=(0, None))
    # A bare "aç" with names is how apps are opened too ("Claude Code'u aç"), so it needs more to go on.
    tells = any(word.startswith(_CUE_WORDS) for word in words)
    needed = 1 if names_news else 2 if tells or asked else 3
    if best[1] is None or best[0] < needed:
        return None
    return Request(best[1], opens)


def matches(said: str, title: str) -> bool:
    """The same word with another ending ("buluşu", "buluş"), or one a recognizer misheard ("cloudun", "claudeun")."""
    if len(said) < 4 or len(title) < 4:
        return False
    common = 0
    for a, b in zip(said, title, strict=False):
        if a != b:
            break
        common += 1
    if common >= min(5, len(said), len(title)):
        return True
    return len(said) >= 5 and len(title) >= 5 and said[:2] == title[:2] and text.levenshtein(said, title) <= 2


def _asks_for_article(words: list[str]) -> bool:
    return any(_is_open_word(word) or any(word.startswith(cue) for cue in _CUE_WORDS) for word in words)


def _is_open_word(word: str) -> bool:
    return word == "ac" or word.startswith(_OPEN_WORDS)


def _is_named(word: str) -> bool:
    """A word that says what the request is about, rather than how it is asked."""
    return (
        word not in _FILLERS
        and word not in _BROWSER_WORDS
        and not _is_open_word(word)
        and not word.startswith(_CUE_WORDS)
        and not word.startswith(_NEWS_WORDS)
    )


def _ordinal(word: str) -> int | None:
    if word in _ENGLISH_ORDINALS:
        return _ENGLISH_ORDINALS[word]
    for prefix, place in _ORDINALS:
        if word.startswith(prefix) and (len(prefix) >= 5 or len(word) <= len(prefix) + 3):
            return place
    return None


def _words(sentence: str) -> list[str]:
    return text.folded(sentence).split()
