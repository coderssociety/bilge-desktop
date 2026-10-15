"""Whether an IP address is on the public internet. Fetching tools refuse everything else, so a web
page cannot make the assistant probe the router, the LM Studio server or other local services."""

import re

_LOCAL_SUFFIXES = ("local", "localhost", "internal", "lan", "home", "arpa")
_DECIMAL = re.compile(r"[+-]?[0-9]+")
_HEX_GROUP = re.compile(r"\+?[0-9a-fA-F]+")
_GROUP_COUNT = 8
_MAX_OCTET = 255
_MAX_GROUP_DIGITS = 4


def is_public(address: str) -> bool:
    octets = _ipv4(address)
    if octets is not None:
        return _is_public_ipv4(octets)
    groups = _ipv6(address)
    if groups is None:
        return False
    embedded_ipv4 = [groups[6] >> 8, groups[6] & 0xFF, groups[7] >> 8, groups[7] & 0xFF]
    if all(group == 0 for group in groups[:5]) and groups[5] == 0xFFFF:
        return _is_public_ipv4(embedded_ipv4)
    # NAT64 (64:ff9b::/96) reaches IPv4 hosts from IPv6-only networks, private ones included.
    if groups[0] == 0x64 and groups[1] == 0xFF9B and all(group == 0 for group in groups[2:6]):
        return _is_public_ipv4(embedded_ipv4)
    if all(group == 0 for group in groups[:7]):
        return False
    first = groups[0]
    if first & 0xFE00 == 0xFC00:  # unique local fc00::/7
        return False
    if first & 0xFFC0 == 0xFE80:  # link-local fe80::/10
        return False
    if first & 0xFFC0 == 0xFEC0:  # deprecated site-local fec0::/10
        return False
    return first & 0xFF00 != 0xFF00  # multicast


def is_local_name(host: str) -> bool:
    """Host names that never leave the machine or the local network."""
    host = host.lower().strip(".")
    return host == "localhost" or any(host.endswith(f".{suffix}") for suffix in _LOCAL_SUFFIXES) or "." not in host


def _is_public_ipv4(octets: list[int]) -> bool:
    first, second = octets[0], octets[1]
    if first in (0, 10, 127) or first >= 224:
        return False
    private_pairs = (
        (first == 169 and second == 254)
        or (first == 192 and second in (0, 168))
        or (first == 172 and 16 <= second <= 31)
        or (first == 100 and 64 <= second <= 127)
        or (first == 198 and 18 <= second <= 19)
    )
    return not private_pairs


def _ipv4(text: str) -> list[int] | None:
    parts = text.split(".")
    if len(parts) != 4:
        return None
    octets = [octet for octet in map(_octet, parts) if octet is not None]
    return octets if len(octets) == 4 else None


def _octet(part: str) -> int | None:
    # Swift's Int(_:) accepts a sign and rejects overflow; a long digit run is never an octet.
    if not _DECIMAL.fullmatch(part) or len(part.lstrip("+-").lstrip("0")) > 3:
        return None
    value = int(part)
    return value if 0 <= value <= _MAX_OCTET else None


def _ipv6(text: str) -> list[int] | None:
    zone_split = [part for part in text.split("%") if part]
    address = zone_split[0] if zone_split else text
    if ":" not in address:
        return None
    # An embedded IPv4 tail ("::ffff:8.8.8.8") becomes two hex groups.
    colon = address.rfind(":")
    octets = _ipv4(address[colon + 1 :])
    if octets is not None:
        address = address[: colon + 1] + f"{octets[0] << 8 | octets[1]:x}:{octets[2] << 8 | octets[3]:x}"
    halves = address.split("::")
    if len(halves) > 2:
        return None
    head = _hex_groups(halves[0])
    if head is None or len(head) > _GROUP_COUNT:
        return None
    tail = _hex_groups(halves[1]) if len(halves) == 2 else []
    if tail is None:
        return None
    missing = _GROUP_COUNT - len(head) - len(tail)
    if (missing < 1) if len(halves) == 2 else (missing != 0):
        return None
    return head + [0] * missing + tail


def _hex_groups(part: str) -> list[int] | None:
    if not part:
        return []
    values: list[int] = []
    for group in part.split(":"):
        # Swift's UInt16(_:radix:) rejects overflow past four hex digits.
        if not _HEX_GROUP.fullmatch(group) or len(group.lstrip("+").lstrip("0")) > _MAX_GROUP_DIGITS:
            return None
        values.append(int(group, 16))
    return values
