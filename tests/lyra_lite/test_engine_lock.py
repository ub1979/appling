"""Hermes-only project state and safe handling of older installations."""
import json
import os

import pytest
import yaml

from lyra_lite.settings import effective_engine, migrate_engine_settings, save_section
from lyra_lite.store import ProjectStore


def _legacy(tmp_path, **state):
    store = ProjectStore(tmp_path / 'legacy')
    store.dir.mkdir(parents=True)
    store.state_path.write_text(json.dumps({
        'chat_id': 'original-chat', 'running': False, 'queue': [],
        'engine': 'claude', 'engine_locked': True, **state,
    }))
    return store


@pytest.mark.parametrize('default', ['hermes', 'claude'])
def test_new_projects_always_use_hermes(tmp_path, default):
    save_section({'engine': default})
    store = ProjectStore(tmp_path / 'new').init()
    assert effective_engine(store.state()) == 'hermes'
    assert store.state()['engine_locked']
    assert not store.state().get('paused')
    assert not (store.dir / 'migrations').exists()


@pytest.mark.parametrize('legacy', [
    {'engine': 'claude', 'engine_locked': True},
    {'engine': 'claude', 'engine_override': True, 'engine_locked': False},
    {'engine': None, 'engine_locked': False, 'claude_session': 'sdk-session'},
    {'engine': None, 'engine_locked': False},
])
def test_old_claude_state_is_held_without_rewriting_history(tmp_path, legacy):
    save_section({'engine': 'claude'})
    queue = [{'id': 'held', 'kind': 'helper_done', 'text': 'QA has finished'}]
    store = _legacy(tmp_path, **legacy, queue=queue, claude={'auth_token': 'private'},
                    claude_chat='sdk-chat', rules_hash='old-rules', focus_hash='old-focus')
    original = store.state_path.read_bytes()
    store.save_messages([{'role': 'user', 'content': 'Build this'}, {'role': 'assistant', 'content': 'Done'}])
    store.write_transcript(store.messages())
    messages, transcript = store.messages_path.read_bytes(), store.transcript_path.read_bytes()
    store.init()
    backup = store.dir / 'migrations/claude-to-hermes/state.json'
    assert backup.read_bytes() == original
    if os.name != 'nt':
        assert backup.stat().st_mode & 0o077 == 0
    state = store.state()
    assert state['engine'] == 'hermes' and state['engine_locked'] and state['paused']
    assert state['chat_id'] == 'original-chat' and state['queue'] == queue
    assert not {'claude', 'claude_session', 'claude_chat', 'engine_override'} & state.keys()
    assert state['rules_hash'] == '' and state['focus_hash'] is None
    assert store.messages_path.read_bytes() == messages
    assert store.transcript_path.read_bytes() == transcript
    store.update_state(paused=False)
    migrated = store.state_path.read_bytes()
    store.init()
    assert store.state_path.read_bytes() == migrated
    assert backup.read_bytes() == original


def test_existing_hermes_project_is_unchanged(tmp_path):
    store = _legacy(tmp_path, engine='hermes', paused=False, rules_hash='current', focus_hash='current')
    original = store.state_path.read_bytes()
    save_section({'engine': 'claude'})
    store.init()
    assert store.state_path.read_bytes() == original
    assert not (store.dir / 'migrations').exists()


def test_failed_backup_cannot_convert_or_resume_project(tmp_path, monkeypatch):
    store = _legacy(tmp_path)
    original = store.state_path.read_bytes()
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr('lyra_lite.store._backup_once', fail)
    with pytest.raises(OSError, match='disk unavailable'):
        store.init()
    assert store.state_path.read_bytes() == original


def test_retired_settings_preserve_provider_config_and_legacy_default(tmp_path):
    from hermes_cli.config import get_config_path, read_raw_config
    path = get_config_path()
    config = {'model': {'provider': 'custom', 'default': 'existing-model'},
              'lyra_lite': {'engine': 'claude', 'claude': {'auth_token': 'private'},
                            'about_me': 'Explain clearly', 'watchdog': {'enabled': False}}}
    path.write_text(yaml.safe_dump(config))
    original = path.read_bytes()
    migrate_engine_settings()
    saved = read_raw_config()
    assert saved['model'] == config['model']
    assert saved['lyra_lite'] == {'engine': 'hermes', 'legacy_engine_default': 'claude',
                                  'about_me': 'Explain clearly', 'watchdog': {'enabled': False}}
    backup = path.parent / 'lyra-lite/migrations/claude-to-hermes/config.yaml'
    assert backup.read_bytes() == original
    migrate_engine_settings()
    assert backup.read_bytes() == original
    # An old unopened project still inherits the old default for retirement;
    # a new one never does.
    old = _legacy(tmp_path, engine=None, engine_locked=False).init()
    assert old.state()['paused']
    assert not ProjectStore(tmp_path / 'new').init().state().get('paused')


def test_restart_expires_legacy_approvals_and_recovers_old_turn(tmp_path, monkeypatch):
    from lyra_lite.runner import ProjectRunner
    monkeypatch.setattr('lyra_lite.runner.checkpoint', lambda *a, **kw: None)
    store = _legacy(tmp_path, running=True,
                    turn={'id': 'old-turn', 'kind': 'user', 'text': 'Finish the build', 'started': 1})
    approval = store.add_inbox('approval', prompt='Old tool command', turn=None)
    calls = []
    runner = ProjectRunner(store, lambda *args: calls.append(args))
    try:
        assert runner.store.state()['paused'] and not runner.store.state()['running']
        assert runner.store.inbox_item(approval['id'])['status'] == 'expired'
        assert not runner.answer(approval['id'], 'once')
        assert runner.store.messages()[0]['content'] == 'Finish the build'
        assert runner.store.messages()[-1]['role'] == 'assistant'
        assert not calls
        assert any(e.get('status') == 'lost_on_restart' for e in store.read_events()[0])
    finally:
        runner.shutdown()
