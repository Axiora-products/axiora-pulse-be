"""Unit tests for app/services/web_scraper_service.py.

Uses mocked httpx responses so no live network calls are made.
"""
import pytest
from unittest.mock import patch

from app.services.web_scraper_service import WebScraperService

SAMPLE_HTML = """
<html>
<head><title>Example Page</title></head>
<body>
  <nav>Nav content nav nav nav</nav>
  <script>var junk = 1;</script>
  <h1>Hello World</h1>
  <p>This is a sufficiently long paragraph of content to be extracted.</p>
  <p>Another paragraph with enough words to satisfy the length threshold.</p>
  <li>List item one two three four five six seven</li>
</body>
</html>
"""


def _make_service(**overrides) -> WebScraperService:
    return WebScraperService(
        timeout=overrides.get("timeout", 10.0),
        max_length=overrides.get("max_length", 4000),
    )


@pytest.mark.asyncio
async def test_scrape_success_extracts_title_and_content():
    svc = _make_service()

    class FakeResp:
        status_code = 200
        text = SAMPLE_HTML

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is True
    assert res["title"] == "Example Page"
    assert "Hello World" in res["content"]
    assert res["length"] == len(res["content"])


@pytest.mark.asyncio
async def test_scrape_prepends_https_when_missing_scheme():
    svc = _make_service()
    captured = {}

    class FakeResp:
        status_code = 200
        text = SAMPLE_HTML

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            captured["url"] = url
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        await svc.scrape_webpage("example.com")

    assert captured["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_scrape_non_200_returns_error():
    svc = _make_service()

    class FakeResp:
        status_code = 404
        text = ""

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is False
    assert "error" in res


@pytest.mark.asyncio
async def test_scrape_error_title_detected():
    svc = _make_service()

    class FakeResp:
        status_code = 200
        text = "<html><head><title>404 - Page Not Found</title></head><body></body></html>"

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is False
    assert "Page returned non-content error title" in res["error"]


@pytest.mark.asyncio
async def test_scrape_insufficient_content_returns_error():
    svc = _make_service()

    class FakeResp:
        status_code = 200
        text = "<html><head><title>Short</title></head><body><p>tiny</p></body></html>"

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is False
    assert res["content"] == ""


@pytest.mark.asyncio
async def test_scrape_truncates_content():
    svc = _make_service(max_length=50)

    class FakeResp:
        status_code = 200

        @property
        def text(self):
            return ("<html><head><title>Big</title></head><body>"
                    + "<p>" + ("word " * 500) + "</p>"
                    + "</body></html>")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is True
    assert res["length"] <= 50 + len("\n... [Content Truncated]")
    assert "Content Truncated" in res["content"]


@pytest.mark.asyncio
async def test_scrape_timeout_returns_error():
    svc = _make_service()

    class RaisingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            import httpx
            raise httpx.TimeoutException("timed out")

    with patch("httpx.AsyncClient", RaisingClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is False
    assert "Request timed out" in res["error"]


@pytest.mark.asyncio
async def test_scrape_generic_exception_returns_error():
    svc = _make_service()

    class RaisingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise ValueError("boom")

    with patch("httpx.AsyncClient", RaisingClient):
        res = await svc.scrape_webpage("https://example.com")

    assert res["success"] is False
    assert res["error"] == "boom"
