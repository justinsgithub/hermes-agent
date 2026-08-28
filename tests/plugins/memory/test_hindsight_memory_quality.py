"""Contract tests for Hermes' Hindsight v0.8.6 memory-quality upgrade."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import stat
import tomllib
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from plugins.memory.hindsight import (
    FULL_PROVENANCE_MODE,
    LEGACY_OBSERVATIONS_MODE,
    SERVER_MIXED_MODE,
    HindsightMemoryProvider,
    _append_capability_cache,
    _append_capability_lock,
    _normalize_observation_scopes,
)
from plugins.memory.hindsight.contract import (
    MAX_CONTENT_CHARACTERS_PER_PART,
    MAX_GATEWAY_BODY_BYTES,
    RecallBundle,
    count_render_tokens,
    immutable_json_sha256,
    load_deployment_profiles,
    merge_recall_results,
    render_recall_bundle,
    resolve_profile_scope,
    sealed_conversation_tags,
    split_text_utf8_safe,
)
from plugins.memory.hindsight.outbox import DurableRetainOutbox

REPO_ROOT = Path(__file__).resolve().parents[3]


def _response(results=(), source_facts=None):
    return SimpleNamespace(results=list(results), source_facts=source_facts or {})


def _result(result_id: str, text: str, source_fact_ids=()):
    return SimpleNamespace(
        id=result_id,
        text=text,
        source_fact_ids=list(source_fact_ids),
    )


def _client(*, retain_side_effect=None, recall_side_effect=None):
    client = SimpleNamespace()
    client.aretain_batch = AsyncMock(side_effect=retain_side_effect)
    client.arecall = AsyncMock(
        side_effect=recall_side_effect,
        return_value=_response(),
    )
    client.areflect = AsyncMock(return_value=SimpleNamespace(text="reflection"))
    client.aclose = AsyncMock()
    return client


def _clear_append_capability_cache() -> None:
    with _append_capability_lock:
        _append_capability_cache.clear()


def _make_provider(
    home: Path,
    monkeypatch,
    *,
    client=None,
    session_id: str = "session-quality",
    **overrides,
) -> HindsightMemoryProvider:
    config = {
        "mode": "cloud",
        "apiKey": "test-key",
        "api_url": "http://hindsight.invalid",
        "bank_id": "personal-justin-core",
        "integration_profile": "tyler",
        "memory_mode": "hybrid",
        "recall_max_tokens": 100,
    }
    config.update(overrides)
    config_path = home / "hindsight" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr("plugins.memory.hindsight.get_hermes_home", lambda: home)
    monkeypatch.setattr(
        "plugins.memory.hindsight._fetch_hindsight_api_version",
        lambda *args, **kwargs: "0.8.6",
    )
    _clear_append_capability_cache()
    provider = HindsightMemoryProvider()
    provider.initialize(
        session_id=session_id,
        hermes_home=str(home),
        platform="cli",
        agent_identity="tyler",
    )
    provider._client = client or _client()
    return provider


def _outbox_record(*, turn_index: int = 1, part_count: int = 1, ready: bool = True):
    turn_id = f"turn-{turn_index}"
    parts = []
    for part_index in range(part_count):
        operation_id = f"00000000-0000-4000-8000-{turn_index:06d}{part_index:02d}"
        request = {
            "bank_id": "bank",
            "items": [{"content": f"turn {turn_index}, part {part_index}"}],
            "document_id": "document",
            "retain_async": True,
            "operation_id": operation_id,
        }
        parts.append(
            {
                "part_index": part_index,
                "part_id": f"part-{turn_index}-{part_index}",
                "operation_id": operation_id,
                "payload_sha256": "fixture",
                "request": request,
                "delivery": {"attempts": 0, "acked": False, "poisoned": False},
            }
        )
    return {
        "turn_id": turn_id,
        "turn_index": turn_index,
        "session_id": "session",
        "profile": "tyler",
        "scope": "personal",
        "bank_id": "bank",
        "document_id": "document",
        "document_uuid": "document",
        "ready": ready,
        "parts": parts,
    }


class TestRequestContract:
    def test_shared_scope_is_literal_and_list_lookalikes_fail(self):
        assert _normalize_observation_scopes("shared") == "shared"
        with pytest.raises(ValueError, match="literal string"):
            _normalize_observation_scopes(["shared"])
        with pytest.raises(ValueError, match="literal string"):
            _normalize_observation_scopes([["shared"]])
        with pytest.raises(ValueError, match="literal string"):
            _normalize_observation_scopes('["shared"]')

    def test_sealed_conversation_tags_are_exact_and_ordered(self):
        assert sealed_conversation_tags(
            profile="tyler",
            scope="personal",
            session_id="session-123",
        ) == [
            "runtime:hermes",
            "profile:tyler",
            "scope:personal",
            "session:session-123",
        ]

    def test_client_dependency_and_lock_are_exact_086(self):
        project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert project["project"]["optional-dependencies"]["hindsight"][0] == (
            "hindsight-client==0.8.6"
        )
        assert "memory/hindsight/deployment-profiles.json" in (
            project["tool"]["setuptools"]["package-data"]["plugins"]
        )

        lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
        versions = {
            package["version"]
            for package in lock["package"]
            if package["name"] == "hindsight-client"
        }
        assert versions == {"0.8.6"}

        plugin_yaml = (
            REPO_ROOT / "plugins" / "memory" / "hindsight" / "plugin.yaml"
        ).read_text(encoding="utf-8")
        lazy_deps = (REPO_ROOT / "tools" / "lazy_deps.py").read_text(encoding="utf-8")
        assert "hindsight-client==0.8.6" in plugin_yaml
        assert "hindsight-client==0.8.6" in lazy_deps

    def test_installed_086_sdk_exposes_every_native_request_field(self):
        try:
            installed = metadata.version("hindsight-client")
        except metadata.PackageNotFoundError:
            pytest.skip("hindsight optional extra is not installed")
        assert installed == "0.8.6"

        from hindsight_client import Hindsight

        retain = inspect.signature(Hindsight.aretain_batch).parameters
        recall = inspect.signature(Hindsight.arecall).parameters
        assert {"document_id", "retain_async", "operation_id"} <= set(retain)
        assert {
            "types",
            "max_tokens",
            "include_entities",
            "include_source_facts",
            "max_source_facts_tokens",
            "tags",
            "tags_match",
            "tag_groups",
            "prefer_observations",
            "min_scores",
        } <= set(recall)

    def test_utf8_split_preserves_content_and_both_hard_caps(self):
        text = ('😀"\\\n' * 55_000) + ("tail" * 5_000)
        parts = split_text_utf8_safe(text)
        assert len(parts) > 1
        assert "".join(parts) == text
        assert all(len(part) <= MAX_CONTENT_CHARACTERS_PER_PART for part in parts)
        assert all(part.encode("utf-8").decode("utf-8") == part for part in parts)

        for part in parts:
            request = {
                "bank_id": "personal-justin-core",
                "items": [
                    {
                        "content": part,
                        "metadata": {"turn_id": "t", "part_id": "p"},
                        "tags": [
                            "runtime:hermes",
                            "profile:tyler",
                            "scope:personal",
                            "session:s",
                        ],
                        "observation_scopes": "shared",
                    }
                ],
                "document_id": "d",
                "retain_async": True,
                "operation_id": "00000000-0000-4000-8000-000000000001",
            }
            body = json.dumps(request, ensure_ascii=True).encode("utf-8")
            assert len(body) < MAX_GATEWAY_BODY_BYTES

    def test_manifest_covers_exact_two_universal_profiles(self):
        manifest = json.loads(
            (
                REPO_ROOT
                / "plugins"
                / "memory"
                / "hindsight"
                / "deployment-profiles.json"
            ).read_text(encoding="utf-8")
        )
        assert manifest["required_config"] == {
            "auto_retain": True,
            "retain_async": True,
            "retain_every_n_turns": 1,
            "observation_scopes": "shared",
        }
        assert manifest["limits"] == {
            "maximum_content_characters_per_part": 190_000,
            "maximum_gateway_body_bytes": 2_097_152,
            "minimum_recall_max_tokens": 2,
        }
        profiles = load_deployment_profiles()
        assert {
            entry["profile"]: (
                entry["scope"],
                entry["bank_id"],
                entry["credential"],
            )
            for entry in profiles
        } == {
            "default": ("universal", "personal-justin-universal", "hermes-default"),
            "tyler": ("universal", "personal-justin-universal", "hermes-tyler"),
        }
        assert len({entry["profile"] for entry in profiles}) == 2
        for entry in profiles:
            assert resolve_profile_scope(entry["profile"], entry["bank_id"]) == entry["scope"]
            assert sealed_conversation_tags(
                profile=entry["profile"],
                scope=entry["scope"],
                session_id="profile-probe",
            ) == [
                "runtime:hermes",
                f"profile:{entry['profile']}",
                f"scope:{entry['scope']}",
                "session:profile-probe",
            ]


class TestRecallContract:
    def test_automatic_recall_is_concurrent_bounded_and_source_deduplicated(
        self,
        tmp_path,
        monkeypatch,
    ):
        started: set[str] = set()
        both_started = None

        async def recall(**kwargs):
            nonlocal both_started
            if both_started is None:
                both_started = asyncio.Event()
            lane = kwargs["types"][0]
            started.add(lane)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.25)
            if kwargs["types"] == ["observation"]:
                return _response(
                    [
                        _result("observation-1", "Observed answer", ["raw-covered"]),
                        _result("duplicate", "Observed duplicate"),
                    ],
                    {"raw-covered": _result("raw-covered", "Source body")},
                )
            return _response(
                [
                    _result("raw-covered", "Covered raw fact"),
                    _result("duplicate", "Duplicate raw fact"),
                    _result("raw-keep", "Independent raw fact"),
                ]
            )

        client = _client(recall_side_effect=recall)
        provider = _make_provider(
            tmp_path,
            monkeypatch,
            client=client,
            recall_max_tokens=100,
        )
        bundle = provider._recall_bundle("remember this")

        assert [result.id for result in bundle.results] == [
            "observation-1",
            "duplicate",
            "raw-keep",
        ]
        assert started == {"observation", "world"}
        observation, raw = [call.kwargs for call in client.arecall.call_args_list]
        assert observation == {
            "bank_id": "personal-justin-core",
            "query": "remember this",
            "budget": "mid",
            "max_tokens": 55,
            "types": ["observation"],
            "tags": [],
            "tags_match": "exact",
            "include_entities": False,
            "include_source_facts": True,
            "max_source_facts_tokens": 1,
        }
        assert raw == {
            "bank_id": "personal-justin-core",
            "query": "remember this",
            "budget": "mid",
            "max_tokens": 35,
            "types": ["world", "experience"],
            "include_entities": False,
        }
        assert "min_scores" not in observation
        assert "min_scores" not in raw

        rendered = provider._render_recall(bundle)
        assert "sources: raw-covered" in rendered
        assert "Covered raw fact" not in rendered
        assert count_render_tokens(rendered) <= 100

    def test_two_lane_budget_reserves_formatter_headroom(self, tmp_path, monkeypatch):
        provider = _make_provider(
            tmp_path,
            monkeypatch,
            recall_max_tokens=101,
        )
        observation, raw = provider._recall_lane_budgets()
        assert observation == 55
        assert raw == 35
        assert observation >= int(101 * 0.55)
        assert raw >= int(101 * 0.35)
        assert observation + raw < 101

        provider._recall_max_tokens = 2
        assert provider._recall_lane_budgets() == (1, 1)
        provider._recall_max_tokens = 1
        with pytest.raises(ValueError, match="at least 2"):
            provider._recall_lane_budgets()

    def test_configured_recall_budget_below_two_fails_closed(self, tmp_path, monkeypatch):
        with pytest.raises(ValueError, match="at least 2"):
            _make_provider(tmp_path, monkeypatch, recall_max_tokens=1)

    def test_rendered_cl100k_budget_is_a_hard_single_cap(self):
        tiktoken = pytest.importorskip("tiktoken")
        bundle = RecallBundle(
            results=tuple(
                _result(f"observation-{index}", "memory " + ("token " * 80))
                for index in range(5)
            )
            + tuple(
                _result(f"raw-{index}", "raw " + ("detail " * 80))
                for index in range(5)
            ),
            source_facts={},
        )
        rendered = render_recall_bundle(bundle, max_tokens=120)
        encoding = tiktoken.get_encoding("cl100k_base")
        assert len(encoding.encode(rendered, disallowed_special=())) <= 120
        assert "1. memory" in rendered
        assert "raw-4" not in rendered

    def test_legacy_observations_omits_all_tag_filters(self, tmp_path, monkeypatch):
        client = _client()
        provider = _make_provider(tmp_path, monkeypatch, client=client)
        provider._recall_bundle("legacy", mode=LEGACY_OBSERVATIONS_MODE)
        request = client.arecall.call_args.kwargs
        assert request == {
            "bank_id": "personal-justin-core",
            "query": "legacy",
            "budget": "mid",
            "max_tokens": 100,
            "types": ["observation"],
            "include_entities": False,
        }
        assert not ({"tags", "tag_groups", "tags_match", "min_scores"} & request.keys())

    def test_full_provenance_uses_explicit_subbudget_and_renders_source_body(
        self,
        tmp_path,
        monkeypatch,
    ):
        async def recall(**kwargs):
            if kwargs["types"] == ["observation"]:
                return _response(
                    [_result("observation", "Remembered", ["source-1"])],
                    {"source-1": _result("source-1", "Original source body")},
                )
            return _response()

        client = _client(recall_side_effect=recall)
        provider = _make_provider(tmp_path, monkeypatch, client=client)
        bundle = provider._recall_bundle(
            "why",
            mode=FULL_PROVENANCE_MODE,
            source_facts_max_tokens=25,
        )
        observation, raw = [call.kwargs for call in client.arecall.call_args_list]
        assert observation["max_source_facts_tokens"] == 25
        assert observation["include_source_facts"] is True
        assert "include_source_facts" not in raw
        rendered = provider._render_recall(bundle, include_source_content=True)
        assert "sources: source-1" in rendered
        assert "[source-1] Original source body" in rendered
        assert count_render_tokens(rendered) <= provider._recall_max_tokens

        with pytest.raises(ValueError, match="requires"):
            provider._recall_bundle("why", mode=FULL_PROVENANCE_MODE)
        with pytest.raises(ValueError, match="between 1"):
            provider._recall_bundle(
                "why",
                mode=FULL_PROVENANCE_MODE,
                source_facts_max_tokens=101,
            )

    def test_server_mixed_is_one_native_prefer_observations_request(
        self,
        tmp_path,
        monkeypatch,
    ):
        client = _client()
        provider = _make_provider(tmp_path, monkeypatch, client=client)
        provider._recall_bundle("mixed", mode=SERVER_MIXED_MODE)
        client.arecall.assert_awaited_once()
        assert client.arecall.call_args.kwargs == {
            "bank_id": "personal-justin-core",
            "query": "mixed",
            "budget": "mid",
            "max_tokens": 100,
            "types": ["world", "experience", "observation"],
            "include_entities": False,
            "prefer_observations": True,
        }

    def test_merge_helper_keeps_rank_and_removes_covered_or_duplicate_raw(self):
        observations = [
            _result("o1", "first", ["r1"]),
            _result("same", "observation duplicate winner"),
        ]
        raw = [
            _result("r1", "covered"),
            _result("same", "duplicate"),
            _result("r2", "second raw"),
            _result("r3", "third raw"),
        ]
        assert [result.id for result in merge_recall_results(observations, raw)] == [
            "o1",
            "same",
            "r2",
            "r3",
        ]


class TestDurableOutbox:
    def test_intent_is_owner_only_and_exists_before_first_network_attempt(
        self,
        tmp_path,
        monkeypatch,
    ):
        observed = {}
        provider = None

        async def retain(**request):
            records = provider._outbox.records()
            observed["record"] = copy.deepcopy(records[0])
            observed["request"] = copy.deepcopy(request)
            observed["watermark"] = provider._outbox.contiguous_acked_turn(
                provider._bank_id,
                provider._session_id,
            )

        client = _client(retain_side_effect=retain)
        provider = _make_provider(tmp_path, monkeypatch, client=client)
        provider.sync_turn(
            "original user",
            "final assistant",
            messages=[
                {"role": "user", "content": "original user"},
                {"role": "assistant", "tool_calls": [{"id": "secret-tool-call"}]},
                {"role": "tool", "content": "secret-tool-output"},
                {"role": "assistant", "content": "final assistant"},
            ],
        )
        provider._retain_queue.join()

        assert observed["watermark"] == 0
        persisted_part = observed["record"]["parts"][0]
        assert observed["request"] == persisted_part["request"]
        assert persisted_part["payload_sha256"] == immutable_json_sha256(
            observed["request"]
        )
        UUID(persisted_part["operation_id"])
        content = json.loads(observed["request"]["items"][0]["content"])
        assert [message["role"] for message in content] == ["user", "assistant"]
        assert content[0]["content"] == "User: original user"
        assert content[1]["content"] == "Assistant: final assistant"
        assert all(message["role"] != "tool" for message in content)
        assert "secret-tool" not in observed["request"]["items"][0]["content"]
        assert provider._outbox.records() == []
        assert provider._outbox.contiguous_acked_turn(
            provider._bank_id,
            provider._session_id,
        ) == 1

        root = tmp_path / "hindsight" / "outbox-v1"
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        state_files = list((root / "state").glob("*.json"))
        assert len(state_files) == 1
        assert stat.S_IMODE(state_files[0].stat().st_mode) == 0o600

    def test_all_split_parts_must_ack_before_watermark_and_removal(self, tmp_path):
        outbox = DurableRetainOutbox(tmp_path)
        record = _outbox_record(part_count=2)
        outbox.put_turn(record)
        record_path = outbox.records_dir / "turn-1.json"
        assert stat.S_IMODE(record_path.stat().st_mode) == 0o600
        assert stat.S_IMODE((outbox.root / ".lock").stat().st_mode) == 0o600
        assert outbox.contiguous_acked_turn("bank", "session") == 0

        outbox.mark_acknowledged("turn-1", 0)
        assert record_path.exists()
        assert outbox.contiguous_acked_turn("bank", "session") == 0

        outbox.mark_acknowledged("turn-1", 1)
        assert not record_path.exists()
        assert outbox.contiguous_acked_turn("bank", "session") == 1

    def test_lost_ack_retries_exact_immutable_request_and_uuid(
        self,
        tmp_path,
        monkeypatch,
    ):
        attempts = []
        backend_operation_ids = set()

        async def retain(**request):
            attempts.append(copy.deepcopy(request))
            backend_operation_ids.add(request["operation_id"])
            if len(attempts) == 1:
                raise ConnectionError("server committed but acknowledgement was lost")

        client = _client(retain_side_effect=retain)
        provider = _make_provider(
            tmp_path,
            monkeypatch,
            client=client,
            outbox_poison_attempts=3,
        )
        provider.sync_turn("one", "answer")
        provider._retain_queue.join()

        assert len(attempts) == 2
        assert attempts[0] == attempts[1]
        assert attempts[0]["operation_id"] == attempts[1]["operation_id"]
        assert len(backend_operation_ids) == 1
        assert provider._outbox.records() == []
        assert provider._outbox.contiguous_acked_turn(
            provider._bank_id,
            provider._session_id,
        ) == 1

    def test_restart_replays_persisted_request_without_reminting_identity(
        self,
        tmp_path,
        monkeypatch,
    ):
        first = _make_provider(tmp_path, monkeypatch, retain_every_n_turns=10)
        monkeypatch.setattr(first, "_ensure_writer", lambda: None)
        monkeypatch.setattr(first, "_register_atexit", lambda: None)
        first.sync_turn("survive crash", "replay me")
        persisted = copy.deepcopy(first._outbox.records()[0]["parts"][0]["request"])

        replayed = []

        async def retain(**request):
            replayed.append(copy.deepcopy(request))

        second_client = _client(retain_side_effect=retain)
        second = HindsightMemoryProvider()
        second._client = second_client
        second.initialize(
            session_id="replacement-session",
            hermes_home=str(tmp_path),
            platform="cli",
            agent_identity="tyler",
        )
        second._retain_queue.join()

        assert replayed == [persisted]
        assert second._outbox.records() == []
        assert second._outbox.contiguous_acked_turn(
            second._bank_id,
            "session-quality",
        ) == 1

    def test_poison_item_is_retained_while_later_turn_drains(
        self,
        tmp_path,
        monkeypatch,
    ):
        delivered = []

        async def retain(**request):
            content = request["items"][0]["content"]
            if "poison-user" in content:
                raise ValueError("permanent poison")
            delivered.append(copy.deepcopy(request))

        client = _client(retain_side_effect=retain)
        provider = _make_provider(
            tmp_path,
            monkeypatch,
            client=client,
            outbox_poison_attempts=1,
        )
        provider.sync_turn("poison-user", "bad")
        provider.sync_turn("healthy-user", "good")
        provider._retain_queue.join()

        records = provider._outbox.records()
        assert len(records) == 1
        poison = records[0]
        assert "poison-user" in poison["parts"][0]["request"]["items"][0]["content"]
        assert poison["parts"][0]["delivery"]["poisoned"] is True
        assert poison["parts"][0]["delivery"]["last_error_sha256"]
        assert len(delivered) == 1
        assert "healthy-user" in delivered[0]["items"][0]["content"]
        state = provider._outbox.completed_state(provider._bank_id, provider._session_id)
        assert state["completed_turns"] == [2]
        assert state["contiguous_acked_turn"] == 0
        assert provider._outbox.pending_jobs() == []

    def test_recovery_finishes_crash_after_durable_final_ack(self, tmp_path):
        outbox = DurableRetainOutbox(tmp_path)
        record = _outbox_record()
        record["parts"][0]["delivery"]["acked"] = True
        outbox.put_turn(record)

        restarted = DurableRetainOutbox(tmp_path)
        restarted.recover_acknowledged_turns()
        assert restarted.records() == []
        assert restarted.contiguous_acked_turn("bank", "session") == 1

    def test_large_turn_requests_keep_same_document_and_distinct_part_identities(
        self,
        tmp_path,
        monkeypatch,
    ):
        provider = _make_provider(tmp_path, monkeypatch, retain_every_n_turns=2)
        provider.sync_turn("😀" * 190_000, "final")
        records = provider._outbox.records()
        assert len(records) == 1
        parts = records[0]["parts"]
        assert len(parts) > 1
        requests = [part["request"] for part in parts]
        assert len({request["document_id"] for request in requests}) == 1
        assert len({part["part_id"] for part in parts}) == len(parts)
        assert len({part["operation_id"] for part in parts}) == len(parts)
        assert all(request["retain_async"] is True for request in requests)
        assert all(
            len(request["items"][0]["content"]) <= MAX_CONTENT_CHARACTERS_PER_PART
            for request in requests
        )
        assert all(
            len(
                json.dumps(
                    request,
                    ensure_ascii=True,
                ).encode("utf-8")
            )
            < MAX_GATEWAY_BODY_BYTES
            for request in requests
        )

        reconstructed = "".join(request["items"][0]["content"] for request in requests)
        messages = json.loads(reconstructed)
        assert messages[0]["content"] == "User: " + ("😀" * 190_000)
        assert messages[1]["content"] == "Assistant: final"

    def test_same_document_new_turns_receive_distinct_operation_ids(
        self,
        tmp_path,
        monkeypatch,
    ):
        provider = _make_provider(tmp_path, monkeypatch, retain_every_n_turns=10)
        provider.sync_turn("body one", "answer one")
        provider.sync_turn("body two", "answer two")
        records = provider._outbox.records()
        assert len(records) == 2
        requests = [record["parts"][0]["request"] for record in records]
        assert len({request["document_id"] for request in requests}) == 1
        assert len({request["operation_id"] for request in requests}) == 2
        assert requests[0]["items"][0]["content"] != requests[1]["items"][0]["content"]
