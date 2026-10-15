"""The HTMLText and NetworkAddress cases of the Swift SecurityTests."""

import time

import pytest

from bilge.core.web import html_text, network_address

_MAX_EXTRACTION_SECONDS = 2


@pytest.mark.parametrize(
    ("address", "is_public"),
    [
        ("8.8.8.8", True),
        ("151.101.1.69", True),
        ("2606:4700::6810:84e5", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("192.168.1.30", False),
        ("172.20.0.5", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("::", False),
        ("fe80::1", False),
        ("fd12:3456::1", False),
        ("::ffff:192.168.1.1", False),
        ("::ffff:8.8.8.8", True),
        ("999.1.1.1", False),
        ("abc", False),
        ("64:ff9b::192.168.1.1", False),
        ("64:ff9b::8.8.8.8", True),
        ("fec0::1", False),
    ],
)
def test_only_public_addresses_are_fetchable(address: str, is_public: bool) -> None:
    assert network_address.is_public(address) == is_public


@pytest.mark.parametrize(
    ("host", "is_local"),
    [
        ("localhost", True),
        ("router.local", True),
        ("nas", True),
        ("printer.lan", True),
        ("ntv.com.tr", False),
        ("api.open-meteo.com", False),
    ],
)
def test_local_host_names(host: str, is_local: bool) -> None:
    assert network_address.is_local_name(host) == is_local


def test_unclosed_tags_do_not_make_extraction_slow() -> None:
    page = "<form a>x " * 60_000 + "<p>son</p>"
    started = time.monotonic()
    html_text.extract(page)
    assert time.monotonic() - started < _MAX_EXTRACTION_SECONDS
