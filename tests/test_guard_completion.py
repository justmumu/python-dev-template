"""Completion evidence from Codex schema-1 lifecycle records, without a host process."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("guard_completion", ROOT / "scripts/hooks/guard_config.py")
assert _SPEC is not None
assert _SPEC.loader is not None
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)


class Trace:
    """Small sanitized records with the shapes captured from Codex 0.162.1."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bundle = root / "trace-example-thread"
        (self.bundle / "payloads").mkdir(parents=True)
        self.path = self.bundle / "trace.jsonl"
        self.path.touch()
        self.seq = 0

    def event(self, event_type, *, call="call", thread="thread", **fields):
        self.seq += 1
        record = {
            "schema_version": 1,
            "seq": self.seq,
            "thread_id": thread,
            "codex_turn_id": "turn",
            "payload": {"type": event_type, "tool_call_id": call, **fields},
        }
        with self.path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def start(self, *, call="call", thread="thread"):
        self.event("tool_call_started", call=call, thread=thread, kind={"type": "exec_command"})

    def runtime(self, *, end=False, process: str | None = "42", exit_code=0, call="call", thread="thread"):
        data: dict[str, Any] = {"call_id": call, "turn_id": "turn", "source": "unified_exec_startup"}
        if process is not None:
            data["process_id"] = process
        if end:
            data["exit_code"] = exit_code
            data["status"] = "completed" if exit_code == 0 else "failed"
        path = f"payloads/{self.seq + 1}.json"
        (self.bundle / path).write_text(json.dumps(data))
        self.event(
            "tool_call_runtime_ended" if end else "tool_call_runtime_started",
            call=call,
            thread=thread,
            status="completed" if exit_code == 0 else "failed",
            runtime_payload={"kind": {"type": "tool_runtime_event"}, "path": path},
        )

    def dispatch(self, *, status="completed", call="call", thread="thread"):
        self.event("tool_call_ended", call=call, thread=thread, status=status)

    def state(self, *, call="call", thread="thread"):
        return {
            "inflight": {
                call: {
                    "started": time.time(),
                    "client": "codex",
                    "session": thread,
                    "trace_root": str(self.root),
                }
            }
        }


@pytest.fixture
def trace(tmp_path):
    return Trace(tmp_path)


def test_spawn_failure_closes_only_its_call(trace):
    trace.start()
    trace.runtime(process=None)
    trace.runtime(end=True, process=None, exit_code=-1)
    trace.dispatch(status="failed")
    state = trace.state()
    state["inflight"]["other"] = trace.state(call="other")["inflight"]["other"]
    assert set(guard.live_calls(state)) == {"other"}
    assert state["needs_evaluation"] is True
    assert not state.get("window")


@pytest.mark.parametrize("dispatch_first", [False, True])
@pytest.mark.parametrize("exit_code", [0, 1])
def test_process_completion_requires_both_receipts(trace, dispatch_first, exit_code):
    trace.start()
    trace.runtime()
    state = trace.state()
    entry = state["inflight"]["call"]
    entry["allowances"] = {"success": {"marker": "success"}, "failure": {"marker": "failure"}}
    if dispatch_first:
        trace.dispatch()
    else:
        trace.runtime(end=True, exit_code=exit_code)
    assert "call" in guard.live_calls(state)
    if dispatch_first:
        trace.runtime(end=True, exit_code=exit_code)
    else:
        trace.dispatch()
    assert guard.live_calls(state) == {}
    assert state["window"] == [{"marker": "success" if exit_code == 0 else "failure"}]
    guard.live_calls(state)
    assert len(state["window"]) == 1


def test_running_receipt_overrides_age_and_transcript(trace):
    trace.start()
    trace.runtime()
    trace.dispatch()
    state = trace.state()
    entry = state["inflight"]["call"]
    entry["started"] -= 7200
    transcript = trace.root / "rollout.jsonl"
    transcript.write_text(json.dumps({"type": "function_call_output", "call_id": "call", "output": "yield"}))
    entry["transcript"] = str(transcript)
    assert "call" in guard.live_calls(state)
    trace.path.unlink()
    assert "call" in guard.live_calls(state)


def test_retry_does_not_finish_before_final_dispatch(trace):
    trace.start()
    trace.runtime(process=None)
    trace.runtime(end=True, process=None, exit_code=-1)
    state = trace.state()
    assert "call" in guard.live_calls(state)
    trace.runtime()
    trace.dispatch()
    assert "call" in guard.live_calls(state)
    trace.runtime(end=True)
    assert guard.live_calls(state) == {}


def test_other_thread_cannot_close_call(trace):
    trace.start(thread="other")
    trace.runtime(thread="other")
    trace.runtime(end=True, thread="other")
    trace.dispatch(thread="other")
    assert "call" in guard.live_calls(trace.state())


def test_partial_last_line_is_retried(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    state = trace.state()
    trace.dispatch()
    complete = trace.path.read_bytes()
    trace.path.write_bytes(complete[:-1])
    assert "call" in guard.live_calls(state)
    with trace.path.open("ab") as handle:
        handle.write(b"\n")
    assert guard.live_calls(state) == {}


def test_unknown_schema_never_completes(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    trace.dispatch()
    trace.path.write_text(trace.path.read_text().replace('"schema_version": 1', '"schema_version": 2'))
    assert "call" in guard.live_calls(trace.state())


def test_missing_runtime_payload_is_retried(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    trace.dispatch()
    payload = trace.bundle / "payloads/3.json"
    data = payload.read_bytes()
    payload.unlink()
    state = trace.state()
    assert "call" in guard.live_calls(state)
    payload.write_bytes(data)
    assert guard.live_calls(state) == {}


def test_legacy_expiry_is_unchanged():
    state = {"inflight": {"old": {"started": time.time() - 7200}}}
    assert guard.live_calls(state) == {}


def test_duplicate_records_do_not_duplicate_allowance(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    trace.dispatch()
    lines = trace.path.read_text().splitlines(keepends=True)
    trace.path.write_text("".join(line + line for line in lines))
    state = trace.state()
    state["inflight"]["call"]["allowances"] = {"success": {"marker": "once"}}
    assert guard.live_calls(state) == {}
    assert state["window"] == [{"marker": "once"}]


def test_large_trace_advances_without_losing_early_start(trace):
    trace.start()
    trace.runtime()
    for _ in range(70):
        trace.event("unrelated", padding="x" * 65536)
    trace.runtime(end=True)
    trace.dispatch()
    state = trace.state()
    assert "call" in guard.live_calls(state)
    assert guard.live_calls(state) == {}


def test_scan_budget_before_start_does_not_fall_back_to_yielded_result(trace):
    for _ in range(70):
        trace.event("unrelated", padding="x" * 65536)
    trace.start()
    trace.runtime()
    trace.dispatch()
    state = trace.state()
    entry = state["inflight"]["call"]
    assert guard.trace_completion(entry, "call") == "pending"
    assert guard.trace_completion(entry, "call") == "pending"
    trace.runtime(end=True)
    assert guard.live_calls(state) == {}


def test_replaced_trace_does_not_reuse_old_runtime_end(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    state = trace.state()
    assert "call" in guard.live_calls(state)
    trace.path.rename(trace.path.with_suffix(".old"))
    trace.seq = 0
    trace.start()
    trace.dispatch()
    assert "call" in guard.live_calls(state)


def test_ambiguous_bundles_cannot_close_call(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    trace.dispatch()
    other = trace.root / "trace-other-thread"
    other.mkdir()
    (other / "trace.jsonl").write_bytes(trace.path.read_bytes())
    assert "call" in guard.live_calls(trace.state())


def test_runtime_payload_cannot_leave_bundle(trace):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    trace.dispatch()
    outside = trace.root / "outside.json"
    outside.write_bytes((trace.bundle / "payloads/3.json").read_bytes())
    trace.path.write_text(trace.path.read_text().replace("payloads/3.json", "../outside.json"))
    assert "call" in guard.live_calls(trace.state())


def test_subagent_uses_thread_identity_not_bundle_name(trace):
    trace.start(thread="child")
    trace.runtime(thread="child")
    trace.runtime(end=True, thread="child")
    trace.dispatch(thread="child")
    assert guard.live_calls(trace.state(thread="child")) == {}


@pytest.mark.parametrize("parent", ["thread", "unrelated"])
def test_child_hook_session_uses_related_transcript_identity(trace, parent):
    trace.start(thread="child")
    trace.runtime(thread="child", process=None)
    trace.runtime(end=True, thread="child", process=None, exit_code=-1)
    trace.dispatch(thread="child", status="failed")
    transcript = trace.root / "rollout.jsonl"
    transcript.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": "child", "parent_thread_id": parent}}) + "\n"
    )
    state = trace.state()
    state["inflight"]["call"]["transcript"] = str(transcript)
    assert (guard.live_calls(state) == {}) is (parent == "thread")


@pytest.mark.parametrize("field", ["call_id", "turn_id", "source", "process_id"])
def test_mismatched_runtime_receipt_never_closes_call(trace, field):
    trace.start()
    trace.runtime()
    trace.runtime(end=True)
    trace.dispatch()
    receipt = trace.bundle / "payloads/3.json"
    data = json.loads(receipt.read_text())
    data[field] = "unrelated"
    receipt.write_text(json.dumps(data))
    state = trace.state()
    entry = state["inflight"]["call"]
    entry["started"] -= 7200
    entry["allowances"] = {"success": {"marker": "must-not-grant"}}
    transcript = trace.root / "rollout.jsonl"
    transcript.write_text(json.dumps({"type": "function_call_output", "call_id": "call", "output": "yield"}))
    entry["transcript"] = str(transcript)
    assert "call" in guard.live_calls(state)
    assert not state.get("window")


def test_discovery_limit_keeps_unmatched_reservation_pending(trace):
    trace.start()
    trace.runtime()
    trace.dispatch()
    for index in range(129):
        (trace.root / f"other-{index}").touch()
    state = trace.state()
    entry = state["inflight"]["call"]
    transcript = trace.root / "rollout.jsonl"
    transcript.write_text(json.dumps({"type": "function_call_output", "call_id": "call", "output": "yield"}))
    entry["transcript"] = str(transcript)
    assert "call" in guard.live_calls(state)
