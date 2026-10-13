"""Behavior of the protected-files guard, driven through its hook interface."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.test_guard_completion import Trace


def live_codex_fixture(tmp_path):
    """Prepare a disposable repository with the installed host's trusted hook commands."""
    binary = os.environ.get("GUARD_CODEX_BINARY") or shutil.which("codex")
    assert binary, "Codex CLI is required"
    fixture = tmp_path / "project"
    (fixture / "scripts/hooks").mkdir(parents=True)
    (fixture / ".codex").mkdir()
    for name in ("scripts/hooks/guard_config.py", ".codex/hooks.json"):
        shutil.copy2(ROOT / name, fixture / name)
    (fixture / "AGENTS.md").write_text("Disposable guard test. Follow the diagnostic sequence only.\n")
    original = '[project]\nname="guard-experiment"\nversion="0.0.0"\n'
    (fixture / "pyproject.toml").write_text(original)
    (fixture / "uv.lock").write_text("version = 1\n")
    (fixture / "Makefile").write_text("format:\n\t@printf guard_format_ran\\n\n")
    for arguments in (
        ["init", "-q", "-b", "main"],
        ["add", "."],
        ["-c", "user.name=Guard Test", "-c", "user.email=guard@example.invalid", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", *arguments], cwd=fixture, check=True, capture_output=True)
    config_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    config = tomllib.loads((config_home / "config.toml").read_text())
    original_prefix = str(ROOT / ".codex/hooks.json")
    trusted = []
    for key, value in config.get("hooks", {}).get("state", {}).items():
        if key.startswith(original_prefix + ":"):
            fixture_key = str(fixture / ".codex/hooks.json") + key[len(original_prefix) :]
            trusted.append(json.dumps(fixture_key) + "={trusted_hash=" + json.dumps(value["trusted_hash"]) + "}")
    assert trusted, "Review and trust the project's exact hooks before this attended test"
    args = [binary, "exec", "--json", "-C", str(fixture), "-s", "workspace-write"]
    args += ["-c", "projects={" + json.dumps(str(fixture)) + '={trust_level="trusted"}}']
    args += ["-c", "hooks.state={" + ",".join(trusted) + "}"]
    for feature in ("hooks", "code_mode", "code_mode_only", "unified_exec"):
        args += ["-c", f"features.{feature}=true"]
    args += ["-c", "features.multi_agent=true"]
    return fixture, original, args


def live_codex_prompt(fixture, mode):
    """Specify the same diagnostic sequence for a root or child thread."""
    prompt = f"""Run only this authorized disposable guard test, using tools.exec_command and
tools.write_stdin through code-mode. No agents, file inspection, extra commands or repairs.
Use one code cell for steps 1-6. Catch each rejection and print the error; keep going.
1. Execute "printf guard_exit_one; exit 1", yield_time_ms 1000.
2. Execute "sleep 8; printf guard_live_done", yield_time_ms 1000. Save session_id.
3. Execute "printf guard_spawn_failure" with workdir {json.dumps(str(fixture / "missing"))}.
4. Execute "make format" while the sleep still runs. A guard rejection is expected.
5. Poll the saved session_id until exit_code is present; yielded output is not completion.
6. Execute "make format" again. This time it must run.
7. Execute "printf '\\ninjected = true\\n' >> pyproject.toml" in the disposable project.
8. Execute "printf guard_after_write". The guard should report restoring the forbidden write.
9. Execute "printf guard_final_probe" to allow the final completion check.
Final response: EXPERIMENT_DONE. Do not bypass hooks or retry other commands.
"""
    if mode == "child":
        prompt = (
            "Spawn exactly one child agent with the following diagnostic task. "
            "Do not run any shell tools yourself. Wait for the child to finish, then report its result. "
            "The child must run the task in the shared project directory.\n\n" + prompt
        )
    if mode == "untraced":
        prompt = f"""Run this disposable guard control using tools.exec_command through code-mode.
In one cell, catch each error and print it. Run exactly these three calls, then stop:
1. Execute "printf guard_exit_one; exit 1", yield_time_ms 1000.
2. Execute "printf guard_spawn_failure" with workdir {json.dumps(str(fixture / "missing"))}.
3. Execute "make format". A guard rejection is expected: tracing is disabled in this control.
Do not repair anything or retry. Final response: CONTROL_DONE.
"""
    return prompt


def host_trace_evidence(trace_files):
    """Read host receipts, keeping original call and thread identities."""
    commands, ends, inputs, runtime_ends = {}, {}, {}, {}
    command_threads = set()
    for trace_file in trace_files:
        for line in trace_file.read_text().splitlines():
            event = json.loads(line)
            payload = event["payload"]
            call_id = payload.get("tool_call_id")
            if payload["type"] == "tool_call_started" and payload["kind"]["type"] == "exec_command":
                arguments = json.loads(payload["summary"]["input_preview"])
                commands.setdefault(arguments["cmd"], []).append(call_id)
                inputs[call_id] = arguments
                command_threads.add(event["thread_id"])
            if payload["type"] == "tool_call_ended":
                ends[call_id] = json.loads((trace_file.parent / payload["result_payload"]["path"]).read_text())
            if payload["type"] == "tool_call_runtime_ended":
                runtime_ends[call_id] = json.loads((trace_file.parent / payload["runtime_payload"]["path"]).read_text())
    return commands, ends, inputs, runtime_ends, command_threads


@pytest.mark.parametrize("mode", ["traced", "untraced", "child"])
def test_live_codex_completion(tmp_path, mode):
    """Opt-in host acceptance: real hooks, yielded process, spawn error and restoration."""
    if os.environ.get("GUARD_LIVE_CODEX") != "1":
        pytest.skip("Set GUARD_LIVE_CODEX=1 to invoke an authenticated Codex CLI")
    fixture, original, args = live_codex_fixture(tmp_path)
    prompt = live_codex_prompt(fixture, mode)
    trace_root = tmp_path / "traces"
    environment = {**os.environ, "CODEX_ROLLOUT_TRACE_ROOT": str(trace_root)}
    if mode == "untraced":
        environment.pop("CODEX_ROLLOUT_TRACE_ROOT")
    result = subprocess.run(
        [*args, prompt], cwd=fixture, env=environment, capture_output=True, text=True, timeout=180, check=False
    )
    (tmp_path / "codex-events.jsonl").write_text(result.stdout)
    (tmp_path / "codex-stderr.txt").write_text(result.stderr)
    version = subprocess.check_output([args[0], "--version"], text=True).strip()
    print(f"Real host: {version}; evidence: {tmp_path}")
    assert result.returncode == 0, result.stderr[-3000:]
    state = json.loads((fixture / ".git/protected-baseline/state.json").read_text())
    trace_files = list(trace_root.glob("trace-*/trace.jsonl"))
    if mode == "untraced":
        assert not trace_files
        assert len(state["inflight"]) == 1
        stranded = next(iter(state["inflight"].values()))
        assert stranded["client"] == "codex"
        assert not stranded["trace_root"]
        # JSON CLI output omits rejected code-mode calls; the rollout retains them.
        rollout = Path(stranded["transcript"]).read_text()
        assert "Another call that can change protected files is running" in rollout
        assert "guard_exit_one" in result.stdout
        assert '"exit_code":1' in result.stdout
        assert (fixture / "pyproject.toml").read_text() == original
        return
    assert trace_files, "Host must produce lifecycle traces"
    commands, ends, inputs, runtime_ends, command_threads = host_trace_evidence(trace_files)
    if mode == "child":
        host_events = [json.loads(line) for line in result.stdout.splitlines()]
        parent_thread = next(event["thread_id"] for event in host_events if event["type"] == "thread.started")
        assert command_threads
        assert parent_thread not in command_threads
    first_format, second_format = commands["make format"]
    assert "running" in ends[first_format]["error"]
    assert ends[second_format]["value"]["exit_code"] == 0
    assert ends[commands["printf guard_exit_one; exit 1"][0]]["value"]["exit_code"] == 1
    (spawn_call,) = commands["printf guard_spawn_failure"]
    assert inputs[spawn_call]["workdir"] == str(fixture / "missing")
    assert ends[spawn_call]["type"] == "error"
    spawn_end = runtime_ends[spawn_call]
    assert spawn_end["call_id"] == spawn_call
    assert spawn_end["source"] == "unified_exec_startup"
    assert spawn_end["exit_code"] == -1
    assert spawn_end["status"] == "failed"
    assert not spawn_end.get("process_id")
    assert "restored" in ends[commands["printf guard_after_write"][0]]["error"]
    assert (fixture / "pyproject.toml").read_text() == original
    assert state["inflight"] == {}


# Every scenario drives real Git repositories, hooks and commits.
pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "hooks" / "guard_config.py"
PROTECTED_CONTENT = 'name = "demo"\n'
MAKEFILE = """\
uv-add:
\tprintf 'dep = "%s"\\n' "$$PKG" >> pyproject.toml
\tprintf 'locked %s\\n' "$$PKG" >> uv.lock

uv-reinstall:
\trm -rf .venv && mkdir -p .venv/bin .venv/lib/python3.13/site-packages && touch .venv/bin/python

test:
\ttouch .venv/bin/synced-tool

setup:
\t@true

bump-patch:
\tprintf 'version = "2"\\n' >> pyproject.toml && git commit -q -am "bump: 2"

format:
\tprintf '# formatted\\n' >> pyproject.toml

guard-accept-changes:
\t{python} -I -B {guard} --event accept
"""


class Project:
    """A throwaway Git project with the guard's protected files."""

    def __init__(self, root: Path, codex_home: Path) -> None:
        self.root = root
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(root.parent),
            "CODEX_HOME": str(codex_home),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        self.calls = 0

    def sh(self, command: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", command], cwd=self.root, env=self.env, capture_output=True, text=True, check=check
        )

    def hook(self, event: str, payload: dict[str, Any], *, client: str = "claude") -> dict[str, Any]:
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(GUARD), "--client", client, "--event", event],
            input=json.dumps({"cwd": str(self.root), **payload}),
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def call(
        self,
        command: str,
        *,
        client: str = "claude",
        tool: str = "Bash",
        extra: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run one shell call the way a host does: pre hook, command, post hook."""
        self.calls += 1
        payload = shell_payload(command, f"call-{self.calls}", tool=tool, **(extra or {}))
        pre = self.hook("pre", payload, client=client)
        if pre:
            return pre, {}
        result = self.sh(command, check=False)
        event = "post" if result.returncode == 0 or client == "codex" else "post-failure"
        return pre, self.hook(event, payload, client=client)

    def edit(self, path: str, content: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run a Claude Write call the user approved."""
        self.calls += 1
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / path), "content": content},
            "tool_use_id": f"call-{self.calls}",
        }
        pre = self.hook("pre", payload)
        if not pre:
            (self.root / path).write_text(content)
        return pre, self.hook("post", payload)

    def read(self, path: str) -> str:
        return (self.root / path).read_text()


def shell_payload(command: str, call_id: str, *, tool: str = "Bash", **extra: Any) -> dict[str, Any]:
    """A hook payload for one shell call."""
    return {"tool_name": tool, "tool_input": {"command": command, **extra}, "tool_use_id": call_id}


def denial(output: dict[str, Any]) -> str:
    return output.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text('model = "gpt"\n')
    repo = Project(root, codex_home)
    repo.sh("git init -q -b main .")
    (root / "pyproject.toml").write_text(PROTECTED_CONTENT)
    (root / "uv.lock").write_text("version = 1\n")
    (root / "AGENTS.md").write_text("# Rules\n")
    (root / "Makefile").write_text(MAKEFILE.format(python=sys.executable, guard=GUARD))
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n")
    (root / ".codex" / "rules").mkdir(parents=True)
    (root / ".codex" / "rules" / "publishing.rules").write_text("# rules\n")
    (root / "scripts" / "hooks").mkdir(parents=True)
    (root / "scripts" / "hooks" / "helper.py").write_text("VALUE = 1\n")
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/lib/python3.13/site-packages").mkdir(parents=True)
    (root / ".venv/bin/python").write_text("")
    (root / ".gitignore").write_text(".venv/\n")
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        f"#!/bin/sh\n{sys.executable} -I -B {GUARD} --event pre-commit || exit 1\n"
        "if [ -f .format-me ]; then printf '# formatted\\n' >> pyproject.toml; rm .format-me; exit 1; fi\n"
    )
    hook.chmod(0o755)
    repo.sh("git add -A && git commit -q -m init")
    return repo


def test_redirect_into_protected_file_is_restored(project):
    _, post = project.call("echo 'evil = 1' >> pyproject.toml")
    assert project.read("pyproject.toml") == PROTECTED_CONTENT
    assert post["decision"] == "block"
    assert "make uv-add" in post["reason"]
    assert "ask the user" in post["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "python3 -c \"open('pyproject.toml', 'a').write('x = 1')\"",
        "bash -c 'echo x >> uv.lock'",
        "cat > AGENTS.md <<'EOF'\nloosened\nEOF",
        "sed -i.bak 's/demo/other/' pyproject.toml",
        "rm Makefile",
    ],
)
def test_indirect_writes_are_restored(project, command):
    before = {name: project.read(name) for name in ("pyproject.toml", "uv.lock", "AGENTS.md", "Makefile")}
    _, post = project.call(command)
    assert {name: project.read(name) for name in before} == before
    assert post["decision"] == "block"


def test_failed_call_is_still_checked(project):
    _, post = project.call("echo broken >> uv.lock; false")
    assert project.read("uv.lock") == "version = 1\n"
    assert "forbidden" in post["hookSpecificOutput"]["additionalContext"]


def test_codex_spawn_failure_releases_reservation(project, tmp_path):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("true", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    trace.runtime(process=None)
    trace.runtime(end=True, process=None, exit_code=-1)
    trace.dispatch(status="failed")
    assert project.hook("pre", shell_payload("make format", "next"), client="codex") == {}


def test_codex_yielded_post_keeps_reservation(project, tmp_path):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("sleep 8", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    trace.runtime()
    assert project.hook("post", payload, client="codex") == {}
    trace.dispatch()
    next_call = shell_payload("make format", "next")
    assert "running" in denial(project.hook("pre", next_call, client="codex"))
    trace.runtime(end=True)
    assert project.hook("pre", next_call, client="codex") == {}


def test_codex_discovery_overflow_keeps_yielded_post_reserved(project, tmp_path):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    trace.start()
    overflow = [trace.root / f"other-{index}" for index in range(129)]
    for path in overflow:
        path.touch()
    payload = {**shell_payload("sleep 8", "call"), "session_id": "thread"}
    assert project.hook("pre", payload, client="codex") == {}
    trace.runtime()
    trace.dispatch()
    assert project.hook("post", payload, client="codex") == {}
    next_call = shell_payload("make format", "next")
    assert "running" in denial(project.hook("pre", next_call, client="codex"))
    for path in overflow:
        path.unlink()
    assert "running" in denial(project.hook("pre", next_call, client="codex"))
    trace.runtime(end=True)
    assert project.hook("pre", next_call, client="codex") == {}


def test_recovered_call_still_restores_protected_write(project, tmp_path):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("true", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    (project.root / "pyproject.toml").write_text("unauthorized = true\n")
    trace.runtime(process=None)
    trace.runtime(end=True, process=None, exit_code=-1)
    trace.dispatch(status="failed")
    result = project.hook("stop", {}, client="codex")
    assert project.read("pyproject.toml") == PROTECTED_CONTENT
    assert "restored" in result["reason"]


def test_late_post_cannot_approve_another_change(project):
    payload = {**shell_payload("make format", "call"), "session_id": "thread"}
    assert project.hook("pre", payload, client="codex") == {}
    project.sh("make format")
    assert project.hook("post", payload, client="codex") == {}
    (project.root / "pyproject.toml").write_text("unapproved = true\n")
    project.hook("post", payload, client="codex")
    assert "outside an agent call" in denial(project.hook("pre", shell_payload("true", "next")))


@pytest.mark.parametrize("executed", [True, False])
def test_trace_failure_grants_make_allowance_only_after_execution(project, tmp_path, executed):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("make format", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    # A failed Make may have written partial output; a failed spawn may not approve it.
    (project.root / "pyproject.toml").write_text(PROTECTED_CONTENT + "# partial output\n")
    process = "42" if executed else None
    trace.runtime(process=process)
    trace.runtime(end=True, process=process, exit_code=1 if executed else -1)
    trace.dispatch(status="failed")
    result = project.hook("stop", {}, client="codex")
    if executed:
        assert result == {}
        assert "# partial output" in project.read("pyproject.toml")
    else:
        assert "restored" in result["reason"]
        assert project.read("pyproject.toml") == PROTECTED_CONTENT


@pytest.mark.parametrize("exit_code", [0, 1])
def test_trace_accept_requires_success(project, tmp_path, exit_code):
    assert project.call("true") == ({}, {})
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("make guard-accept-changes", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    override = project.root / "pytest.ini"
    override.write_text("[pytest]\n")
    trace.runtime()
    trace.runtime(end=True, exit_code=exit_code)
    trace.dispatch(status="completed" if exit_code == 0 else "failed")
    project.hook("stop", {}, client="codex")
    assert override.exists() is (exit_code == 0)


def test_trace_failed_reinstall_does_not_accept_venv(project, tmp_path):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("make uv-reinstall", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    (project.root / ".venv/bin/incomplete-tool").touch()
    trace.runtime()
    trace.runtime(end=True, exit_code=1)
    trace.dispatch(status="failed")
    assert "make uv-reinstall" in project.hook("stop", {}, client="codex")["reason"]


def test_other_session_cannot_replace_or_finish_reservation(project):
    payload = {**shell_payload("true", "call"), "session_id": "owner"}
    assert project.hook("pre", payload, client="codex") == {}
    impostor = {**payload, "session_id": "other"}
    assert "running" in denial(project.hook("pre", impostor, client="codex"))
    assert project.hook("post", impostor, client="codex") == {}
    next_call = shell_payload("make format", "next")
    assert "running" in denial(project.hook("pre", next_call, client="codex"))
    assert project.hook("post", payload, client="codex") == {}
    assert project.hook("pre", next_call, client="codex") == {}


def test_pre_commit_preserves_recovered_evaluation_for_stop(project, tmp_path):
    trace = Trace(tmp_path / "traces")
    project.env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace.root)
    payload = {**shell_payload("true", "call"), "session_id": "thread"}
    trace.start()
    assert project.hook("pre", payload, client="codex") == {}
    (project.root / "pyproject.toml").write_text("unauthorized = true\n")
    trace.runtime(process=None)
    trace.runtime(end=True, process=None, exit_code=-1)
    trace.dispatch(status="failed")
    project.sh(".git/hooks/pre-commit")
    assert "restored" in project.hook("stop", {}, client="codex")["reason"]
    assert project.read("pyproject.toml") == PROTECTED_CONTENT


@pytest.mark.parametrize(
    "path", ["tests/pytest.ini", "ruff.toml", "src/pkg/ruff.toml", "sub/pyproject.toml", "uv.toml", "GNUmakefile"]
)
def test_override_configuration_files_are_removed(project, path):
    _, post = project.call(f"mkdir -p $(dirname {path}) && echo '[x]' > {path}")
    assert not (project.root / path).exists()
    assert "override configuration" in post["reason"]


def test_allowlisted_dependency_target_is_accepted(project):
    _, post = project.call("make uv-add PKG=httpx")
    assert post == {}
    assert 'dep = "httpx"' in project.read("pyproject.toml")
    pre, post = project.call("true")
    assert (pre, post) == ({}, {})


def test_dependency_with_an_environment_marker_is_accepted(project):
    _, post = project.call(
        """make uv-add PKG="taplo>=0.9.3 ; platform_machine != 'aarch64' or sys_platform != 'linux'\""""
    )
    assert post == {}
    assert "platform_machine != 'aarch64' or sys_platform != 'linux'" in project.read("pyproject.toml")


@pytest.mark.parametrize(
    "command",
    [
        "make uv-add PKG=httpx && true",
        "make uv-add PKG='x; echo'",
        """make uv-add PKG="x ; os_name == '$(id)'\"""",
        """make uv-add PKG="x ; os_name == 'nt'; touch y\"""",
        "make uv-add PKG=-e",
        "make uv-add PKG=httpx EXTRA=1",
        "make -f Makefile uv-add PKG=httpx",
        "MAKEFLAGS=e make uv-add PKG=httpx",
        "make --directory . uv-add PKG=httpx",
    ],
)
def test_other_make_forms_are_not_accepted(project, command):
    pre, _ = project.call(command)
    assert pre or 'dep = "' not in project.read("pyproject.toml")
    assert project.read("pyproject.toml") == PROTECTED_CONTENT


def test_claude_make_must_run_from_the_root(project):
    payload_cwd = project.root / "src"
    project.calls += 1
    payload = {**shell_payload("make uv-add PKG=httpx", "from-src"), "cwd": str(payload_cwd)}
    project.hook("pre", payload)
    project.sh("make uv-add PKG=httpx")
    post = project.hook("post", payload)
    assert post["decision"] == "block"
    assert project.read("pyproject.toml") == PROTECTED_CONTENT


def test_codex_accepts_plain_make(project):
    _, post = project.call("make uv-add PKG=httpx", client="codex")
    assert post == {}
    assert 'dep = "httpx"' in project.read("pyproject.toml")


def test_codex_make_is_not_accepted_with_another_makefile(project):
    (project.root / "src" / "Makefile").write_text("uv-add:\n\techo hijacked >> ../pyproject.toml\n")
    project.sh("git add -A && git commit -q -m sub-makefile")
    _, post = project.call("make uv-add PKG=httpx", client="codex")
    assert post["decision"] == "block"
    assert project.read("pyproject.toml") == PROTECTED_CONTENT


def test_background_allowlisted_target_is_refused(project):
    pre, _ = project.call("make uv-add PKG=httpx", extra={"run_in_background": True})
    assert "foreground" in denial(pre)


def test_plain_commit_accepts_pre_commit_formatting(project):
    (project.root / ".format-me").write_text("")
    _, post = project.call("git commit -q --allow-empty -m wip")
    assert post == {}
    assert project.read("pyproject.toml").endswith("# formatted\n")


def test_staged_protected_change_is_unstaged_and_restored(project):
    _, post = project.call("sed -i.bak 's/demo/other/' pyproject.toml && git add pyproject.toml")
    assert project.read("pyproject.toml") == PROTECTED_CONTENT
    assert project.sh("git diff --cached --name-only").stdout == ""
    assert "Unstaged" in post["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "echo 'x = 1' >> pyproject.toml && git commit -q -am sneak",
        "printf 'repos: []\\n' > .pre-commit-config.yaml && git add -A && git commit -q -m sneak",
        'git commit -q --allow-empty -m "$(echo sneak)"',
    ],
)
def test_commits_must_be_standalone(project, command):
    head = project.sh("git rev-parse HEAD").stdout
    pre, _ = project.call(command)
    assert "standalone" in denial(pre)
    assert project.sh("git rev-parse HEAD").stdout == head
    assert project.read("pyproject.toml") == PROTECTED_CONTENT


def test_commit_hook_rejects_unapproved_staged_content_during_an_agent_commit(project):
    payload = shell_payload("git commit -q -m sneak", "commit")
    assert project.hook("pre", payload) == {}
    project.sh("echo 'x = 1' >> pyproject.toml && git add pyproject.toml")
    result = project.sh("git commit -q -m sneak", check=False)
    assert result.returncode != 0
    assert "Unapproved protected changes are staged: pyproject.toml" in result.stderr


def test_plumbing_commit_adding_a_protected_file_blocks_further_calls(project):
    command = (
        "blob=$(printf 'allow\\n' | git hash-object -w --stdin) && "
        "tree=$(git read-tree --index-output=.git/sneak-index HEAD && "
        "GIT_INDEX_FILE=.git/sneak-index git update-index --add --cacheinfo 100644,$blob,.codex/rules/allow.rules && "
        "GIT_INDEX_FILE=.git/sneak-index git write-tree) && "
        "git update-ref HEAD $(git commit-tree $tree -p HEAD -m sneak)"
    )
    _, post = project.call(command)
    assert ".codex/rules/allow.rules" in post["reason"]
    assert "ask the user" in denial(project.call("true")[0])


def test_version_bump_commits_its_own_output(project):
    head = project.sh("git rev-parse HEAD").stdout
    pre, post = project.call("make bump-patch")
    assert (pre, post) == ({}, {})
    assert project.sh("git rev-parse HEAD").stdout != head
    assert project.sh("git show HEAD:pyproject.toml").stdout.endswith('version = "2"\n')


def test_plumbing_commit_with_protected_change_blocks_further_calls(project):
    command = (
        "blob=$(printf 'evil\\n' | git hash-object -w --stdin) && "
        "git update-index --add --cacheinfo 100644,$blob,pyproject.toml && "
        "tree=$(git write-tree) && commit=$(git commit-tree $tree -p HEAD -m sneak) && "
        "git update-ref HEAD $commit && git reset -q --hard HEAD"
    )
    _, post = project.call(command)
    assert "unapproved changes" in post["reason"]
    pre, _ = project.call("true")
    assert "ask the user" in denial(pre)


def test_stash_pop_keeps_an_approved_change(project):
    project.call("make uv-add PKG=httpx")
    project.call("git stash")
    assert project.read("pyproject.toml") == PROTECTED_CONTENT
    _, post = project.call("git stash pop")
    assert post == {}
    assert 'dep = "httpx"' in project.read("pyproject.toml")


def test_branch_switch_to_other_metadata_is_accepted(project):
    project.sh(
        "git switch -q -c other && echo 'x = 2' >> pyproject.toml && git commit -qam other && git switch -q main"
    )
    _, post = project.call("git switch other")
    assert post == {}
    assert "x = 2" in project.read("pyproject.toml")


def test_user_approved_edit_is_accepted(project):
    _, post = project.edit("pyproject.toml", 'name = "renamed"\n')
    assert post == {}
    assert project.read("pyproject.toml") == 'name = "renamed"\n'


def test_codex_patch_to_protected_file_is_denied(project):
    patch = "*** Begin Patch\n*** Update File: Makefile\n*** End Patch"
    pre = project.hook("pre", {"tool_name": "apply_patch", "tool_input": {"command": patch}}, client="codex")
    assert "ask the user" in denial(pre).lower()


@pytest.mark.parametrize(
    "command",
    [
        "git commit --no-verify -m x",
        "git commit -nm x",
        "git push --no-verify",
        "SKIP=lint git commit -m x",
        "git -c core.hooksPath=/tmp git commit -m x",
        "git config core.hooksPath /dev/null",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath git commit",
        "PYTEST_ADDOPTS='-p no:cov' make test",
        "COVERAGE_RCFILE=x make test",
        "make -C src test",
        "pre-commit uninstall",
        f"/usr/bin/python3 {GUARD} --event accept",
        "echo '{}' > .git/protected-baseline/state.json",
        "make uv-add PKG=httpx guard-accept-changes",
        "make X=1 guard-accept-changes",
        "make uv-add PKG=x bump-patch",
        "bash -c 'make guard-accept-changes'",
    ],
)
def test_switch_off_commands_are_refused(project, command):
    pre, _ = project.call(command)
    assert denial(pre).startswith("Refused")


@pytest.mark.parametrize(
    "command",
    [
        "git commit --amend -m x",
        "cat scripts/hooks/guard_config.py",
        "make test",
        "rg guard-accept-changes docs",
        "git log --grep commit",
        "cat > notes.md <<'EOF'\nscripts/hooks/guard_config.py runs with python3\nEOF",
        "rg -n 'make --directory|core.hooksPath' docs",
        'git commit -q --allow-empty -m "explain the -n flag"',
        "cat > notes.md <<'EOF'\nnever run git commit --no-verify or SKIP=x\nEOF",
    ],
)
def test_ordinary_commands_are_not_refused(project, command):
    pre = project.hook("pre", shell_payload(command, "x"))
    assert pre == {}


def test_change_outside_a_call_needs_the_user(project):
    project.call("true")
    (project.root / "pyproject.toml").write_text('name = "user edit"\n')
    pre, _ = project.call("true")
    assert "ask the user" in denial(pre)
    pre, post = project.call("make guard-accept-changes")
    assert (pre, post) == ({}, {})
    assert project.call("true") == ({}, {})
    assert project.read("pyproject.toml") == 'name = "user edit"\n'


def test_accepted_change_can_be_committed(project):
    project.call("true")
    (project.root / "pyproject.toml").write_text('name = "user edit"\n')
    project.call("make guard-accept-changes")
    _, post = project.call("git commit -q -m keep -- pyproject.toml")
    assert post == {}
    assert project.sh("git show HEAD:pyproject.toml").stdout == 'name = "user edit"\n'


def test_first_run_with_uncommitted_metadata_asks(project):
    (project.root / "uv.lock").write_text("changed\n")
    pre, _ = project.call("true")
    assert "first run" in denial(pre)


def test_accept_records_nothing_before_the_user_approves(project):
    """Claude runs PreToolUse before its permission prompt; a denied accept must change nothing."""
    (project.root / "uv.lock").write_text("changed\n")
    payload = shell_payload("make guard-accept-changes", "denied")
    assert project.hook("pre", payload) == {}
    pre, _ = project.call("true")
    assert "first run" in denial(pre)


def test_tampered_venv_must_be_rebuilt(project):
    _, post = project.call("touch .venv/lib/python3.13/site-packages/evil.pth")
    assert ".venv" in post["reason"]
    pre, _ = project.call("true")
    assert "uv-reinstall" in denial(pre)
    pre, post = project.call("make uv-reinstall")
    assert (pre, post) == ({}, {})
    assert project.call("true") == ({}, {})


def test_project_targets_may_sync_the_venv(project):
    assert project.call("make test") == ({}, {})
    _, post = project.call("python3 -c \"open('.venv/bin/planted', 'w')\"")
    assert ".venv" in post["reason"]


def test_hand_edited_git_hook_is_restored(project):
    hook = project.root / ".git" / "hooks" / "pre-commit"
    original = hook.read_text()
    _, post = project.call("printf '#!/bin/sh\\nexit 0\\n' > .git/hooks/pre-commit")
    assert hook.read_text() == original
    assert "Git hooks" in post["reason"]


def test_monitor_write_is_restored(project):
    _, post = project.call("echo x >> Makefile", tool="Monitor")
    assert post["decision"] == "block"
    assert "x\n" not in project.read("Makefile")


def test_parallel_calls_defer_the_check_to_the_last_one(project):
    first = shell_payload("sleep 1", "first")
    second = shell_payload("echo x >> uv.lock", "second")
    assert project.hook("pre", first) == {}
    assert project.hook("pre", second) == {}
    project.sh("echo x >> uv.lock")
    assert project.hook("post", second) == {}
    assert project.read("uv.lock") != "version = 1\n"
    assert project.hook("post", first)["decision"] == "block"
    assert project.read("uv.lock") == "version = 1\n"


def test_exclusive_call_runs_alone(project):
    running = shell_payload("make uv-add PKG=x", "running")
    assert project.hook("pre", running) == {}
    other = shell_payload("ls", "other")
    assert "Retry" in denial(project.hook("pre", other))


def test_denied_call_does_not_keep_others_waiting(project, tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("")
    denied = {**shell_payload("git switch other", "denied"), "transcript_path": str(transcript)}
    assert project.hook("pre", denied) == {}
    result = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "denied"}]}}
    transcript.write_text(json.dumps(result) + "\n")
    assert project.call("ls") == ({}, {})


def test_stop_reports_drift_once(project):
    project.call("true")
    (project.root / "pyproject.toml").write_text("late write\n")
    assert project.hook("stop", {})["decision"] == "block"
    assert "pyproject.toml" in project.hook("stop", {"stop_hook_active": True})["systemMessage"]


def test_config_change_blocks_disable_all_hooks(project, tmp_path):
    local = project.root / ".claude" / "settings.local.json"
    local.parent.mkdir()
    local.write_text(json.dumps({"disableAllHooks": True, "theme": "dark"}))
    output = project.hook("config-change", {"source": "local_settings", "file_path": str(local)})
    assert output["decision"] == "block"
    assert json.loads(local.read_text()) == {"theme": "dark"}
    assert project.hook("config-change", {"source": "local_settings", "file_path": str(local)}) == {}


def test_config_change_keeps_the_guard_in_project_settings(project):
    settings = project.root / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text("{}")
    assert project.hook("config-change", {"source": "project_settings"})["decision"] == "block"
    events = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "ConfigChange", "Stop")
    command = {"hooks": [{"type": "command", "command": "python3 scripts/hooks/guard_config.py"}]}
    settings.write_text(json.dumps({"hooks": {event: [command] for event in events}}))
    assert project.hook("config-change", {"source": "project_settings"}) == {}


def test_codex_user_config_disabling_hooks_is_restored(project):
    config = Path(project.env["CODEX_HOME"]) / "config.toml"
    project.call("true")
    _, post = project.call(f"printf '[features]\\nhooks = false\\n' >> {config}")
    assert "hooks = false" not in config.read_text()
    assert "switch the project's hooks off" in post["reason"]
    config.write_text('model = "user choice"\n')
    assert project.call("true") == ({}, {})
    assert config.read_text() == 'model = "user choice"\n'


def test_each_worktree_has_its_own_baseline(project, tmp_path):
    other = tmp_path / "linked"
    project.sh(f"git worktree add -q -b linked {other}")
    project.call("true")
    linked = Project(other, Path(project.env["CODEX_HOME"]))
    linked.env = project.env
    (other / ".venv/bin").mkdir(parents=True)
    linked.call("true")
    _, post = linked.call("echo x >> pyproject.toml")
    assert post["decision"] == "block"
    assert (project.root / ".git" / "worktrees" / "linked" / "protected-baseline" / "state.json").is_file()


@pytest.mark.parametrize("raw", ["not json", "[]", '{"tool_input": null}'])
def test_invalid_hook_input_blocks(project, raw):
    result = subprocess.run(
        [sys.executable, str(GUARD), "--client", "claude", "--event", "pre"],
        input=raw,
        cwd=project.root,
        env=project.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_a_failing_stop_check_does_not_block_the_turn(project):
    # Exit 2 at Stop would re-prompt the agent every turn while the error lasts.
    result = subprocess.run(
        [sys.executable, str(GUARD), "--client", "claude", "--event", "stop"],
        input="not json",
        cwd=project.root,
        env=project.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "cannot evaluate" in result.stderr


@pytest.mark.parametrize(("age_minutes", "still_running"), [(30, True), (61, False)])
def test_running_calls_expire_after_an_hour(project, age_minutes, still_running):
    project.call("true")
    state_file = project.root / ".git" / "protected-baseline" / "state.json"
    state = json.loads(state_file.read_text())
    started = time.time() - age_minutes * 60
    state["inflight"]["long"] = {"started": started, "exclusive": True, "transcript": None}
    state_file.write_text(json.dumps(state))
    pre, _ = project.call("ls")
    assert ("Retry" in denial(pre)) is still_running


def test_hook_mode_change_is_restored(project):
    hook = project.root / ".git" / "hooks" / "pre-commit"
    _, post = project.call("chmod -x .git/hooks/pre-commit")
    assert hook.stat().st_mode & 0o777 == 0o755
    assert "Git hooks" in post["reason"]


def test_codex_make_is_not_accepted_with_a_makefile_in_build_output(project):
    (project.root / "build").mkdir()
    (project.root / "build" / "Makefile").write_text("format:\n\techo hijacked >> ../pyproject.toml\n")
    _, post = project.call("make format", client="codex")
    assert post["decision"] == "block"
    assert project.read("pyproject.toml") == PROTECTED_CONTENT


def test_conflicted_merge_is_held_for_the_user(project):
    project.sh(
        "git switch -q -c other && printf 'name = \"other\"\\n' > pyproject.toml && git commit -qam other && "
        "git switch -q main && printf 'name = \"main\"\\n' > pyproject.toml && git commit -qam main"
    )
    _, post = project.call("git merge other")
    assert "<<<<<<<" in project.read("pyproject.toml")
    assert "resolve them" in post["hookSpecificOutput"]["additionalContext"]
    assert "resolve them" in denial(project.call("true")[0])


def test_nested_worktree_keeps_its_files(project):
    pre, post = project.call("git worktree add -q -b linked .worktrees/linked")
    assert (pre, post) == ({}, {})
    assert (project.root / ".worktrees" / "linked" / "pyproject.toml").is_file()
    assert project.call("true") == ({}, {})


def test_denied_call_does_not_strand_a_parallel_write(project, tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("")
    denied = {**shell_payload("sleep 5", "denied"), "transcript_path": str(transcript)}
    writer = shell_payload("echo x >> uv.lock", "writer")
    assert project.hook("pre", denied) == {}
    assert project.hook("pre", writer) == {}
    project.sh("echo x >> uv.lock")
    assert project.hook("post", writer) == {}
    result = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "denied"}]}}
    transcript.write_text(json.dumps(result) + "\n")
    pre, _ = project.call("ls")
    assert "uv.lock" in denial(pre)
    assert project.read("uv.lock") == "version = 1\n"


def test_writes_inside_protected_directories_are_restored(project):
    _, post = project.call("echo 'VALUE = 2' > scripts/hooks/helper.py && echo allow > .codex/rules/allow.rules")
    assert project.read("scripts/hooks/helper.py") == "VALUE = 1\n"
    assert not (project.root / ".codex" / "rules" / "allow.rules").exists()
    assert "scripts/hooks/helper.py" in post["reason"]


def test_symlinked_protected_file_is_replaced_by_its_content(project):
    project.call("rm AGENTS.md && ln -s src/app.py AGENTS.md")
    assert not (project.root / "AGENTS.md").is_symlink()
    assert project.read("AGENTS.md") == "# Rules\n"
