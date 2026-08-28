"""Sealed retain/recall semantics for the Hindsight memory integration.

This module intentionally contains only pure helpers.  Keeping request shaping,
result merging, and budget enforcement here makes the provider's network and
lifecycle code easier to audit and lets tests exercise the contract without a
running Hindsight service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

MAX_CONTENT_CHARACTERS_PER_PART = 190_000
MAX_GATEWAY_BODY_BYTES = 2 * 1024 * 1024
_GATEWAY_ENVELOPE_RESERVE_BYTES = 64 * 1024
AUTOMATIC_RECALL_MODE = "automatic"
LEGACY_OBSERVATIONS_MODE = "legacy_observations"
FULL_PROVENANCE_MODE = "full_provenance"
SERVER_MIXED_MODE = "server_mixed"
RECALL_MODES = {
    AUTOMATIC_RECALL_MODE,
    LEGACY_OBSERVATIONS_MODE,
    FULL_PROVENANCE_MODE,
    SERVER_MIXED_MODE,
}


@dataclass(frozen=True)
class RecallBundle:
    """Merged recall results plus any explicitly requested source bodies."""

    results: tuple[Any, ...]
    source_facts: Mapping[str, Any]


def load_deployment_profiles() -> tuple[dict[str, Any], ...]:
    """Load the deployment matrix shipped beside the plugin.

    The file contains no credentials, only the profile-to-bank boundary.  It is
    deliberately data rather than code so deployment tooling can consume the
    same source of truth as the integration tests.
    """

    path = Path(__file__).with_name("deployment-profiles.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("Hindsight deployment profile manifest is malformed")
    return tuple(dict(entry) for entry in profiles)


@lru_cache(maxsize=1)
def deployment_profile_map() -> dict[str, dict[str, Any]]:
    return {str(entry["profile"]): entry for entry in load_deployment_profiles()}


def resolve_profile_scope(profile: str, bank_id: str, configured_scope: str = "") -> str:
    """Resolve the deployment scope used for retain provenance tags."""

    explicit = str(configured_scope or "").strip().lower()
    if explicit:
        if explicit not in {"personal", "business", "universal"}:
            raise ValueError("integration_scope must be 'personal', 'business', or 'universal'")
        return explicit

    manifest_entry = deployment_profile_map().get(profile)
    if manifest_entry and manifest_entry.get("bank_id") == bank_id:
        return str(manifest_entry["scope"])
    if bank_id == "personal-justin-universal":
        return "universal"
    if bank_id.startswith("personal-"):
        return "personal"
    if bank_id.startswith(("aivex-", "client-")):
        return "business"
    # Generic Hermes installations may use arbitrary bank names.  Preserve a
    # deterministic boundary while making the local mission's named banks exact.
    return "personal"


def sealed_conversation_tags(*, profile: str, scope: str, session_id: str) -> list[str]:
    """Return the exact four-tag conversational provenance envelope."""

    normalized_profile = str(profile or "default").strip() or "default"
    normalized_session = str(session_id or "unspecified").strip() or "unspecified"
    if scope not in {"personal", "business", "universal"}:
        raise ValueError("scope must be 'personal', 'business', or 'universal'")
    return [
        "runtime:hermes",
        f"profile:{normalized_profile}",
        f"scope:{scope}",
        f"session:{normalized_session}",
    ]


def split_text_utf8_safe(text: str, max_characters: int = MAX_CONTENT_CHARACTERS_PER_PART) -> list[str]:
    """Split text at Python character boundaries, preferring whitespace.

    Python string slices never bisect a UTF-8 byte sequence.  The soft boundary
    search avoids cutting a word when practical while the hard bound remains
    exact for every emitted part.
    """

    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    if not text:
        return [""]

    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        hard_end = min(len(text), cursor + max_characters)
        end = hard_end
        if hard_end < len(text):
            # Search only the final 4 KiB so splitting remains linear for large
            # turns while still finding a natural boundary in normal prose.
            floor = max(cursor + 1, hard_end - 4096)
            newline = text.rfind("\n", floor, hard_end)
            space = text.rfind(" ", floor, hard_end)
            candidate = max(newline, space)
            if candidate >= floor:
                end = candidate + 1
        piece = text[cursor:end]
        encoded_limit = MAX_GATEWAY_BODY_BYTES - _GATEWAY_ENVELOPE_RESERVE_BYTES
        if len(json.dumps(piece, ensure_ascii=True).encode("utf-8")) > encoded_limit:
            # The generated SDK may ASCII-escape non-BMP characters.  Binary
            # search the largest safe character boundary so even an all-emoji
            # turn remains below the 2 MiB gateway limit after envelope fields.
            low, high = 1, len(piece)
            while low < high:
                midpoint = (low + high + 1) // 2
                size = len(json.dumps(piece[:midpoint], ensure_ascii=True).encode("utf-8"))
                if size <= encoded_limit:
                    low = midpoint
                else:
                    high = midpoint - 1
            end = cursor + low
            piece = text[cursor:end]
        parts.append(piece)
        cursor = end
    return parts


def _result_attr(result: Any, key: str, default: Any = None) -> Any:
    if isinstance(result, Mapping):
        return result.get(key, default)
    return getattr(result, key, default)


def merge_recall_results(
    observations: Sequence[Any],
    raw_facts: Sequence[Any],
) -> tuple[Any, ...]:
    """Merge observation-first and remove source-covered/duplicate raw facts."""

    covered_raw_ids: set[str] = set()
    seen_result_ids: set[str] = set()
    merged: list[Any] = []

    for result in observations:
        result_id = str(_result_attr(result, "id", "") or "")
        if result_id and result_id in seen_result_ids:
            continue
        if result_id:
            seen_result_ids.add(result_id)
        for source_id in _result_attr(result, "source_fact_ids", None) or ():
            covered_raw_ids.add(str(source_id))
        merged.append(result)

    for result in raw_facts:
        result_id = str(_result_attr(result, "id", "") or "")
        if result_id and (result_id in covered_raw_ids or result_id in seen_result_ids):
            continue
        if result_id:
            seen_result_ids.add(result_id)
        merged.append(result)
    return tuple(merged)


@lru_cache(maxsize=1)
def _token_encoding():
    """Return Hindsight's cl100k token counter when the optional extra is present."""

    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_render_tokens(text: str) -> int:
    """Count rendered tokens exactly when possible, conservatively otherwise."""

    if not text:
        return 0
    encoding = _token_encoding()
    if encoding is not None:
        return len(encoding.encode(text, disallowed_special=()))
    # One token cannot encode less than one byte, so byte length is a safe
    # upper bound when the optional tokenizer cannot be imported.
    return len(text.encode("utf-8"))


def _truncate_to_token_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0 or not text:
        return ""
    encoding = _token_encoding()
    if encoding is not None:
        tokens = encoding.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text
        return encoding.decode(tokens[:max_tokens])

    raw = text.encode("utf-8")[:max_tokens]
    return raw.decode("utf-8", errors="ignore")


def _source_ids(result: Any) -> tuple[str, ...]:
    return tuple(str(value) for value in (_result_attr(result, "source_fact_ids", None) or ()))


def _render_result(
    index: int,
    result: Any,
    *,
    source_facts: Mapping[str, Any],
    include_source_content: bool,
) -> str:
    text = str(_result_attr(result, "text", "") or "").strip()
    line = f"{index}. {text}"
    source_ids = _source_ids(result)
    if source_ids:
        line += "\n   sources: " + ", ".join(source_ids)
        if include_source_content:
            for source_id in source_ids:
                source = source_facts.get(source_id)
                if source is None:
                    continue
                source_text = str(_result_attr(source, "text", "") or "").strip()
                if source_text:
                    line += f"\n   - [{source_id}] {source_text}"
    return line


def render_recall_bundle(
    bundle: RecallBundle,
    *,
    max_tokens: int,
    include_source_content: bool = False,
) -> str:
    """Render ranked results without crossing the single configured budget."""

    if max_tokens < 1:
        return ""
    rendered: list[str] = []
    for result in bundle.results:
        candidate = _render_result(
            len(rendered) + 1,
            result,
            source_facts=bundle.source_facts,
            include_source_content=include_source_content,
        )
        joined = "\n".join((*rendered, candidate))
        if count_render_tokens(joined) <= max_tokens:
            rendered.append(candidate)
            continue
        if not rendered:
            truncated = _truncate_to_token_budget(candidate, max_tokens)
            if truncated:
                rendered.append(truncated)
        break
    return "\n".join(rendered)


def response_results(response: Any) -> tuple[Any, ...]:
    return tuple(getattr(response, "results", None) or ())


def response_source_facts(response: Any) -> Mapping[str, Any]:
    value = getattr(response, "source_facts", None)
    return value if isinstance(value, Mapping) else {}


def bundle_single_response(response: Any) -> RecallBundle:
    return RecallBundle(response_results(response), response_source_facts(response))


def bundle_two_lane(observation_response: Any, raw_response: Any) -> RecallBundle:
    return RecallBundle(
        merge_recall_results(
            response_results(observation_response),
            response_results(raw_response),
        ),
        response_source_facts(observation_response),
    )


def immutable_json_sha256(value: Any) -> str:
    """Stable content hash used in outbox records and deployment evidence."""

    import hashlib

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
