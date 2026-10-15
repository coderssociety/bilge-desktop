"""Readable text from a web page, without markup, scripts or styles. Not a full HTML parser:
good enough to summarize an article."""

import re

_DROPPED_BLOCKS = ("script", "style", "noscript", "svg", "head", "nav", "footer", "form")
_BLOCK_TAGS = ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article")
_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&rsquo;": "’",
    "&lsquo;": "‘",
    "&ldquo;": "“",
    "&rdquo;": "”",
    "&hellip;": "…",
    "&ndash;": "–",
    "&mdash;": "—",
}

# Pages are cut to this size first; extraction is meant for article text, not whole sites.
_MAX_INPUT_CHARACTERS = 600_000
_MAX_CODE_POINT = 0x10FFFF
_SURROGATES = range(0xD800, 0xE000)
_MAX_ENTITY_DIGITS = 10

_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_BLOCK_TAG_PATTERNS = tuple(re.compile(rf"</?{tag}\b[^>]*>", re.IGNORECASE) for tag in _BLOCK_TAGS)
_ANY_TAG = re.compile(r"<[^>]+>")
_NUMERIC_ENTITY = re.compile(r"&#(x?)([0-9a-fA-F]+);")
_TITLE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.IGNORECASE)


def extract(html: str) -> str:
    text = html[:_MAX_INPUT_CHARACTERS]
    for tag in _DROPPED_BLOCKS:
        text = _removing_blocks(tag, text)
    text = _COMMENT.sub(" ", text)
    for pattern in _BLOCK_TAG_PATTERNS:
        text = pattern.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    for entity, value in _ENTITIES.items():
        text = text.replace(entity, value)
    text = _NUMERIC_ENTITY.sub(_decode_numeric_entity, text)
    # Swift treats "\r\n" as one whitespace character, so it never splits a line.
    lines = (" ".join(line.split()) for line in text.replace("\r\n", " ").split("\n"))
    return "\n".join(line for line in lines if line)


def title(html: str) -> str | None:
    match = _TITLE.search(html)
    if match is None:
        return None
    text = extract(match[0]).strip()
    return text or None


def _removing_blocks(tag: str, text: str) -> str:
    """One forward scan per tag. A lazy regex rescans to the end for every unclosed tag, which is
    quadratic on pages with thousands of them."""
    opening = re.compile(re.escape(f"<{tag}"), re.IGNORECASE)
    closing = re.compile(re.escape(f"</{tag}>"), re.IGNORECASE)
    pieces: list[str] = []
    position = 0
    while (open_match := opening.search(text, position)) is not None:
        following = text[open_match.end()] if open_match.end() < len(text) else " "
        if following.isalpha() or following.isnumeric():
            pieces.append(text[position : open_match.end()])
            position = open_match.end()
            continue
        pieces.append(text[position : open_match.start()] + " ")
        close_match = closing.search(text, open_match.end())
        if close_match is None:
            return "".join(pieces)
        position = close_match.end()
    pieces.append(text[position:])
    return "".join(pieces)


def _decode_numeric_entity(match: re.Match[str]) -> str:
    is_hex = bool(match[1])
    digits = match[2]
    # Long digit runs are out of range anyway, and int() refuses very long strings.
    if (not is_hex and not digits.isdigit()) or len(digits.lstrip("0")) > _MAX_ENTITY_DIGITS:
        return match[0]
    value = int(digits, 16 if is_hex else 10)
    if value > _MAX_CODE_POINT or value in _SURROGATES:
        return match[0]
    return chr(value)
