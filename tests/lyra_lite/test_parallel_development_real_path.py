"""Real daemon -> development lead -> simultaneous workers -> real Git merge."""
import json
import threading

import pytest

from lyra_lite.development import git
from lyra_lite.store import ProjectStore
from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import (  # noqa: F401
    Daemon, _events, _new_project, _wait_event, _write_config, env,
)


@pytest.mark.parametrize("workers,limit", [(1, 10), (2, 10), (3, 10), (5, 10), (9, 10), (14, 15)])
def test_developer_fans_out_and_integrates_relative_file_and_terminal_work(env, workers, limit):
    letters = [chr(ord("A") + i) for i in range(workers)]
    lead = "sw-developer: DEV-LEAD implement independent modules"
    tasks = [{"goal": f"CODE-{letter}: implement module", "context": json.dumps({
        "owned_paths": [f"{letter}.txt"], "instructions": "Implement this module and check the result.",
    })} for letter in letters]
    barrier = threading.Barrier(workers, timeout=60)
    with FakeOpenAIServer([], side_scripts={
        "DEV-LEAD": [tool_step("delegate_task", {"tasks": tasks}), text_step("Lead integrated the coding work.")],
        **{f"CODE-{letter}": [
            {**tool_step("terminal", {"command": "pwd"}), "worker_barrier": True},
            tool_step("write_file", {"path": f"{letter}.txt", "content": f"Module {letter}\n"}, call_id="write"),
            text_step(f"Module {letter} implemented."),
        ] for letter in letters},
    }) as llm:
        next_step = llm.next_step

        def simultaneous(body):
            step = next_step(body)
            if step.get("worker_barrier"):
                barrier.wait()
            return step

        llm.next_step = simultaneous
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={"watchdog": {"enabled": False}, "parallel_work": {"max_workers": limit}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, "Parallel coding")
            git(root, "init")
            (root / "contract.txt").write_text("Stable shared contract\n")
            git(root, "add", "contract.txt")
            git(root, "commit", "-m", "Initial contract")
            llm.script = [tool_step("delegate_task", {"goal": lead}), text_step("Development is running."),
                          text_step("Development report received.")]
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Build the modules"}).is_success
            _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "Development report received.", 120)
            for letter in letters:
                assert (root / f"{letter}.txt").read_text() == f"Module {letter}\n"
            wave = next((root / ".lyra/development").iterdir())
            metadata = json.loads((wave / "wave.json").read_text())
            assert metadata["integrated"]
            assert len({r["workspace"] for r in metadata["workers"]}) == workers
            assert (root / "contract.txt").read_text() == "Stable shared contract\n"
            requests = llm.main_requests()
            # Request routing is also validated by the actual output files;
            # inspect all requests for terminal results rather than assume
            # that a provider inserts the goal at a fixed message index.
            terminal_outputs = [str(m.get("content", "")) for r in requests for m in r["messages"]
                                if m.get("role") == "tool" and "worker-" in str(m.get("content", ""))]
            assert all(any(f"worker-{i}" in output for output in terminal_outputs) for i in range(workers))
            worker_starts = [e for e in _events(root) if e["type"] == "helper" and e.get("event") == "start"
                             and e.get("goal", "").startswith("CODE-")]
            assert len(worker_starts) == workers and all(e.get("parent_id") for e in worker_starts)
            # Actual leaf file/terminal callbacks must survive the lead relay
            # with each worker's identity, not disappear behind delegate_task.
            for worker in worker_starts:
                tools = [e for e in _events(root) if e["type"] == "helper" and e.get("event") == "tool"
                         and e.get("subagent_id") == worker["subagent_id"]]
                assert {e.get("tool") for e in tools} >= {"terminal", "write_file"}
                assert all(e.get("parent_id") == worker["parent_id"] for e in tools)
            for request in requests:
                first_user = next((str(m.get("content", "")) for m in request["messages"] if m["role"] == "user"), "")
                names = {t["function"]["name"] for t in request.get("tools", [])}
                if first_user.startswith("CODE-"):
                    assert "delegate_task" not in names
                elif first_user.startswith("sw-developer:"):
                    assert "delegate_task" in names
                    schema = next(t["function"] for t in request["tools"] if t["function"]["name"] == "delegate_task")
                    assert "max_spawn_depth=2" in schema["description"]
                    assert f"array with up to {limit} " in schema["description"]
                    assert f"up to {limit} for" in schema["parameters"]["properties"]["tasks"]["description"]
            # Each conversation's schema and system prompt stay byte-stable,
            # including the coordinator while its children are constructed.
            prefixes = {}
            for request in requests:
                first = next(str(m.get("content", "")) for m in request["messages"] if m["role"] == "user")
                prefix = (request["tools"], [m for m in request["messages"] if m["role"] == "system"])
                assert prefixes.setdefault(first, prefix) == prefix
            plans = [e for e in _events(root) if e["type"] == "worker_plan"]
            assert len(plans) == 1 and plans[0]["workers"] == workers and plans[0]["reason"]
            assert plans[0]["total_workers"] == workers + 1
            assert daemon.get("/api/settings").json()["parallel_work"]["active"] == 0
            assert not [e for e in _events(root) if e["type"] == "turn_end" and e.get("status") == "error"]
        finally:
            daemon.stop()


def test_status_note_does_not_call_or_interrupt_a_waiting_model(env):
    release = threading.Event()
    entered = threading.Event()
    with FakeOpenAIServer([text_step("Ready after waiting.")]) as llm:
        next_step = llm.next_step

        def wait_for_release(body):
            step = next_step(body)
            if body.get("tools"):
                entered.set()
                assert release.wait(45)
            return step

        llm.next_step = wait_for_release
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={
            "watchdog": {"enabled": False, "check_seconds": 0.05},
            "status_updates": {"interval_seconds": 0.1},
        })
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, "Waiting model")
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Please work"}).is_success
            assert entered.wait(30), "The model request never arrived"
            _wait_event(root, lambda e: e["type"] == "status_update", 30)
            detail = daemon.get(f"/api/projects/{pid}").json()
            assert detail["running"]
            assert any(m["kind"] == "status" for m in detail["messages"])
            assert len(llm.main_requests()) == 1
            assert ProjectStore(root).messages() == []
            release.set()
            _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "Ready after waiting.")
            assert not any(m.get("kind") == "status" for m in ProjectStore(root).messages())
            assert "Status update:" not in json.dumps(ProjectStore(root).messages())
            assert len(llm.main_requests()) == 1
        finally:
            release.set()
            daemon.stop()


def test_stop_reaches_nested_workers_and_prevents_integration(env):
    letters = ["A", "B"]
    release = threading.Event()
    both_started = threading.Event()
    seen = set()
    guard = threading.Lock()
    tasks = [{"goal": f"STOP-{letter}", "context": json.dumps({"owned_paths": [f"{letter}.txt"]})}
             for letter in letters]
    with FakeOpenAIServer([], side_scripts={
        "STOP-LEAD": [tool_step("delegate_task", {"tasks": tasks}), text_step("Stopped development.")],
        **{f"STOP-{letter}": [tool_step("write_file", {"path": f"{letter}.txt", "content": "partial"})]
           for letter in letters},
    }) as llm:
        next_step = llm.next_step

        def gated(body):
            step = next_step(body)
            first = next((str(m.get("content", "")) for m in body.get("messages", []) if m["role"] == "user"), "")
            if first in {"STOP-A", "STOP-B"}:
                with guard:
                    seen.add(first)
                    if len(seen) == 2:
                        both_started.set()
                assert release.wait(45)
            return step

        llm.next_step = gated
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={"watchdog": {"enabled": False}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, "Stop nested coding")
            git(root, "init")
            (root / "contract.txt").write_text("stable")
            git(root, "add", "contract.txt")
            git(root, "commit", "-m", "Initial")
            llm.script = [tool_step("delegate_task", {"goal": "sw-developer: STOP-LEAD"}), text_step("Working.")]
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Build"}).is_success
            assert both_started.wait(45), "Both nested workers did not start"
            assert daemon.post(f"/api/projects/{pid}/stop", {}).is_success
            release.set()
            _wait_event(root, lambda e: e["type"] == "helper" and e.get("event") == "complete"
                        and e.get("goal") == "sw-developer: STOP-LEAD", 60)
            assert not (root / "A.txt").exists() and not (root / "B.txt").exists()
            assert (root / "contract.txt").read_text() == "stable"
            assert daemon.get(f"/api/projects/{pid}").json()["paused"]
            wave = next((root / ".lyra/development").iterdir())
            assert "integrated" not in json.loads((wave / "wave.json").read_text())
        finally:
            release.set()
            daemon.stop()


@pytest.mark.parametrize("workers", [1, 3, 5])
def test_qa_read_only_workers_keep_the_selected_role_provider_and_model(env, workers):
    tasks = [{"goal": f"READ-{n}", "context": json.dumps({
        "read_only": True, "instructions": "Read the contract and return findings without editing files."
    })} for n in range(workers)]
    barrier = threading.Barrier(workers, timeout=30)
    with FakeOpenAIServer([]) as coordinator, FakeOpenAIServer([], side_scripts={
        "QA-LEAD": [tool_step("delegate_task", {"tasks": tasks,
            "context": f"One QA lead plus {workers} independent read-only contract checks."}),
            text_step("QA findings consolidated.")],
        **{f"READ-{n}": [{**tool_step("read_file", {"path": "contract.txt"}), "worker_barrier": True},
                         text_step("Contract checked; no modifications.")] for n in range(workers)},
    }) as role_provider:
        next_step = role_provider.next_step
        def simultaneous(body):
            step = next_step(body)
            if step.get("worker_barrier"):
                barrier.wait()
            return step
        role_provider.next_step = simultaneous
        _write_config(env["hermes_home"], coordinator.base_url,
            custom_providers=[{"name": "QA", "base_url": role_provider.base_url, "api_key": "role-key"}],
            delegation={"model": "wrong-global-delegation-model"},
            lyra_lite={"watchdog": {"enabled": False}, "agent_models": {
                "qa-engineer": {"provider": "custom:qa", "model": "selected-qa-model", "effort": "off"}}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, "Independent QA")
            git(root, "init")
            (root / "contract.txt").write_text("Stable shared contract\n")
            git(root, "add", "contract.txt")
            git(root, "commit", "-m", "Saved QA baseline")
            baseline = git(root, "rev-parse", "HEAD")
            before = daemon.get("/api/settings").json()
            assert daemon.post("/api/settings", {"parallel_work": {"max_workers": 15}}).is_success
            assert daemon.post("/api/settings", {"parallel_work": {"max_workers": 16}}).status_code == 400
            after = daemon.get("/api/settings").json()
            assert after["hermes"] == before["hermes"]
            assert after["agent_models"] == before["agent_models"]
            coordinator.script = [tool_step("delegate_task", {"goal": "qa-engineer: QA-LEAD verify saved contract"}),
                                  text_step("QA is working."), text_step("QA report received.")]
            assert daemon.post(f"/api/projects/{pid}/messages", {"text": "Verify the contract"}).is_success
            _wait_event(root, lambda e: e["type"] == "turn_end" and e.get("reply") == "QA report received.", 90)
            assert git(root, "rev-parse", "HEAD") == baseline
            wave = next((root / ".lyra/development").iterdir())
            meta = json.loads((wave / "wave.json").read_text())
            assert meta["validated_baseline"] == baseline
            assert all(r["read_only"] for r in meta["workers"])
            assert all(r["model"] == "selected-qa-model" for r in role_provider.main_requests())
            assert all(r["model"] == "fake-model" for r in coordinator.main_requests())
            assert len([e for e in _events(root) if e["type"] == "helper" and e.get("event") == "start"
                        and e.get("goal", "").startswith("READ-")]) == workers
        finally:
            daemon.stop()


def test_planner_receives_worker_contract_without_implementation_permission(env):
    from lyra_lite.development import PLANNING_CONTEXT

    with FakeOpenAIServer([], side_scripts={
        'PACKAGE-PLAN': [text_step('Worker packages planned; no implementation started.')],
    }) as llm:
        _write_config(env['hermes_home'], llm.base_url,
                      lyra_lite={'watchdog': {'enabled': False}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, 'Worker package planning')
            llm.script = [tool_step('delegate_task', {
                'goal': 'task-planner: PACKAGE-PLAN',
                'context': 'Preserve this approved boundary: local files only.',
            }), text_step('Planning is running.'), text_step('Plan received.')]
            assert daemon.post(f'/api/projects/{pid}/messages', {'text': 'Plan worker packages'}).is_success
            _wait_event(root, lambda e: e['type'] == 'turn_end' and e.get('reply') == 'Plan received.', 60)
            requests = [r for r in llm.main_requests() if any(
                m.get('role') == 'user' and str(m.get('content', '')).startswith('task-planner:')
                for m in r['messages'])]
            assert requests
            for request in requests:
                context = '\n'.join(str(m.get('content', '')) for m in request['messages'])
                # A transport assertion, not a snapshot of the policy wording:
                # the complete current contract and owner scope reach the planner.
                assert PLANNING_CONTEXT in context
                assert 'Preserve this approved boundary: local files only.' in context
                assert 'delegate_task' not in {t['function']['name'] for t in request['tools']}
            assert not [e for e in _events(root) if e['type'] == 'worker_plan']
        finally:
            daemon.stop()


@pytest.mark.parametrize('role', ['sw-developer', 'researcher', 'code-reviewer'])
def test_role_can_choose_direct_execution_without_forced_workers(env, role):
    leaf_step = (tool_step('write_file', {'path': 'small-fix.txt', 'content': 'Fixed directly.\n'})
                 if role == 'sw-developer' else tool_step('read_file', {'path': 'contract.txt'}))
    with FakeOpenAIServer([], side_scripts={
        'DIRECT-LEAD': [leaf_step, text_step('Small assignment completed directly; worker startup would cost more.')],
    }) as llm:
        _write_config(env['hermes_home'], llm.base_url,
                      lyra_lite={'watchdog': {'enabled': False}, 'parallel_work': {'max_workers': 15}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, 'Small direct task')
            (root / 'contract.txt').write_text('Approved stable contract.\n')
            llm.script = [tool_step('delegate_task', {'goal': f'{role}: DIRECT-LEAD small scoped assignment'}),
                          text_step('Working.'), text_step('Direct assignment report received.')]
            assert daemon.post(f'/api/projects/{pid}/messages', {'text': 'Complete the small assignment'}).is_success
            _wait_event(root, lambda e: e['type'] == 'turn_end'
                        and e.get('reply') == 'Direct assignment report received.', 60)
            events = _events(root)
            assert not [e for e in events if e['type'] == 'worker_plan']
            assert not [e for e in events if e['type'] == 'helper' and e.get('parent_id')]
            if role == 'sw-developer':
                assert (root / 'small-fix.txt').read_text() == 'Fixed directly.\n'
            assert (root / 'contract.txt').read_text() == 'Approved stable contract.\n'
            assert daemon.get('/api/settings').json()['parallel_work']['active'] == 0
            assert not [e for e in events if e['type'] == 'turn_end' and e.get('status') == 'error']
        finally:
            daemon.stop()
