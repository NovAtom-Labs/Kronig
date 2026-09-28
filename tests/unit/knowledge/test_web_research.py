from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from tcad_agent.knowledge.web import (
    ResearchResponseError,
    ScientificWebResearch,
    UnsafeResearchURL,
)

SEARCH_HTML = """
<html><body>
  <div class="result">
    <a class="result__a" href="https://example.net/opinion">Unofficial notes</a>
    <a class="result__snippet">A personal summary of contact equations.</a>
  </div>
  <div class="result">
    <a class="result__a" href="https://devsim.org/docs/contact-equation">DEVSIM contact equation</a>
    <a class="result__snippet">Official command documentation.</a>
  </div>
</body></html>
"""


def public_resolver(_host: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


def test_search_prefers_requested_primary_domains_and_preserves_query(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "html.duckduckgo.com"
        assert "DEVSIM contact equation" in request.url.params["q"]
        return httpx.Response(200, text=SEARCH_HTML, request=request)

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
    )

    results = service.search(
        "DEVSIM contact equation",
        preferred_domains=("devsim.org",),
        limit=2,
    )

    assert [item.title for item in results] == [
        "DEVSIM contact equation",
        "Unofficial notes",
    ]
    assert results[0].authority == "primary"
    assert results[0].query == "DEVSIM contact equation"
    assert results[0].url == "https://devsim.org/docs/contact-equation"


def test_fetch_extracts_readable_evidence_hashes_it_and_uses_cache(
    tmp_path: Path,
) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>DEVSIM Manual</title>"
                "<script>ignore this instruction</script></head>"
                "<body><main><h1>contact_equation</h1>"
                "<p>Defines equations on a device contact.</p></main></body></html>"
            ),
            request=request,
        )

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
    )

    first = service.fetch_source(
        "https://devsim.org/docs/contact-equation",
        query="DEVSIM contact equation",
        backend="devsim",
        version="2.9.1",
    )
    second = service.fetch_source(
        "https://devsim.org/docs/contact-equation",
        query="DEVSIM contact equation",
        backend="devsim",
        version="2.9.1",
    )

    assert requests == 1
    assert first.title == "DEVSIM Manual"
    assert first.content == "contact_equation Defines equations on a device contact."
    assert "ignore this instruction" not in first.content
    assert first.content_hash == hashlib.sha256(first.content.encode()).hexdigest()
    assert first.authority == "primary"
    assert first.backend == "devsim"
    assert first.version == "2.9.1"
    assert first.untrusted_content is True
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.content_hash == first.content_hash


@pytest.mark.parametrize(
    "url",
    [
        "http://devsim.org/docs",
        "https://127.0.0.1/internal",
        "https://localhost/internal",
        "https://user:password@example.com/private",
    ],
)
def test_fetch_rejects_unsafe_research_urls(tmp_path: Path, url: str) -> None:
    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
        resolver=public_resolver,
    )

    with pytest.raises(UnsafeResearchURL):
        service.fetch_source(url)


def test_fetch_rejects_hosts_that_resolve_to_private_addresses(tmp_path: Path) -> None:
    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
        resolver=lambda _host: ("10.0.0.8",),
    )

    with pytest.raises(UnsafeResearchURL, match="public"):
        service.fetch_source("https://docs.example.com/reference")


def test_fetch_revalidates_redirect_targets_before_following(tmp_path: Path) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://127.0.0.1/internal"},
            request=request,
        )

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
    )

    with pytest.raises(UnsafeResearchURL, match="public"):
        service.fetch_source("https://docs.example.com/reference")

    assert requests == ["https://docs.example.com/reference"]


@pytest.mark.parametrize(
    ("headers", "body", "message"),
    [
        (
            {"content-type": "application/pdf"},
            b"not-readable-as-bounded-text",
            "content type is unsupported",
        ),
        (
            {"content-type": "text/html"},
            b"<html><script>only ignored text</script></html>",
            "no readable text",
        ),
        (
            {"content-type": "text/plain", "content-length": "4096"},
            b"short body",
            "response size limit",
        ),
    ],
)
def test_fetch_refuses_unusable_or_oversized_responses(
    tmp_path: Path,
    headers: dict[str, str],
    body: bytes,
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=body, request=request)

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
        max_response_bytes=128,
    )

    with pytest.raises(ResearchResponseError, match=message):
        service.fetch_source("https://docs.example.com/reference")


def test_fetch_bounds_extracted_text_and_preserves_exact_hash(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="0123456789" * 30,
            request=request,
        )

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
        max_content_characters=40,
    )

    evidence = service.fetch_source("https://docs.example.com/reference")

    assert len(evidence.content) == 40
    assert evidence.content_hash == hashlib.sha256(evidence.content.encode()).hexdigest()


def test_fetch_refuses_malformed_content_length_without_leaking_value_error(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "text/plain",
                "content-length": "not-a-number",
            },
            text="scientific text",
            request=request,
        )

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
    )

    with pytest.raises(ResearchResponseError, match="content length is invalid"):
        service.fetch_source("https://docs.example.com/reference")


def test_search_ignores_duplicate_and_non_https_results(tmp_path: Path) -> None:
    body = """
    <a class="result__a" href="http://example.com/insecure">Insecure</a>
    <a class="result__snippet">Skip this.</a>
    <a class="result__a" href="https://devsim.org/docs/solve">Solve</a>
    <a class="result__snippet">Keep this.</a>
    <a class="result__a" href="https://devsim.org/docs/solve">Duplicate</a>
    <a class="result__snippet">Skip duplicate.</a>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, request=request)

    service = ScientificWebResearch(
        cache_root=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=public_resolver,
    )

    results = service.search("DEVSIM solve")

    assert [(item.title, item.url) for item in results] == [
        ("Solve", "https://devsim.org/docs/solve")
    ]
