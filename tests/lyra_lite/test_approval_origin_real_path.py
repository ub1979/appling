"""An actual delegated terminal wait identifies its owner and denial executes nothing."""
import shlex

from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step, tool_step
from tests.lyra_lite.test_lyrad_real_path import Daemon, _events, _new_project, _wait_event, _write_config, env  # noqa: F401


def test_delegated_command_card_identifies_planner_and_denies_command(env):
    goal = 'task-planner: Verify command approval attribution'
    with FakeOpenAIServer([]) as llm:
        _write_config(env['hermes_home'], llm.base_url, lyra_lite={'watchdog': {'enabled': False}})
        daemon = Daemon(env).start()
        try:
            pid, root = _new_project(daemon, env, 'Approval source')
            marker = root / 'keep-this-test-file.txt'
            marker.write_text('must remain untouched')
            command = 'rm -rf ' + shlex.quote(str(marker))
            llm.script = [tool_step('delegate_task', {'goal': goal}), text_step('Waiting for the command decision.'), text_step('Denied command handled.')]
            llm.side_scripts = {goal: [tool_step('terminal', {'command': command}), text_step('Command denied; no retry.')]}
            prefix = f'/api/projects/{pid}'
            assert daemon.post(prefix + '/messages', {'text': 'Run the isolated approval attribution test'}).is_success
            item = _wait_event(root, lambda e: e['type'] == 'inbox' and e['item']['kind'] in {'approval', 'scope_permission'})['item']
            worker = next(e for e in _events(root) if e['type'] == 'helper' and e.get('event') == 'start')
            assert item['requester']['subagent_id'] == worker['subagent_id']
            assert item['requester']['label'] == 'Task planning'
            assert item['requester']['goal'] == goal
            assert item['requester']['model'] == worker['model']
            assert marker.read_text() == 'must remain untouched'
            assert daemon.post(prefix + '/inbox/' + item['id'], {'answer': 'Deny' if item['kind'] == 'scope_permission' else 'deny'}).is_success
            _wait_event(root, lambda e: e['type'] == 'helper' and e.get('event') == 'reported')
            assert marker.read_text() == 'must remain untouched'
        finally:
            daemon.stop()
