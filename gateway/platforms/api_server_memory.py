"""
Read-only memory introspection helpers for the API server adapter.

Exposes the active memory provider's state to authenticated callers (admin
dashboards, the Aivex portal, ops surfaces) without going through the agent
chat loop. Designed to be safe to call when no provider is configured: every
function returns a structured "available: false" envelope rather than raising.

Honcho is the only provider with rich introspection today. When the active
provider is something else (or none), the endpoints degrade gracefully so
clients can render an "unavailable" UI instead of breaking.

All call sites in api_server.py wrap these results in `web.json_response`
after running the standard `_check_auth(request)` guard.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def _load_active_provider_name() -> Optional[str]:
    """Read `memory.provider` from config.yaml. Returns None if unset."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
    except Exception as e:
        logger.debug("memory introspection: load_config failed: %s", e)
        return None

    memory_block = cfg.get("memory") if isinstance(cfg, dict) else None
    if not isinstance(memory_block, dict):
        return None
    name = memory_block.get("provider")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _load_honcho_components() -> Tuple[Any, Any]:
    """Resolve a Honcho config + session manager pair.

    Returns (config, manager). Either may be None on failure. The manager is
    a fresh `HonchoSessionManager` (NOT the live one used by chat agents) so
    we never mutate the caching state of any in-flight conversation.
    """
    try:
        from plugins.memory.honcho.client import HonchoClientConfig, get_honcho_client
        from plugins.memory.honcho.session import HonchoSessionManager
    except ImportError:
        logger.debug("memory introspection: honcho package not installed")
        return None, None

    try:
        cfg = HonchoClientConfig.from_global_config()
    except Exception as e:
        logger.debug("memory introspection: HonchoClientConfig.from_global_config failed: %s", e)
        return None, None

    if not cfg.enabled or not (cfg.api_key or cfg.base_url):
        return cfg, None

    try:
        client = get_honcho_client(cfg)
    except Exception as e:
        logger.debug("memory introspection: honcho client init failed: %s", e)
        return cfg, None

    try:
        manager = HonchoSessionManager(
            honcho=client,
            context_tokens=cfg.context_tokens,
            config=cfg,
        )
    except Exception as e:
        logger.debug("memory introspection: HonchoSessionManager construction failed: %s", e)
        return cfg, None

    return cfg, manager


def _resolve_session(manager: Any, session_key: str) -> Optional[Any]:
    """Hydrate the manager's local cache for `session_key`.

    Honcho session objects are lazy on the SDK side — calling `get_or_create`
    for a key the user already wrote messages to is a cache lookup plus a
    cheap server-side peer-config sync. For a key that's never existed it
    creates an empty session, which is benign for read-only introspection
    (Honcho self-prunes stale empty sessions). Returns the cached session or
    None on failure.
    """
    if not session_key:
        return None
    try:
        return manager.get_or_create(session_key)
    except Exception as e:
        logger.debug("memory introspection: get_or_create(%r) failed: %s", session_key, e)
        return None


# ---------------------------------------------------------------------------
# Public-shape helpers (returned verbatim as JSON bodies)
# ---------------------------------------------------------------------------


def _unavailable(reason: str, *, provider: Optional[str] = None) -> Dict[str, Any]:
    """Standard envelope for "memory is not available right now"."""
    return {
        "available": False,
        "provider": provider,
        "reason": reason,
    }


def _peer_summary(cfg: Any) -> Dict[str, Any]:
    """Surface the user/ai peer ids the provider is configured to use."""
    return {
        "user": getattr(cfg, "peer_name", None),
        "ai": getattr(cfg, "ai_peer", None),
    }


# ---------------------------------------------------------------------------
# Endpoint implementations
# ---------------------------------------------------------------------------


def get_status() -> Dict[str, Any]:
    """`GET /v1/memory/status` body."""
    name = _load_active_provider_name()
    if not name:
        return _unavailable("no memory provider configured in config.yaml")

    if name != "honcho":
        return {
            "available": False,
            "provider": name,
            "reason": (
                f"introspection helpers currently only know how to read the "
                f"'honcho' provider; active provider is '{name}'"
            ),
        }

    cfg, manager = _load_honcho_components()
    if cfg is None:
        return _unavailable("honcho package not installed", provider=name)
    if not cfg.enabled:
        return {
            "available": False,
            "provider": name,
            "reason": "honcho is configured but disabled (memory.enabled=false)",
        }
    if manager is None:
        return {
            "available": False,
            "provider": name,
            "reason": "honcho session manager could not be constructed; check api_key/base_url",
            "configured": bool(cfg.api_key or cfg.base_url),
        }

    return {
        "available": True,
        "provider": "honcho",
        "configured": bool(cfg.api_key or cfg.base_url),
        "enabled": bool(cfg.enabled),
        "workspace": getattr(cfg, "workspace_id", None),
        "host": getattr(cfg, "host", None),
        "environment": getattr(cfg, "environment", None),
        "peers": _peer_summary(cfg),
        "recall_mode": getattr(cfg, "recall_mode", None),
        "session_strategy": getattr(cfg, "session_strategy", None),
        "context_tokens": getattr(cfg, "context_tokens", None),
        "dialectic": {
            "depth": getattr(cfg, "dialectic_depth", None),
            "reasoning_level": getattr(cfg, "dialectic_reasoning_level", None),
            "dynamic": getattr(cfg, "dialectic_dynamic", None),
        },
    }


def get_profile(peer: str = "user") -> Dict[str, Any]:
    """`GET /v1/memory/profile?peer=user|ai` body.

    Returns the peer card + free-form representation pulled directly from the
    peer object — no session needed. This is the cheapest signal that Honcho
    has actually accumulated information about the requested peer.
    """
    name = _load_active_provider_name()
    if name != "honcho":
        return _unavailable(
            f"profile introspection requires honcho provider; active is {name!r}",
            provider=name,
        )

    cfg, manager = _load_honcho_components()
    if cfg is None or manager is None:
        return _unavailable("honcho not available", provider=name)

    peer_alias = (peer or "user").strip().lower()
    if peer_alias == "ai":
        peer_id = getattr(cfg, "ai_peer", None) or "hermes"
    elif peer_alias == "user":
        peer_id = getattr(cfg, "peer_name", None) or "user"
    else:
        peer_id = peer.strip()

    try:
        ctx = manager._fetch_peer_context(peer_id, target=peer_id)
    except Exception as e:
        logger.debug("memory introspection: _fetch_peer_context(%r) failed: %s", peer_id, e)
        return {
            "available": False,
            "provider": "honcho",
            "peer": peer_alias,
            "peer_id": peer_id,
            "reason": f"honcho peer lookup failed: {e}",
        }

    representation = ctx.get("representation") or ""
    card_facts: List[str] = ctx.get("card") or []

    return {
        "available": True,
        "provider": "honcho",
        "peer": peer_alias,
        "peer_id": peer_id,
        "representation": representation,
        "card": card_facts,
    }


def get_context(session_key: str = "", peer: str = "user") -> Dict[str, Any]:
    """`GET /v1/memory/context?session_key=...&peer=...` body."""
    name = _load_active_provider_name()
    if name != "honcho":
        return _unavailable(
            f"context introspection requires honcho provider; active is {name!r}",
            provider=name,
        )

    cfg, manager = _load_honcho_components()
    if cfg is None or manager is None:
        return _unavailable("honcho not available", provider=name)

    if not session_key:
        return {
            "available": False,
            "provider": "honcho",
            "reason": "session_key is required for /v1/memory/context",
        }

    if _resolve_session(manager, session_key) is None:
        return {
            "available": False,
            "provider": "honcho",
            "session_key": session_key,
            "reason": "could not resolve session from key",
        }

    try:
        ctx = manager.get_session_context(session_key, peer=peer or "user")
    except Exception as e:
        logger.debug("memory introspection: get_session_context failed: %s", e)
        return {
            "available": False,
            "provider": "honcho",
            "session_key": session_key,
            "reason": f"honcho session context failed: {e}",
        }

    return {
        "available": True,
        "provider": "honcho",
        "session_key": session_key,
        "peer": peer or "user",
        "summary": ctx.get("summary", ""),
        "representation": ctx.get("representation", ""),
        "card": ctx.get("card", ""),
        "recent_messages": ctx.get("recent_messages", []),
    }


def search_memory(
    query: str,
    *,
    peer: str = "user",
    max_tokens: int = 800,
    session_key: str = "",
) -> Dict[str, Any]:
    """`POST /v1/memory/search` body."""
    if not query or not query.strip():
        return {"available": False, "provider": None, "reason": "query is required"}

    name = _load_active_provider_name()
    if name != "honcho":
        return _unavailable(
            f"search requires honcho provider; active is {name!r}",
            provider=name,
        )

    cfg, manager = _load_honcho_components()
    if cfg is None or manager is None:
        return _unavailable("honcho not available", provider=name)

    safe_max_tokens = max(50, min(int(max_tokens or 800), 4000))

    if session_key:
        if _resolve_session(manager, session_key) is None:
            return {
                "available": False,
                "provider": "honcho",
                "session_key": session_key,
                "reason": "could not resolve session from key",
            }
        try:
            result = manager.search_context(
                session_key, query.strip(),
                max_tokens=safe_max_tokens, peer=peer or "user",
            )
        except Exception as e:
            logger.debug("memory introspection: search_context failed: %s", e)
            return {
                "available": False,
                "provider": "honcho",
                "session_key": session_key,
                "reason": f"honcho search failed: {e}",
            }
        return {
            "available": True,
            "provider": "honcho",
            "scope": "session",
            "session_key": session_key,
            "peer": peer or "user",
            "query": query.strip(),
            "max_tokens": safe_max_tokens,
            "result": result or "",
        }

    # No session key → fall back to peer-level context lookup so the caller
    # still gets *some* answer for "what does Honcho know overall?". This is
    # implemented in terms of _fetch_peer_context with a search_query.
    peer_alias = (peer or "user").strip().lower()
    if peer_alias == "ai":
        peer_id = getattr(cfg, "ai_peer", None) or "hermes"
    elif peer_alias == "user":
        peer_id = getattr(cfg, "peer_name", None) or "user"
    else:
        peer_id = peer.strip()

    try:
        ctx = manager._fetch_peer_context(peer_id, search_query=query.strip(), target=peer_id)
    except Exception as e:
        logger.debug("memory introspection: peer-level search failed: %s", e)
        return {
            "available": False,
            "provider": "honcho",
            "reason": f"honcho peer-level search failed: {e}",
        }

    parts: List[str] = []
    if ctx.get("representation"):
        parts.append(ctx["representation"])
    card = ctx.get("card") or []
    if card:
        parts.append("\n".join(f"- {fact}" for fact in card))

    return {
        "available": True,
        "provider": "honcho",
        "scope": "peer",
        "peer": peer_alias,
        "peer_id": peer_id,
        "query": query.strip(),
        "max_tokens": safe_max_tokens,
        "result": "\n\n".join(parts),
    }


def get_stats(session_key: str = "") -> Dict[str, Any]:
    """`GET /v1/memory/stats` body.

    Returns aggregate counts where Honcho can supply them. The legacy SQLite
    schema (factCount/entityCount/notebook) is intentionally NOT faked —
    callers should treat any count we can't supply as "unknown" rather than
    "zero". Old fields are still emitted with sentinel `null` so older portal
    UIs don't crash.
    """
    name = _load_active_provider_name()
    if not name:
        return _unavailable("no memory provider configured")
    if name != "honcho":
        return _unavailable(
            f"stats introspection requires honcho provider; active is {name!r}",
            provider=name,
        )

    cfg, manager = _load_honcho_components()
    if cfg is None or manager is None:
        return _unavailable("honcho not available", provider=name)

    user_card: List[str] = []
    ai_card: List[str] = []
    try:
        user_id = getattr(cfg, "peer_name", None) or "user"
        user_ctx = manager._fetch_peer_context(user_id, target=user_id)
        user_card = user_ctx.get("card") or []
    except Exception as e:
        logger.debug("memory introspection: stats user card lookup failed: %s", e)

    try:
        ai_id = getattr(cfg, "ai_peer", None) or "hermes"
        ai_ctx = manager._fetch_peer_context(ai_id, target=ai_id)
        ai_card = ai_ctx.get("card") or []
    except Exception as e:
        logger.debug("memory introspection: stats ai card lookup failed: %s", e)

    session_summary: Dict[str, Any] = {}
    if session_key:
        if _resolve_session(manager, session_key) is not None:
            try:
                ctx = manager.get_session_context(session_key, peer="user")
                session_summary = {
                    "session_key": session_key,
                    "has_summary": bool(ctx.get("summary")),
                    "recent_messages": len(ctx.get("recent_messages") or []),
                }
            except Exception as e:
                logger.debug("memory introspection: stats session context failed: %s", e)
                session_summary = {"session_key": session_key, "error": str(e)}

    return {
        "available": True,
        "provider": "honcho",
        "workspace": getattr(cfg, "workspace_id", None),
        "peers": _peer_summary(cfg),
        "user_card_size": len(user_card),
        "ai_card_size": len(ai_card),
        "session": session_summary or None,
        # Legacy compatibility fields — explicit null so the old SQLite UI
        # can render an "unknown / not applicable" state instead of
        # confidently showing zero.
        "factCount": None,
        "entityCount": None,
        "categories": [],
        "notebookEntryCount": None,
        "notebookCharCount": None,
        "notebookCharLimit": None,
        "userProfileEntryCount": None,
        "userProfileCharCount": None,
        "userProfileCharLimit": None,
    }


# ---------------------------------------------------------------------------
# Compatibility wrappers for the original SQLite-shaped routes
# ---------------------------------------------------------------------------


def facts_compat() -> Dict[str, Any]:
    """`GET /v1/memory/facts` graceful empty body.

    The original endpoint returned a curated list of fact rows from a local
    SQLite store. Honcho doesn't model memory that way, so we return an
    empty list plus a `notice` field that the portal UI can surface.
    """
    return {
        "facts": [],
        "total": 0,
        "notice": (
            "Memory now lives behind Honcho; the facts/entities/notebook "
            "schema is no longer populated. Use /v1/memory/profile, "
            "/v1/memory/context, or /v1/memory/search for the current "
            "operator surface."
        ),
        "provider": _load_active_provider_name(),
    }


def entities_compat() -> Dict[str, Any]:
    return {
        "entities": [],
        "notice": "Honcho does not maintain the legacy entities table; see /v1/memory/profile.",
        "provider": _load_active_provider_name(),
    }


def notebook_compat() -> Dict[str, Any]:
    return {
        "entries": [],
        "charCount": 0,
        "charLimit": 0,
        "notice": "Honcho does not maintain notebook entries; see /v1/memory/context.",
        "provider": _load_active_provider_name(),
    }


def user_profile_compat() -> Dict[str, Any]:
    """Bridge the legacy notebook-shaped /v1/memory/user-profile to the new profile call."""
    name = _load_active_provider_name()
    if name != "honcho":
        return {
            "entries": [],
            "charCount": 0,
            "charLimit": 0,
            "notice": "Memory provider is not honcho; user-profile compatibility unavailable.",
            "provider": name,
        }

    profile = get_profile(peer="user")
    if not profile.get("available"):
        return {
            "entries": [],
            "charCount": 0,
            "charLimit": 0,
            "notice": profile.get("reason", "honcho profile unavailable"),
            "provider": "honcho",
        }
    facts = profile.get("card") or []
    entries = [{"index": i, "content": fact} for i, fact in enumerate(facts)]
    char_count = sum(len(f) for f in facts)
    return {
        "entries": entries,
        "charCount": char_count,
        # No fixed limit in honcho — surface the same number twice so the
        # portal's "% used" math degrades gracefully to 100% rather than
        # dividing by zero.
        "charLimit": max(char_count, 1),
        "representation": profile.get("representation", ""),
        "notice": "Compatibility view of /v1/memory/profile?peer=user",
        "provider": "honcho",
    }
