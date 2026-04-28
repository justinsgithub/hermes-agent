"""
Tests for the /v1/memory/* introspection endpoints on the API server adapter.

Covers:
- Auth enforcement (401 when API_SERVER_KEY is set and missing/wrong)
- Provider-not-configured graceful response (available=false)
- Successful status / profile / context / search / stats with mocked Honcho
- Legacy compatibility wrappers return {available, notice} envelopes
"""

from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter, cors_middleware

_MEM_MOD = "gateway.platforms.api_server_memory"


def _make_adapter(api_key: str = "") -> APIServerAdapter:
    extra = {}
    if api_key:
        extra["key"] = api_key
    config = PlatformConfig(enabled=True, extra=extra)
    return APIServerAdapter(config)


def _create_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app["api_server_adapter"] = adapter
    app.router.add_get("/health", adapter._handle_health)
    app.router.add_get("/v1/memory/status", adapter._handle_memory_status)
    app.router.add_get("/v1/memory/stats", adapter._handle_memory_stats)
    app.router.add_get("/v1/memory/profile", adapter._handle_memory_profile)
    app.router.add_get("/v1/memory/context", adapter._handle_memory_context)
    app.router.add_post("/v1/memory/search", adapter._handle_memory_search)
    app.router.add_get("/v1/memory/facts", adapter._handle_memory_facts_compat)
    app.router.add_get("/v1/memory/entities", adapter._handle_memory_entities_compat)
    app.router.add_get("/v1/memory/notebook", adapter._handle_memory_notebook_compat)
    app.router.add_get("/v1/memory/user-profile", adapter._handle_memory_user_profile_compat)
    return app


@pytest.fixture
def adapter():
    return _make_adapter()


@pytest.fixture
def auth_adapter():
    return _make_adapter(api_key="sk-test")


def _fake_cfg(**overrides):
    cfg = MagicMock()
    cfg.enabled = True
    cfg.api_key = "fake-api-key"
    cfg.base_url = None
    cfg.workspace_id = "test-workspace"
    cfg.host = "test-host"
    cfg.environment = "production"
    cfg.peer_name = "test-user"
    cfg.ai_peer = "test-ai"
    cfg.recall_mode = "hybrid"
    cfg.session_strategy = "per-directory"
    cfg.context_tokens = 1024
    cfg.dialectic_depth = 1
    cfg.dialectic_reasoning_level = "low"
    cfg.dialectic_dynamic = True
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


class TestMemoryAuth:
    @pytest.mark.asyncio
    async def test_status_requires_auth_when_key_set(self, auth_adapter):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/v1/memory/status")
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_status_passes_auth_when_key_matches(self, auth_adapter):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value=None):
                resp = await cli.get(
                    "/v1/memory/status",
                    headers={"Authorization": "Bearer sk-test"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["available"] is False

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, auth_adapter):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(
                "/v1/memory/search",
                json={"query": "foo"},
            )
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_no_key_allows_local(self, adapter):
        """With no API_SERVER_KEY configured, local callers shouldn't be blocked."""
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value=None):
                resp = await cli.get("/v1/memory/status")
                assert resp.status == 200


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestMemoryStatus:
    @pytest.mark.asyncio
    async def test_status_no_provider(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value=None):
                resp = await cli.get("/v1/memory/status")
                data = await resp.json()
                assert data["available"] is False
                assert "no memory provider" in data["reason"].lower()

    @pytest.mark.asyncio
    async def test_status_unsupported_provider(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="mem0"):
                resp = await cli.get("/v1/memory/status")
                data = await resp.json()
                assert data["available"] is False
                assert data["provider"] == "mem0"

    @pytest.mark.asyncio
    async def test_status_honcho_active(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get("/v1/memory/status")
                data = await resp.json()
                assert data["available"] is True
                assert data["provider"] == "honcho"
                assert data["workspace"] == "test-workspace"
                assert data["peers"]["user"] == "test-user"
                assert data["peers"]["ai"] == "test-ai"
                assert data["recall_mode"] == "hybrid"

    @pytest.mark.asyncio
    async def test_status_honcho_disabled(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg(enabled=False)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, None)):
                resp = await cli.get("/v1/memory/status")
                data = await resp.json()
                assert data["available"] is False
                assert "disabled" in data["reason"].lower()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestMemoryProfile:
    @pytest.mark.asyncio
    async def test_profile_user_alias(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        manager._fetch_peer_context.return_value = {
            "representation": "Justin runs Aivex.",
            "card": ["founder of Aivex", "uses tailscale"],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get("/v1/memory/profile?peer=user")
                data = await resp.json()
                assert data["available"] is True
                assert data["peer"] == "user"
                assert data["peer_id"] == "test-user"
                assert "Aivex" in data["representation"]
                assert len(data["card"]) == 2
                manager._fetch_peer_context.assert_called_with("test-user", target="test-user")

    @pytest.mark.asyncio
    async def test_profile_ai_alias(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        manager._fetch_peer_context.return_value = {"representation": "", "card": []}
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get("/v1/memory/profile?peer=ai")
                data = await resp.json()
                assert data["peer_id"] == "test-ai"
                assert data["card"] == []
                manager._fetch_peer_context.assert_called_with("test-ai", target="test-ai")


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class TestMemoryContext:
    @pytest.mark.asyncio
    async def test_context_requires_session_key(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get("/v1/memory/context")
                data = await resp.json()
                assert data["available"] is False
                assert "session_key" in data["reason"]

    @pytest.mark.asyncio
    async def test_context_resolves_session(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        # _resolve_session calls manager.get_or_create
        manager.get_or_create.return_value = MagicMock()
        manager.get_session_context.return_value = {
            "summary": "Discussed memory introspection.",
            "representation": "The user is building a memory observability surface.",
            "card": "facts go here",
            "recent_messages": [{"role": "user", "content": "hi"}],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get(
                    "/v1/memory/context?session_key=portal:agent:aivex:abc&peer=user"
                )
                data = await resp.json()
                assert data["available"] is True
                assert data["session_key"] == "portal:agent:aivex:abc"
                assert "Discussed" in data["summary"]
                assert len(data["recent_messages"]) == 1


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestMemorySearch:
    @pytest.mark.asyncio
    async def test_search_missing_query(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/v1/memory/search", json={"peer": "user"})
            assert resp.status == 400
            data = await resp.json()
            assert "query" in data["error"]["code"].lower() or "required" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_search_invalid_json(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(
                "/v1/memory/search",
                data="not-json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_search_with_session(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        manager.get_or_create.return_value = MagicMock()
        manager.search_context.return_value = "matched excerpts"
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.post(
                    "/v1/memory/search",
                    json={
                        "query": "what does the user do for work",
                        "peer": "user",
                        "session_key": "portal:agent:aivex:abc",
                        "max_tokens": 1500,
                    },
                )
                data = await resp.json()
                assert data["available"] is True
                assert data["scope"] == "session"
                assert data["result"] == "matched excerpts"
                manager.search_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_peer_scope_when_no_session(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        manager._fetch_peer_context.return_value = {
            "representation": "The user is Justin.",
            "card": ["founder", "Idaho"],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.post(
                    "/v1/memory/search",
                    json={"query": "who is the user", "peer": "user"},
                )
                data = await resp.json()
                assert data["available"] is True
                assert data["scope"] == "peer"
                assert "Justin" in data["result"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestMemoryStats:
    @pytest.mark.asyncio
    async def test_stats_no_provider(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value=None):
                resp = await cli.get("/v1/memory/stats")
                data = await resp.json()
                assert data["available"] is False

    @pytest.mark.asyncio
    async def test_stats_honcho(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        manager._fetch_peer_context.side_effect = [
            {"representation": "user repr", "card": ["a", "b", "c"]},
            {"representation": "ai repr", "card": ["x"]},
        ]
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get("/v1/memory/stats")
                data = await resp.json()
                assert data["available"] is True
                assert data["user_card_size"] == 3
                assert data["ai_card_size"] == 1
                # legacy fields are explicit null, not 0
                assert data["factCount"] is None
                assert data["notebookEntryCount"] is None


# ---------------------------------------------------------------------------
# Compatibility wrappers
# ---------------------------------------------------------------------------


class TestMemoryCompatibility:
    @pytest.mark.asyncio
    async def test_facts_returns_empty_with_notice(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"):
                resp = await cli.get("/v1/memory/facts")
                assert resp.status == 200
                data = await resp.json()
                assert data["facts"] == []
                assert data["total"] == 0
                assert "notice" in data
                assert data["provider"] == "honcho"

    @pytest.mark.asyncio
    async def test_entities_returns_empty(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/v1/memory/entities")
            assert resp.status == 200
            data = await resp.json()
            assert data["entities"] == []
            assert "notice" in data

    @pytest.mark.asyncio
    async def test_notebook_returns_empty(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/v1/memory/notebook")
            data = await resp.json()
            assert data["entries"] == []
            assert data["charLimit"] == 0
            assert "notice" in data

    @pytest.mark.asyncio
    async def test_user_profile_bridges_to_profile(self, adapter):
        app = _create_app(adapter)
        cfg = _fake_cfg()
        manager = MagicMock()
        manager._fetch_peer_context.return_value = {
            "representation": "Justin runs Aivex.",
            "card": ["founder", "uses tailscale", "in Idaho"],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch(f"{_MEM_MOD}._load_active_provider_name", return_value="honcho"), \
                 patch(f"{_MEM_MOD}._load_honcho_components", return_value=(cfg, manager)):
                resp = await cli.get("/v1/memory/user-profile")
                data = await resp.json()
                assert len(data["entries"]) == 3
                assert data["entries"][0]["content"] == "founder"
                assert data["charLimit"] >= data["charCount"] >= 0
                assert data["provider"] == "honcho"
