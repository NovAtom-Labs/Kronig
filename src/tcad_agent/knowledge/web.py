"""Bounded external research for scientific evidence."""

from __future__ import annotations

import html
import ipaddress
import socket
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

from tcad_agent.knowledge.models import WebEvidenceRecord, WebSearchResult


class UnsafeResearchURL(ValueError):
    """Raised when a research URL could reach a non-public network target."""


class ResearchResponseError(ValueError):
    """Raised when a remote research response cannot be safely consumed."""


Resolver = Callable[[str], tuple[str, ...]]


def _resolve_public_addresses(host: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(item[4][0])
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        )
    )


def _public_url(url: str, resolver: Resolver) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeResearchURL("research sources must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeResearchURL("research URL authority is invalid")
    if parsed.port not in {None, 443}:
        raise UnsafeResearchURL("research URL must use the standard HTTPS port")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeResearchURL("research source must resolve to a public address")
    try:
        literal = ipaddress.ip_address(host)
        addresses: tuple[str, ...] = (str(literal),)
    except ValueError:
        try:
            addresses = resolver(host)
        except OSError as exc:
            raise UnsafeResearchURL("research source hostname could not be resolved") from exc
    if not addresses:
        raise UnsafeResearchURL("research source hostname did not resolve")
    try:
        parsed_addresses = tuple(ipaddress.ip_address(address) for address in addresses)
    except ValueError as exc:
        raise UnsafeResearchURL("research source resolved to an invalid address") from exc
    if any(not address.is_global for address in parsed_addresses):
        raise UnsafeResearchURL("research source must resolve only to public addresses")
    return parsed.geturl()


class _SearchHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str]] = []
        self._current_url = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._current_url = attributes.get("href") or ""
            self._capture_title = True
        elif "result__snippet" in classes:
            self._capture_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
        if self._capture_snippet and tag in {"a", "div", "span"}:
            self._capture_snippet = False
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        if self._current_url and self._title_parts:
            self.results.append(
                (
                    " ".join("".join(self._title_parts).split()),
                    self._current_url,
                    " ".join("".join(self._snippet_parts).split()),
                )
            )
        self._current_url = ""
        self._title_parts = []
        self._snippet_parts = []


class _ReadableHTMLParser(HTMLParser):
    _ignored: ClassVar[set[str]] = {
        "script",
        "style",
        "noscript",
        "svg",
        "template",
    }
    _separators: ClassVar[set[str]] = {
        "article",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag in self._ignored:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag == "title":
            self._in_title = True
        elif not self._ignored_depth and tag in self._separators:
            self.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif not self._ignored_depth and tag in self._separators:
            self.text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.text_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())

    @property
    def text(self) -> str:
        return " ".join("".join(self.text_parts).split())


def _result_url(raw_url: str) -> str:
    parsed = urlparse(html.unescape(raw_url))
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return parsed.geturl()


def _host_matches(host: str, domains: Iterable[str]) -> bool:
    lowered = host.lower().rstrip(".")
    return any(
        lowered == domain.lower().rstrip(".")
        or lowered.endswith(f".{domain.lower().rstrip('.')}")
        for domain in domains
    )


_SCHOLARLY_DOMAINS = (
    "arxiv.org",
    "crossref.org",
    "doi.org",
    "ieee.org",
    "iop.org",
    "nature.com",
    "nist.gov",
    "sciencedirect.com",
    "springer.com",
)

_PRIMARY_DOMAINS = (
    "devsim.org",
    "devsim.net",
    "synopsys.com",
)


def _authority(
    url: str, preferred_domains: tuple[str, ...]
) -> Literal["primary", "scholarly", "community", "unknown"]:
    host = urlparse(url).hostname or ""
    if _host_matches(host, (*preferred_domains, *_PRIMARY_DOMAINS)):
        return "primary"
    if _host_matches(host, _SCHOLARLY_DOMAINS):
        return "scholarly"
    if host in {"github.com", "gitlab.com"}:
        return "community"
    return "unknown"


class ScientificWebResearch:
    def __init__(
        self,
        *,
        cache_root: Path,
        client: httpx.Client | None = None,
        resolver: Resolver = _resolve_public_addresses,
        search_endpoint: str = "https://html.duckduckgo.com/html/",
        max_response_bytes: int = 2 * 1024 * 1024,
        max_content_characters: int = 120_000,
        cache_ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "Agent-Kronig-Scientific-Research/0.1"},
        )
        self.resolver = resolver
        self.search_endpoint = search_endpoint
        self.max_response_bytes = max_response_bytes
        self.max_content_characters = max_content_characters
        self.cache_ttl = cache_ttl

    def search(
        self,
        query: str,
        *,
        preferred_domains: tuple[str, ...] = (),
        limit: int = 5,
    ) -> tuple[WebSearchResult, ...]:
        normalized = " ".join(query.split())
        if not normalized or limit <= 0:
            return ()
        response = self.client.get(
            self.search_endpoint,
            params={"q": normalized},
            headers={"Accept": "text/html"},
        )
        self._require_response(response)
        parser = _SearchHTMLParser()
        parser.feed(response.text)
        parser.close()
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        for title, raw_url, snippet in parser.results:
            url = _result_url(raw_url)
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or url in seen:
                continue
            seen.add(url)
            results.append(
                WebSearchResult(
                    query=normalized,
                    title=title,
                    url=url,
                    snippet=snippet,
                    authority=_authority(url, preferred_domains),
                )
            )
        priority = {"primary": 0, "scholarly": 1, "community": 2, "unknown": 3}
        ranked = sorted(
            enumerate(results),
            key=lambda item: (priority[item[1].authority], item[0]),
        )
        return tuple(result for _, result in ranked[: min(limit, 10)])

    def fetch_source(
        self,
        url: str,
        *,
        query: str = "",
        backend: str | None = None,
        version: str | None = None,
    ) -> WebEvidenceRecord:
        safe_url = _public_url(url, self.resolver)
        cached = self._read_cache(safe_url)
        if cached is not None:
            return cached.model_copy(update={"from_cache": True})
        response = self.client.get(
            safe_url,
            headers={"Accept": "text/html,text/plain;q=0.9"},
            follow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            location = response.headers.get("location", "")
            if not location:
                raise ResearchResponseError("research source returned an empty redirect")
            redirected = _public_url(urljoin(safe_url, location), self.resolver)
            response = self.client.get(
                redirected,
                headers={"Accept": "text/html,text/plain;q=0.9"},
                follow_redirects=False,
            )
            safe_url = redirected
        self._require_response(response)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {"text/html", "text/plain"}:
            raise ResearchResponseError(
                f"research source content type is unsupported: {content_type or 'missing'}"
            )
        raw = response.content
        if len(raw) > self.max_response_bytes:
            raise ResearchResponseError("research source exceeds the response size limit")
        decoded = response.text
        title = urlparse(safe_url).hostname or safe_url
        if content_type == "text/html":
            parser = _ReadableHTMLParser()
            parser.feed(decoded)
            parser.close()
            content = parser.text
            title = parser.title or title
        else:
            content = " ".join(decoded.split())
        content = content[: self.max_content_characters].strip()
        if not content:
            raise ResearchResponseError("research source contains no readable text")
        record = WebEvidenceRecord.create(
            title=title,
            url=safe_url,
            content_type=content_type,
            content=content,
            query=" ".join(query.split()),
            authority=_authority(safe_url, ()),
            backend=backend,
            version=version,
            from_cache=False,
        )
        self._write_cache(record)
        return record

    def _require_response(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResearchResponseError(
                f"research request failed with HTTP {response.status_code}"
            ) from exc
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise ResearchResponseError(
                    "research source content length is invalid"
                ) from exc
            if declared_length < 0:
                raise ResearchResponseError(
                    "research source content length is invalid"
                )
            if declared_length > self.max_response_bytes:
                raise ResearchResponseError(
                    "research source exceeds the response size limit"
                )
        if len(response.content) > self.max_response_bytes:
            raise ResearchResponseError("research source exceeds the response size limit")

    def _cache_path(self, url: str) -> Path:
        return self.cache_root / f"{sha256(url.encode()).hexdigest()}.json"

    def _read_cache(self, url: str) -> WebEvidenceRecord | None:
        path = self._cache_path(url)
        try:
            record = WebEvidenceRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        age = datetime.now(UTC) - record.retrieved_at
        return record if age <= self.cache_ttl else None

    def _write_cache(self, record: WebEvidenceRecord) -> None:
        path = self._cache_path(record.url)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
