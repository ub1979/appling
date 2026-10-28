"""Hermes-only APIs and old project recovery through real daemons and tools."""
from __future__ import annotations

import json
import threading

from tests.fakes.fake_openai_server import FakeOpenAIServer, _first_user_text
from tests.fakes.fake_openai_server import text_step as ht, tool_step as hc
from tests.lyra_lite.test_lyrad_real_path import (
    Daemon, _events, _new_project, _wait_event, _write_config, env,  # noqa: F401
)


class HeldHermes(FakeOpenAIServer):
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        super().__init__([])

    def next_step(self, body):
        step = super().next_step(body)
        if 'QA-WORKER' in _first_user_text(body) and step.get('tool') == 'write_file':
            self.entered.set()
            assert self.release.wait(60), 'QA worker was not released'
        return step


def _say(daemon, pid, path, text, reply):
    assert daemon.post(f'/api/projects/{pid}/messages', {'text': text}).status_code == 200
    end = _wait_event(path, lambda e: e['type'] == 'turn_end' and e.get('reply') == reply, 60)
    assert end['status'] == 'done', end
    return end


def test_old_project_waits_for_owner_then_resumes_in_hermes(env):
    with FakeOpenAIServer([ht('CONTINUED'), ht('REOPENED'), ht('NEW-CHAT')]) as hermes:
        _write_config(env['hermes_home'], hermes.base_url, lyra_lite={
            'engine': 'claude', 'claude': {'auth_token': 'retired-private'},
            'watchdog': {'enabled': False},
        })
        path = env['home'] / 'Legacy project'
        data = path / '.lyra'
        data.mkdir(parents=True)
        state = {'chat_id': 'original-chat', 'engine': 'claude', 'engine_locked': True,
                 'running': False, 'claude_session': 'retired-sdk-session',
                 'queue': [{'id': 'old-result', 'kind': 'helper_done', 'text': 'QA-ALREADY-PASSED'}]}
        (data / 'state.json').write_text(json.dumps(state))
        messages = [{'role': 'user', 'content': 'Build my app'},
                    {'role': 'assistant', 'content': 'ORIGINAL-CLAUDE-REPLY'}]
        (data / 'messages.jsonl').write_text(''.join(json.dumps(m) + '\n' for m in messages))
        (data / 'transcript.jsonl').write_bytes((data / 'messages.jsonl').read_bytes())
        registry = env['hermes_home'] / 'lyra-lite/projects.json'
        registry.parent.mkdir(exist_ok=True)
        registry.write_text(json.dumps({'projects': [str(path)]}))
        daemon = Daemon(env).start()
        try:
            pid = daemon.get('/api/projects').json()['projects'][0]['id']
            detail = daemon.get(f'/api/projects/{pid}').json()
            assert detail['engine'] == 'hermes' and detail['paused'] and not detail['running']
            assert not hermes.main_requests()
            assert 'ORIGINAL-CLAUDE-REPLY' in json.dumps(detail['messages'])
            settings = daemon.get('/api/settings').json()
            assert settings['engine'] == 'hermes' and 'claude' not in settings
            assert 'retired-private' not in json.dumps(settings)
            assert [e['id'] for e in daemon.get('/api/engines').json()['engines']] == ['hermes']
            for payload in ({'engine': 'claude'}, {'claude': {'model': 'old-model'}}):
                assert daemon.post('/api/settings', payload).status_code == 400
                assert daemon.post(f'/api/projects/{pid}/settings', payload).status_code == 400
            retired = daemon.get('/api/settings/claude-cli')
            # Unknown paths use the existing SPA fallback when the UI is built.
            assert retired.status_code == 404 or 'text/html' in retired.headers.get('content-type', '')
            _say(daemon, pid, path, 'Report status only', 'CONTINUED')
            first = json.dumps(hermes.main_requests()[0]['messages'])
            assert 'ORIGINAL-CLAUDE-REPLY' in first and 'QA-ALREADY-PASSED' in first
            assert len(hermes.main_requests()) == 1
            backup = (data / 'migrations/claude-to-hermes/state.json').read_bytes()
            daemon.stop()
            daemon = Daemon(env).start()
            _say(daemon, pid, path, 'Check again', 'REOPENED')
            assert 'CONTINUED' in json.dumps(hermes.main_requests()[-1]['messages'])
            assert (data / 'migrations/claude-to-hermes/state.json').read_bytes() == backup
            assert daemon.post(f'/api/projects/{pid}/new-chat', {}).status_code == 200
            _say(daemon, pid, path, 'Hello', 'NEW-CHAT')
            assert 'ORIGINAL-CLAUDE-REPLY' not in json.dumps(hermes.main_requests()[-1]['messages'])
            new_pid, _ = _new_project(daemon, env, 'New Hermes project')
            new = daemon.get(f'/api/projects/{new_pid}').json()
            assert new['engine'] == 'hermes' and not new['paused']
        finally:
            daemon.stop()


def test_rejected_claude_setting_keeps_qa_visible_and_delivers_once(env):
    with HeldHermes() as hermes:
        _write_config(env['hermes_home'], hermes.base_url)
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env, 'QA continuity')
            target = path / 'qa-result.md'
            goal = f'QA-WORKER: independently verify the repaired feature; write PASS to {target}.'
            hermes.script = [hc('delegate_task', {'goal': goal, 'context': 'Build profile: reusable.',
                                                'background': True}), ht('STARTED'), ht('STILL-RUNNING'), ht('QA-COMPLETE')]
            hermes.side_scripts = {'QA-WORKER': [hc('write_file', {'path': str(target), 'content': 'PASS'}), ht('QA PASS')]}
            _say(daemon, pid, path, 'start QA', 'STARTED')
            assert hermes.entered.wait(15)
            before = daemon.get(f'/api/projects/{pid}').json()
            assert len(before['helpers']) == 1
            assert daemon.post(f'/api/projects/{pid}/settings', {'engine': 'claude'}).status_code == 400
            assert daemon.post('/api/settings', {'engine': 'claude'}).status_code == 400
            _say(daemon, pid, path, 'try now', 'STILL-RUNNING')
            after = daemon.get(f'/api/projects/{pid}').json()
            assert after['helpers'] == before['helpers'] and not target.exists()
            hermes.release.set()
            _wait_event(path, lambda e: e['type'] == 'turn_end' and e.get('reply') == 'QA-COMPLETE', 60)
            assert target.read_text() == 'PASS'
            assert daemon.get(f'/api/projects/{pid}').json()['helpers'] == []
            events = _events(path)
            assert len([e for e in events if e['type'] == 'helper' and e['event'] == 'start']) == 1
            assert len([e for e in events if e['type'] == 'turn_start' and e.get('kind') == 'helper_done']) == 1
        finally:
            hermes.release.set()
            daemon.stop()
