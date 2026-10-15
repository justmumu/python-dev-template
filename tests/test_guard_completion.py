"""Completion evidence from ordinary Codex rollouts, without a host process."""

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


class Rollout:
    """Sanitized ordinary session records captured from Codex 0.162.1."""

    def __init__(self, root: Path, *, thread="thread", parent=None, history="paginated") -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "rollout.jsonl"
        self.thread = thread
        self.parent = parent
        self.path.write_text("")
        self.append(
            {
                "type": "session_meta",
                "payload": {
                    "id": thread,
                    "parent_thread_id": parent,
                    "history_mode": history,
                },
            }
        )

    def append(self, record):
        with self.path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def complete(self, *, call="call", thread=None, turn="turn", process: str | None = "42", exit_code=0, **fields):
        item: dict[str, Any] = {
            "type": "CommandExecution",
            "id": call,
            "source": "unified_exec_startup",
            "status": "completed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            **fields,
        }
        if process is not None:
            item["process_id"] = process
        self.append(
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "thread_id": thread or self.thread,
                    "turn_id": turn,
                    "item": item,
                },
            }
        )

    def context(self):
        return {"session_id": self.parent or self.thread, "turn_id": "turn", "transcript_path": str(self.path)}

    def state(self, *, call="call"):
        return {
            "inflight": {
                call: {
                    "started": time.time(),
                    "client": "codex",
                    "session": self.parent or self.thread,
                    "turn": "turn",
                    "shell": True,
                    "transcript": str(self.path),
                }
            }
        }


def stored_rollout(directory, *, thread, parent=None):
    """Store a sanitized session using the host's rollout filename convention."""
    rollout = Rollout(directory, thread=thread, parent=parent)
    path = directory / f"rollout-2026-10-14T12-00-00-{thread}.jsonl"
    rollout.path.rename(path)
    rollout.path = path
    return rollout


@pytest.fixture
def nested_rollout(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(home))
    parent = stored_rollout(home / "sessions/2026/10/13", thread="middle", parent="root")
    leaf = stored_rollout(home / "sessions/2026/10/14", thread="leaf", parent="middle")
    state = leaf.state()
    state["inflight"]["call"]["session"] = "root"
    return home, parent, leaf, state


@pytest.mark.parametrize("depth", [2, 5])
def test_nested_completion_preserves_leaf_identity(nested_rollout, depth):
    home, parent, leaf, state = nested_rollout
    for index in range(depth - 2):
        parent = stored_rollout(home / "sessions/2026/10/12", thread=parent.parent, parent=f"root-{index}")
    state["inflight"]["call"]["session"] = parent.parent
    leaf.complete()
    assert guard.live_calls(state) == {}
    assert state["needs_evaluation"] is True


def test_old_nested_reservation_recovers_without_reader_fields(nested_rollout):
    _, _, leaf, state = nested_rollout
    state["inflight"]["call"]["started"] -= 7200
    leaf.complete()
    restored = json.loads(json.dumps(state))
    assert guard.live_calls(restored) == {}


@pytest.mark.parametrize("duplicate", [False, True])
def test_nested_parent_can_be_archived(nested_rollout, duplicate):
    home, parent, leaf, state = nested_rollout
    assert "call" in guard.live_calls(state)
    stored_rollout(home / "archived_sessions", thread="middle", parent="root")
    if not duplicate:
        parent.path.unlink()
    leaf.complete()
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize("parent_id", ["unrelated", "middle", "leaf", None, "", 3, ["root"]])
def test_unverified_nested_ancestry_stays_pending(nested_rollout, parent_id):
    _, parent, leaf, state = nested_rollout
    header = json.loads(parent.path.read_text())
    header["payload"]["parent_thread_id"] = parent_id
    parent.path.write_text(json.dumps(header) + "\n")
    leaf.complete()
    state["inflight"]["call"]["started"] -= 7200
    assert "call" in guard.live_calls(state)
    assert not state.get("window")


@pytest.mark.parametrize("fault", ["id", "type", "partial", "malformed", "oversized", "replayed"])
def test_nested_ancestry_requires_valid_first_header(nested_rollout, fault):
    _, parent, leaf, state = nested_rollout
    valid = parent.path.read_text()
    header = json.loads(valid)
    if fault == "id":
        header["payload"]["id"] = "impostor"
    elif fault == "type":
        header["type"] = "event_msg"
    elif fault == "oversized":
        header["padding"] = "x" * guard.TRANSCRIPT_TAIL_BYTES
    content = json.dumps(header) + "\n"
    if fault == "partial":
        content = valid.rstrip()
    elif fault == "malformed":
        content = "not json\n"
    elif fault == "replayed":
        content = '{"type":"session_meta","payload":{"id":"impostor"}}\n' + valid
    parent.path.write_text(content)
    leaf.complete()
    assert "call" in guard.live_calls(state)


@pytest.mark.parametrize("conflict_first", [False, True])
def test_conflicting_duplicate_parent_cannot_prove_ancestry(nested_rollout, conflict_first):
    home, parent, leaf, state = nested_rollout
    duplicate = stored_rollout(home / "archived_sessions", thread="middle", parent="unrelated")
    if conflict_first:
        original = parent.path.read_bytes()
        parent.path.write_bytes(duplicate.path.read_bytes())
        duplicate.path.write_bytes(original)
    leaf.complete()
    assert "call" in guard.live_calls(state)


def test_invalid_duplicate_parent_is_not_ignored(nested_rollout):
    home, _, leaf, state = nested_rollout
    duplicate = stored_rollout(home / "archived_sessions", thread="middle", parent="root")
    duplicate.path.write_text("not json\n")
    leaf.complete()
    assert "call" in guard.live_calls(state)


def test_missing_parent_can_appear_without_losing_completion(nested_rollout):
    _, parent, leaf, state = nested_rollout
    header = parent.path.read_bytes()
    parent.path.unlink()
    leaf.complete()
    assert "call" in guard.live_calls(state)
    parent.path.write_bytes(header)
    assert guard.live_calls(state) == {}


def test_changed_ancestor_invalidates_previous_binding(nested_rollout):
    home, parent, leaf, state = nested_rollout
    assert "call" in guard.live_calls(state)
    replacement = stored_rollout(home / "replacement", thread="middle", parent="unrelated")
    replacement.path.replace(parent.path)
    leaf.complete()
    assert "call" in guard.live_calls(state)
    stored_rollout(parent.path.parent, thread="middle", parent="root")
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize("link_kind", ["file", "directory"])
def test_parent_discovery_does_not_follow_links_outside_store(nested_rollout, link_kind, monkeypatch):
    home, parent, leaf, state = nested_rollout
    outside = home / "outside"
    outside.mkdir()
    target = outside / parent.path.name
    parent.path.replace(target)
    if link_kind == "file":
        parent.path.symlink_to(target)
    else:
        (home / "sessions/linked").symlink_to(outside, target_is_directory=True)
    scanned = []
    original_scandir = guard.os.scandir

    def record_scandir(path):
        scanned.append(Path(path).resolve())
        return original_scandir(path)

    monkeypatch.setattr(guard.os, "scandir", record_scandir)
    leaf.complete()
    assert "call" in guard.live_calls(state)
    assert outside.resolve() not in scanned


def test_unreadable_parent_does_not_prove_ancestry(nested_rollout, monkeypatch):
    _, parent, leaf, state = nested_rollout
    leaf.complete()
    original = Path.open

    def open_readable(path, *args, **kwargs):
        if path == parent.path:
            raise PermissionError("parent unreadable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_readable)
    assert "call" in guard.live_calls(state)


@pytest.mark.parametrize("identity", ["call", "thread", "turn"])
def test_nested_terminal_must_match_leaf_call(nested_rollout, identity):
    _, parent, leaf, state = nested_rollout
    leaf.complete(**{identity: "middle"})
    parent.complete(thread="leaf")
    assert "call" in guard.live_calls(state)
    leaf.complete()
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize(
    "fields",
    [{"source": "other"}, {"status": "failed"}, {"process": None}, {"exit_code": True}, {"type": "unknown"}],
)
def test_nested_ancestry_does_not_relax_terminal_evidence(nested_rollout, fields):
    _, _, leaf, state = nested_rollout
    leaf.complete(**fields)
    assert "call" in guard.live_calls(state)
    leaf.complete()
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize(
    ("process", "exit_code", "expected"), [("42", 0, "success"), ("42", 1, "failure"), (None, -1, None)]
)
def test_nested_completion_keeps_outcome_allowance_once(nested_rollout, process, exit_code, expected):
    _, _, leaf, state = nested_rollout
    entry = state["inflight"]["call"]
    entry["allowances"] = {"success": {"marker": "success"}, "failure": {"marker": "failure"}}
    leaf.complete(process=process, exit_code=exit_code)
    assert guard.live_calls(state) == {}
    assert guard.live_calls(state) == {}
    assert state.get("window", []) == ([{"marker": expected}] if expected else [])


def test_nested_admission_skips_prior_results_but_not_future_completion(nested_rollout):
    _, _, leaf, state = nested_rollout
    leaf.complete()
    entry = state["inflight"]["call"]
    assert guard.command_completion(entry, "call", starting=True) == "pending"
    assert "call" in guard.live_calls(state)
    leaf.complete()
    assert guard.live_calls(state) == {}


def test_nested_calls_share_discovery_without_reading_unrelated_bodies(nested_rollout, monkeypatch):
    home, _, leaf, state = nested_rollout
    for index in range(120):
        stored_rollout(home / "sessions/2026/10/01", thread=f"other-{index}")
    state["inflight"]["second"] = dict(state["inflight"]["call"])
    leaf.complete()
    leaf.complete(call="second")
    opened = []
    scanned = []
    original_open = Path.open
    original_scandir = guard.os.scandir

    def record_open(path, *args, **kwargs):
        opened.append(path)
        return original_open(path, *args, **kwargs)

    def record_scandir(path):
        scanned.append(Path(path))
        return original_scandir(path)

    monkeypatch.setattr(Path, "open", record_open)
    monkeypatch.setattr(guard.os, "scandir", record_scandir)
    assert guard.live_calls(state) == {}
    assert len(scanned) == len(set(scanned))
    assert all("-other-" not in path.name for path in opened)


@pytest.fixture
def rollout(tmp_path):
    return Rollout(tmp_path)


def test_spawn_failure_closes_only_its_call(rollout):
    rollout.complete(process=None, exit_code=-1)
    state = rollout.state()
    state["inflight"]["other"] = rollout.state(call="other")["inflight"]["other"]
    assert set(guard.live_calls(state)) == {"other"}
    assert state["needs_evaluation"] is True
    assert not state.get("window")


def test_new_call_skips_history_before_admission(rollout):
    rollout.append({"type": "irrelevant", "text": "x" * (guard.TRANSCRIPT_TAIL_BYTES + 1)})
    state = rollout.state()
    assert guard.command_completion(state["inflight"]["call"], "call", starting=True) == "pending"
    rollout.complete(process=None, exit_code=-1)
    assert guard.live_calls(state) == {}


def test_admission_does_not_skip_an_incomplete_record(rollout):
    state = rollout.state()
    with rollout.path.open("a") as handle:
        handle.write('{"type": "irrelevant"')
    assert guard.command_completion(state["inflight"]["call"], "call", starting=True) == "pending"
    with rollout.path.open("a") as handle:
        handle.write("}\n")
    rollout.complete(process=None, exit_code=-1)
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize("exit_code", [0, 1, -15])
def test_process_completion_grants_existing_outcome_once(rollout, exit_code):
    state = rollout.state()
    entry = state["inflight"]["call"]
    entry["allowances"] = {"success": {"marker": "success"}, "failure": {"marker": "failure"}}
    assert "call" in guard.live_calls(state)
    rollout.complete(exit_code=exit_code)
    assert guard.live_calls(state) == {}
    assert state["window"] == [{"marker": "success" if exit_code == 0 else "failure"}]
    guard.live_calls(state)
    assert len(state["window"]) == 1


def test_yielded_output_and_age_do_not_prove_process_completion(rollout):
    state = rollout.state()
    state["inflight"]["call"]["started"] -= 7200
    rollout.append({"type": "function_call_output", "call_id": "call", "output": "yield"})
    assert "call" in guard.live_calls(state)
    rollout.complete()
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize("identity", ["call", "thread", "turn"])
def test_other_identity_cannot_close_call(rollout, identity):
    rollout.complete(**{identity: "other"})
    assert "call" in guard.live_calls(rollout.state())


@pytest.mark.parametrize(
    "fields",
    [
        {"source": "unrelated"},
        {"type": "unknown"},
        {"status": "unknown"},
        {"exit_code": True},
        {"exit_code": "0"},
        {"status": "failed", "exit_code": 0},
        {"process": None, "exit_code": 0},
        {"process": None, "exit_code": 1},
    ],
)
def test_unrecognized_or_inconsistent_result_stays_pending(rollout, fields):
    rollout.complete(**fields)
    assert "call" in guard.live_calls(rollout.state())


def test_partial_last_line_is_retried(rollout):
    rollout.complete()
    complete = rollout.path.read_bytes()
    rollout.path.write_bytes(complete[:-1])
    state = rollout.state()
    assert "call" in guard.live_calls(state)
    with rollout.path.open("ab") as handle:
        handle.write(b"\n")
    assert guard.live_calls(state) == {}


def test_missing_rollout_does_not_undo_observed_pending_state(rollout):
    state = rollout.state()
    assert "call" in guard.live_calls(state)
    state["inflight"]["call"]["started"] -= 7200
    rollout.path.unlink()
    assert "call" in guard.live_calls(state)


def test_duplicate_records_do_not_duplicate_allowance(rollout):
    rollout.complete()
    rollout.complete()
    state = rollout.state()
    state["inflight"]["call"]["allowances"] = {"success": {"marker": "once"}}
    assert guard.live_calls(state) == {}
    assert state["window"] == [{"marker": "once"}]


def test_large_rollout_advances_without_losing_completion(rollout):
    for _ in range(70):
        rollout.append({"type": "irrelevant", "padding": "x" * 65536})
    rollout.complete()
    state = rollout.state()
    assert "call" in guard.live_calls(state)
    assert guard.live_calls(state) == {}


def test_oversized_unrelated_record_does_not_hide_completion(rollout):
    state = rollout.state()
    assert guard.command_completion(state["inflight"]["call"], "call", starting=True) == "pending"
    rollout.append({"type": "irrelevant", "padding": "x" * (guard.TRANSCRIPT_TAIL_BYTES + 1024)})
    rollout.complete()
    assert "call" in guard.live_calls(state)
    assert guard.live_calls(state) == {}


def test_oversized_terminal_is_not_completion_evidence(rollout):
    state = rollout.state()
    rollout.complete(padding="x" * (guard.TRANSCRIPT_TAIL_BYTES + 1024))
    for _ in range(3):
        assert "call" in guard.live_calls(state)


def test_replaced_rollout_revalidates_identity(rollout):
    state = rollout.state()
    assert "call" in guard.live_calls(state)
    replacement = Rollout(rollout.path.parent / "replacement", thread="other")
    replacement.complete()
    replacement.path.replace(rollout.path)
    assert "call" in guard.live_calls(state)


def test_replaced_rollout_restarts_at_matching_session_header(rollout):
    rollout.append({"type": "irrelevant", "padding": "x" * 4096})
    state = rollout.state()
    assert "call" in guard.live_calls(state)
    replacement = Rollout(rollout.path.parent / "replacement")
    replacement.complete()
    replacement.append({"type": "irrelevant", "padding": "x" * 8192})
    replacement.path.replace(rollout.path)
    assert guard.live_calls(state) == {}


def test_truncated_rollout_restarts_reader(rollout):
    rollout.append({"type": "irrelevant", "padding": "x" * 4096})
    state = rollout.state()
    assert "call" in guard.live_calls(state)
    updated = Rollout(rollout.path.parent)
    updated.complete()
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize("parent", ["parent", "unrelated"])
def test_child_transcript_must_belong_to_hook_session(tmp_path, parent):
    rollout = Rollout(tmp_path, thread="child", parent=parent)
    rollout.complete()
    state = rollout.state()
    state["inflight"]["call"]["session"] = "parent"
    assert (guard.live_calls(state) == {}) is (parent == "parent")


def test_malformed_record_is_not_completion_evidence(rollout):
    with rollout.path.open("a") as handle:
        handle.write("not json\n")
    rollout.complete()
    assert "call" in guard.live_calls(rollout.state())


def test_legacy_expiry_is_unchanged():
    state = {"inflight": {"old": {"started": time.time() - 7200}}}
    assert guard.live_calls(state) == {}


def test_legacy_transcript_result_is_still_supported(tmp_path):
    rollout = Rollout(tmp_path, history="legacy")
    rollout.append({"type": "function_call_output", "call_id": "call", "output": "done"})
    assert guard.live_calls(rollout.state()) == {}


def test_missing_history_mode_uses_legacy_results(rollout):
    header = json.loads(rollout.path.read_text())
    del header["payload"]["history_mode"]
    rollout.path.write_text(json.dumps(header) + "\n")
    rollout.append({"type": "function_call_output", "call_id": "call", "output": "done"})
    assert guard.live_calls(rollout.state()) == {}


@pytest.mark.parametrize("history", [None, "future"])
def test_unrecognized_history_mode_stays_pending(tmp_path, history):
    rollout = Rollout(tmp_path, history=history)
    rollout.append({"type": "function_call_output", "call_id": "call", "output": "done"})
    assert "call" in guard.live_calls(rollout.state())


def test_non_shell_tool_keeps_existing_completion_path(rollout):
    rollout.append({"type": "function_call_output", "call_id": "call", "output": "done"})
    state = rollout.state()
    state["inflight"]["call"]["shell"] = False
    assert guard.live_calls(state) == {}


@pytest.mark.parametrize("status", ["completed", "failed", "declined"])
def test_intercepted_patch_finishes_without_shell_allowance(rollout, status):
    rollout.complete(type="FileChange", status=status, process=None)
    state = rollout.state()
    state["inflight"]["call"]["allowances"] = {"success": {"marker": "must-not-grant"}}
    assert guard.live_calls(state) == {}
    assert not state.get("window")


def test_replayed_parent_metadata_does_not_replace_child_identity(tmp_path):
    rollout = Rollout(tmp_path, thread="child", parent="parent")
    rollout.append({"type": "session_meta", "payload": {"id": "parent", "history_mode": "paginated"}})
    rollout.complete()
    assert guard.live_calls(rollout.state()) == {}
