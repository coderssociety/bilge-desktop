"""HTTP GET for anything the assistant fetches from the internet, limited to the public internet.

The host is resolved once, every address is checked, and the connection goes to a checked address with
the original name used for TLS and the Host header. Checking a name and then letting a library resolve it
again leaves a gap: the name could resolve to a local address the second time (DNS rebinding), and a web page
could then reach the router or a service on this machine.
"""

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bilge.core.language import AssistantLanguage
from bilge.core.web import network_address

TIMEOUT_SECONDS = 15
# For the whole fetch: a server trickling one byte at a time would otherwise keep the assistant waiting.
TOTAL_SECONDS = 25
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
ALLOWED_PORTS = frozenset({80, 443})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_CHUNK = 64 * 1024
_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")


class WebFetchError(Exception):
    """Messages are fixed text: anything the server sent (a redirect target, a status line) could be an
    instruction aimed at the model, which reads tool errors."""


class LocalAddressError(WebFetchError):
    pass


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    content_type: str
    body: bytes

    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip("\"'")
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def get(url: str, language: AssistantLanguage = AssistantLanguage.TURKISH, max_bytes: int = MAX_BYTES) -> Response:
    deadline = time.monotonic() + TOTAL_SECONDS
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        response, location = _get_once(current, language, max_bytes, deadline)
        if location is None:
            return response
        current = urljoin(current, location)
    raise WebFetchError("Too many redirects")


def _get_once(url: str, language: AssistantLanguage, max_bytes: int, deadline: float) -> tuple[Response, str | None]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not parts.hostname:
        raise WebFetchError("Unsupported address")
    try:
        port = parts.port or _DEFAULT_PORTS[scheme]
    except ValueError as error:
        raise WebFetchError("Unsupported address") from error
    if port not in ALLOWED_PORTS:
        raise WebFetchError("Port not allowed")
    host = parts.hostname
    if network_address.is_local_name(host):
        raise LocalAddressError("Local address")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    headers = {
        "Host": host if port == _DEFAULT_PORTS[scheme] else f"{host}:{port}",
        "User-Agent": "Mozilla/5.0 (compatible; Bilge/0.1)",
        "Accept-Language": "en,tr;q=0.8" if language is AssistantLanguage.ENGLISH else "tr,en;q=0.8",
        "Accept-Encoding": "identity",
    }
    last_error: Exception | None = None
    # Each checked address is tried in turn: a dual-stack name may list IPv6 first on a network without it.
    for address in _public_addresses(host, port):
        connection = _PinnedConnection(scheme, host, port, address)
        try:
            connection.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
            for name, value in headers.items():
                connection.putheader(name, value)
            connection.endheaders()
            reply = connection.getresponse()
            location = reply.getheader("Location")
            if reply.status in (301, 302, 303, 307, 308) and location:
                return Response(url, reply.status, "", b""), location
            body = _read_limited(reply, max_bytes, deadline)
            return Response(url, reply.status, reply.getheader("Content-Type", ""), body), None
        except (OSError, http.client.HTTPException) as error:
            last_error = error
        finally:
            connection.close()
    raise WebFetchError("Could not connect") from last_error


def _public_addresses(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise WebFetchError("Could not find the address") from error
    addresses = list(dict.fromkeys(info[4][0].split("%")[0] for info in infos))
    # Every address must be public: a name with one public and one private address could still be steered.
    if not addresses or not all(_is_public(a) for a in addresses):
        raise LocalAddressError("Local address")
    return addresses


def _is_public(address: str) -> bool:
    """Both checks must agree; the standard library also unwraps IPv4-mapped and 6to4 forms."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        # The deprecated IPv4-compatible form (::127.0.0.1) has no public use.
        if ip in _IPV4_COMPATIBLE:
            return False
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is not None and not embedded.is_global:
            return False
    return ip.is_global and network_address.is_public(address)


def _read_limited(reply: http.client.HTTPResponse, max_bytes: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := reply.read(_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise WebFetchError("The page is too large")
        if time.monotonic() > deadline:
            raise WebFetchError("The page took too long")
        chunks.append(chunk)
    return b"".join(chunks)


class _PinnedConnection(http.client.HTTPConnection):
    """Connects to an address checked beforehand while keeping the host name for TLS and the Host header."""

    def __init__(self, scheme: str, host: str, port: int, address: str):
        super().__init__(host, port, timeout=TIMEOUT_SECONDS)
        self._scheme = scheme
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        if self._scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
        self.sock = sock
