"""Unit tests for app/services/web_search_service.py.

Uses mocked HTTP/ddg calls so tests never hit the live network.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from app.services.web_search_service import WebSearchService


def _make_service(**overrides) -> WebSearchService:
    svc = WebSearchService.__new__(WebSearchService)
    svc.provider = overrides.get("provider", "duckduckgo")
    svc.max_results = overrides.get("max_results", 5)
    svc.tavily_key = overrides.get("tavily_key", "")
    return svc


# ── search() orchestration ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_empty_query_returns_error():
    svc = _make_service()
    res = await svc.search("   ")
    assert res["results"] == []
    assert "error" in res


@pytest.mark.asyncio
async def test_search_uses_provided_max_results_over_default():
    svc = _make_service(max_results=5)
    with patch.object(svc, "_search_duckduckgo", new=AsyncMock(return_value={"results": [1]})) as m:
        res = await svc.search("hello", max_results=3)
    m.assert_awaited_once_with("hello", 3)
    assert res["results"] == [1]


@pytest.mark.asyncio
async def test_search_uses_default_max_results_when_none():
    svc = _make_service(max_results=7)
    with patch.object(svc, "_search_duckduckgo", new=AsyncMock(return_value={"results": [1]})) as m:
        await svc.search("hello")
    m.assert_awaited_once_with("hello", 7)


@pytest.mark.asyncio
async def test_search_tavily_used_when_configured_and_returns_results():
    svc = _make_service(provider="tavily", tavily_key="sekret")
    tavily_res = {"results": [{"title": "t", "url": "u", "snippet": "c"}]}
    with patch.object(svc, "_search_tavily", new=AsyncMock(return_value=tavily_res)) as tavily:
        with patch.object(svc, "_search_duckduckgo", new=AsyncMock()) as ddg:
            res = await svc.search("query")
    tavily.assert_awaited_once()
    ddg.assert_not_awaited()
    assert res["results"] == [{"title": "t", "url": "u", "snippet": "c"}]


@pytest.mark.asyncio
async def test_search_tavily_falls_back_to_duckduckgo_when_no_results():
    svc = _make_service(provider="tavily", tavily_key="sekret")
    ddg_res = {"results": [{"title": "d"}]}
    with patch.object(svc, "_search_tavily", new=AsyncMock(return_value={"results": []})) as tavily:
        with patch.object(svc, "_search_duckduckgo", new=AsyncMock(return_value=ddg_res)) as ddg:
            res = await svc.search("query")
    tavily.assert_awaited_once()
    ddg.assert_awaited_once()
    assert res["results"] == [{"title": "d"}]


@pytest.mark.asyncio
async def test_search_tavily_not_used_without_key():
    svc = _make_service(provider="tavily", tavily_key="")
    with patch.object(svc, "_search_tavily", new=AsyncMock()) as tavily:
        with patch.object(svc, "_search_duckduckgo", new=AsyncMock(return_value={"results": []})):
            await svc.search("query")
    tavily.assert_not_awaited()


# ── _search_duckduckgo ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ddg_library_success():
    """The `ddgs` library branch returns results directly."""
    svc = _make_service()

    class FakeDDGItem:
        def __init__(self):
            pass

    class FakeDDGS:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, query, max_results):
            return iter([
                {"title": "T1", "href": "https://a.com", "body": "B1"},
                {"title": "T2", "link": "https://b.com", "snippet": "B2"},
            ])

    fake_mod = type("FakeDDGSMod", (), {"DDGS": FakeDDGS})()

    with patch.dict("sys.modules", {"ddgs": fake_mod}):
        res = await svc._search_duckduckgo("query", 3)

    assert res["provider"] == "duckduckgo_library"
    assert res["results"] == [
        {"title": "T1", "url": "https://a.com", "snippet": "B1"},
        {"title": "T2", "url": "https://b.com", "snippet": "B2"},
    ]


@pytest.mark.asyncio
async def test_ddg_library_failure_then_html_success():
    """When the library raises, the method should fall back to the HTML POST."""
    svc = _make_service()

    class RaisesDDGS:
        def __init__(self, *a, **k):
            raise RuntimeError("ddg unavailable")

    fake_lib = type("FakeLib", (), {"DDGS": RaisesDDGS})()

    # HTML fallback mock via httpx
    class FakeResp:
        status_code = 200
        text = (
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">Ex</a>'
            '<a class="result__snippet">Snippet here</a>'
        )

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    with patch.dict("sys.modules", {"ddgs": fake_lib}):
        with patch("httpx.AsyncClient", FakeClient):
            res = await svc._search_duckduckgo("query", 5)

    assert res["provider"] == "duckduckgo_html"
    assert res["results"][0]["url"] == "https://example.com/page"


@pytest.mark.asyncio
async def test_ddg_total_failure_returns_error():
    svc = _make_service()

    class RaisesDDGS:
        def __init__(self, *a, **k):
            raise RuntimeError("unavailable")

    fake_lib = type("FakeLib", (), {"DDGS": RaisesDDGS})()

    class RaisingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("network down")

    with patch.dict("sys.modules", {"ddgs": fake_lib}):
        with patch("httpx.AsyncClient", RaisingClient):
            res = await svc._search_duckduckgo("query", 5)

    assert res["results"] == []
    assert "error" in res


# ── _search_tavily ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tavily_success_parses_results():
    svc = _make_service(provider="tavily", tavily_key="key")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"results": [{"title": "A", "url": "https://a", "content": "body"}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc._search_tavily("query", 5)
    assert res["provider"] == "tavily"
    assert res["results"] == [{"title": "A", "url": "https://a", "snippet": "body"}]


@pytest.mark.asyncio
async def test_tavily_non_200_returns_error():
    svc = _make_service(provider="tavily", tavily_key="key")

    class FakeResp:
        status_code = 500

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        res = await svc._search_tavily("query", 5)
    assert res["results"] == []
    assert "error" in res


@pytest.mark.asyncio
async def test_tavily_exception_returns_error():
    svc = _make_service(provider="tavily", tavily_key="key")

    class RaisingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("network down")

    with patch("httpx.AsyncClient", RaisingClient):
        res = await svc._search_tavily("query", 5)
    assert res["results"] == []
    assert "error" in res
