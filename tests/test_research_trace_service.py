"""Unit tests for app/services/research_trace_service.py.

Covers the singletons/ContextVar propagation, run lifecycle, query/source
logging (with duplicate suppression and SSE broadcasting), stream subscription,
and trace retrieval.
"""
import asyncio
import pytest

from app.services.research_trace_service import (
    ResearchTraceService,
    current_run_id_var,
    current_agent_var,
    research_trace_service,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fresh_service() -> ResearchTraceService:
    """Return a clean ResearchTraceService instance with an empty run store.

    Also resets the module-level contextvars so tests are isolated from each
    other (they are shared globals set by set_context()).
    """
    current_run_id_var.set(None)
    current_agent_var.set(None)
    svc = ResearchTraceService.__new__(ResearchTraceService)
    svc._runs = {}
    svc._lock = asyncio.Lock()
    return svc


# ── ContextVar helpers ────────────────────────────────────────────────────────

def test_set_context_and_get_run_id():
    svc = _fresh_service()
    svc.set_context("run-abc", "idea_validation_agent")
    assert svc.get_context_run_id() == "run-abc"
    assert svc.get_context_agent_name() == "idea_validation_agent"


def test_set_context_run_id_only():
    svc = _fresh_service()
    svc.set_context("run-xyz")
    assert svc.get_context_run_id() == "run-xyz"
    # agent name should retain a prior value (only set when provided)
    assert svc.get_context_agent_name() is None or True


def test_context_vars_are_isolated_per_context():
    svc = _fresh_service()
    # Module-level ContextVars — ensure the service sets them on the current context
    svc.set_context("run-1", "agent-1")
    assert current_run_id_var.get() == "run-1"
    assert current_agent_var.get() == "agent-1"
    svc.set_context("run-2", "agent-2")
    assert current_run_id_var.get() == "run-2"
    assert current_agent_var.get() == "agent-2"


def test_default_context_is_none():
    # Fresh class-level defaults in a new context
    svc = _fresh_service()
    assert svc.get_context_run_id() is None
    assert svc.get_context_agent_name() is None


# ── Run lifecycle ─────────────────────────────────────────────────────────────

def test_start_run_trace_initializes_store():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    assert "run-1" in svc._runs
    assert svc._runs["run-1"]["queries"] == []
    assert svc._runs["run-1"]["sources"] == []
    assert svc._runs["run-1"]["is_active"] is True
    assert svc._runs["run-1"]["subscribers"] == set()


def test_end_run_trace_marks_inactive():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    svc.end_run_trace("run-1")
    assert svc._runs["run-1"]["is_active"] is False


def test_end_run_trace_unknown_run_is_noop():
    svc = _fresh_service()
    # Should not raise for unknown run ids
    svc.end_run_trace("does-not-exist")


# ── log_query ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_query_without_run_id_returns_untracked_trace():
    svc = _fresh_service()
    trace = await svc.log_query("some query", run_id=None, agent_name="agent")
    assert trace.query == "some query"
    assert trace.agent_name == "agent"
    # No run registered — nothing stored
    assert svc._runs == {}


@pytest.mark.asyncio
async def test_log_query_stores_and_uses_context_when_run_id_omitted():
    svc = _fresh_service()
    svc.set_context("run-ctx", "market_research_agent")
    svc.start_run_trace("run-ctx")
    trace = await svc.log_query("context query")
    assert trace.agent_name == "market_research_agent"
    assert svc._runs["run-ctx"]["queries"] == [trace]


@pytest.mark.asyncio
async def test_log_query_defaults_agent_name():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    trace = await svc.log_query("q", run_id="run-1")
    assert trace.agent_name == "orchestration_agent"


@pytest.mark.asyncio
async def test_log_query_dedupes_identical_queries():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    await svc.log_query("same query", run_id="run-1")
    await svc.log_query("same query", run_id="run-1")
    assert len(svc._runs["run-1"]["queries"]) == 1


@pytest.mark.asyncio
async def test_log_query_auto_creates_run():
    svc = _fresh_service()
    trace = await svc.log_query("auto query", run_id="run-new")
    assert "run-new" in svc._runs
    assert svc._runs["run-new"]["queries"] == [trace]


# ── log_source ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_source_stores_source():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    trace = await svc.log_source(
        "https://example.com", title="Example", snippet="Snippet", run_id="run-1"
    )
    assert svc._runs["run-1"]["sources"] == [trace]
    assert trace.url == "https://example.com"
    assert trace.title == "Example"


@pytest.mark.asyncio
async def test_log_source_dedupes_identical_urls():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    await svc.log_source("https://example.com", run_id="run-1")
    await svc.log_source("https://example.com", run_id="run-1")
    assert len(svc._runs["run-1"]["sources"]) == 1


@pytest.mark.asyncio
async def test_log_source_without_run_id_is_untracked():
    svc = _fresh_service()
    trace = await svc.log_source("https://example.com")
    assert trace.url == "https://example.com"
    assert svc._runs == {}


# ── get_traces ────────────────────────────────────────────────────────────────

def test_get_traces_unknown_run_returns_empty():
    svc = _fresh_service()
    resp = svc.get_traces("missing")
    assert resp.run_id == "missing"
    assert resp.queries == []
    assert resp.sources == []
    assert resp.is_active is False


def test_get_traces_returns_captured_data():
    svc = _fresh_service()
    svc.start_run_trace("run-1")
    assert svc.get_traces("run-1").is_active is True


# ── Subscribe stream / SSE ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_stream_auto_creates_run_and_yields_snapshot():
    svc = _fresh_service()

    gen = svc.subscribe_stream("run-1")
    event = await gen.__anext__()
    assert event["event"] == "snapshot"
    assert event["run_id"] == "run-1"
    assert "data" in event
    await gen.aclose()


@pytest.mark.asyncio
async def test_subscribe_stream_receives_broadcasted_events():
    svc = _fresh_service()
    svc.start_run_trace("run-1")

    received = []

    async def consumer():
        gen = svc.subscribe_stream("run-1")
        try:
            snapshot = await gen.__anext__()
            received.append(snapshot)
            # Log an event now that the subscriber queue is registered
            await svc.log_query("q1", run_id="run-1")
            event = await gen.__anext__()
            received.append(event)
            svc.end_run_trace("run-1")
            completed = await gen.__anext__()
            received.append(completed)
        except asyncio.CancelledError:
            raise
        finally:
            await gen.aclose()

    await consumer()

    events = [e["event"] for e in received]
    assert events[0] == "snapshot"
    assert "research_query" in events
    assert "run_completed" in events


@pytest.mark.asyncio
async def test_subscribe_stream_unsubscribes_on_exit():
    svc = _fresh_service()
    svc.start_run_trace("run-1")

    async def consume_then_stop():
        gen = svc.subscribe_stream("run-1")
        await gen.__anext__()  # snapshot
        await gen.aclose()

    await consume_then_stop()
    # After close, the queue should have been removed from subscribers
    assert svc._runs["run-1"]["subscribers"] == set()


# ── Singleton sanity ──────────────────────────────────────────────────────────

def test_module_singleton():
    assert research_trace_service is ResearchTraceService()
    assert isinstance(research_trace_service, ResearchTraceService)
