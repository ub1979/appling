"""Configuration isolation, migration recovery and native worker safety."""
import base64
import json
from pathlib import Path

import pytest

from lyra_lite import review, settings
from lyra_lite.store import ProjectStore
from lyra_lite.engines.codex import CodexEngine
from lyra_lite.engines.codex_jobs import _review_guard, dispatch
from lyra_lite.development import git


def test_codex_settings_do_not_read_or_write_hermes(tmp_path, monkeypatch):
    legacy = tmp_path / 'hermes'
    legacy.mkdir()
    path = legacy / 'config.yaml'
    original = b'model:\n  default: do-not-change\n'
    path.write_bytes(original)
    monkeypatch.setenv('HERMES_HOME', str(legacy))
    settings.set_codex_model('codex', 'test-model')
    settings.set_codex_effort('medium')
    settings.save_agent_model('sw-developer', {'provider': 'codex', 'model': 'coding-model', 'effort': 'high'})
    assert settings.resolve_agent_model('sw-developer', settings.agent_model_overrides(), {})['model'] == 'coding-model'
    settings.save_agent_model('sw-developer', None)
    assert settings.resolve_agent_model('sw-developer', settings.agent_model_overrides(), {})['model'] == 'test-model'
    assert path.read_bytes() == original
    assert list(legacy.iterdir()) == [path]
    with pytest.raises(ValueError):
        settings.set_codex_model('anthropic', 'test-model')


def test_legacy_project_backup_preserves_queue_messages_and_approvals(tmp_path):
    store = ProjectStore(tmp_path).init()
    store.save_messages([{'role': 'user', 'content': 'Keep this feedback'}])
    old = {'engine': 'hermes', 'chat_id': 'old-chat', 'queue': [{'text': 'Feedback'}],
           'requirements_approved': 'approved-hash', 'running': False}
    store.state_path.write_text(json.dumps(old))
    original = store.state_path.read_bytes()
    messages = store.messages_path.read_bytes()
    store.init()
    assert (store.dir / 'migrations/before-codex/state.json').read_bytes() == original
    assert store.messages_path.read_bytes() == messages
    current = store.state()
    assert current['engine'] == 'codex' and current['paused']
    assert current['queue'] == old['queue'] and current['requirements_approved'] == old['requirements_approved']


def test_running_legacy_project_is_not_migrated(tmp_path):
    store = ProjectStore(tmp_path).init()
    store.update_state(engine='hermes', running=True)
    original = store.state_path.read_bytes()
    with pytest.raises(ValueError, match='still running'):
        store.init()
    assert store.state_path.read_bytes() == original
    assert not (store.dir / 'migrations/before-codex').exists()


def test_plan_gate_allows_engineering_updates_only_after_real_execution(tmp_path):
    store = ProjectStore(tmp_path).init()
    (tmp_path / 'requirements.md').write_text('# Requirements\nPreserve data.\n')
    (tmp_path / 'plan.md').write_text('# Plan\nImplement safely.\n')
    requirements = review.requirements_revision(tmp_path)
    plan = review.implementation_plan(tmp_path)['revision']
    store.update_state(requirements_approved=requirements, plan_approved=plan, plan_requirements=requirements)
    _review_guard(store, ['sw-developer'])
    (tmp_path / 'plan.md').write_text('# Plan\nUnapproved new plan.\n')
    with pytest.raises(ValueError, match='Approve the current implementation plan'):
        _review_guard(store, ['sw-developer'])
    store.update_state(plan_execution={'requirements': requirements, 'plan': plan})
    _review_guard(store, ['sw-developer'])
    (tmp_path / 'requirements.md').write_text('# Requirements\nChanged scope.\n')
    with pytest.raises(ValueError, match='requirements approval'):
        _review_guard(store, ['sw-developer'])


def test_stop_between_worker_return_and_merge_preserves_primary(tmp_path, monkeypatch):
    for key, value in {'GIT_AUTHOR_NAME': 'Test', 'GIT_COMMITTER_NAME': 'Test',
                       'GIT_AUTHOR_EMAIL': 'test@example.invalid', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}.items():
        monkeypatch.setenv(key, value)
    store = ProjectStore(tmp_path).init()
    git(tmp_path, 'init')
    (tmp_path / 'contract').write_text('frozen')
    git(tmp_path, 'add', 'contract');git(tmp_path, 'commit', '-m', 'Baseline')
    engine = CodexEngine(workspace=str(tmp_path), session_key='lead', role='sw-developer', store=store)
    (engine.store.root / 'requirements.md').write_text('# Requirements\nTest feature.\n')
    (engine.store.root / 'plan.md').write_text('# Plan\nImplement safely.\n')
    revision = review.requirements_revision(engine.store.root)
    engine.store.update_state(requirements_approved=revision, plan_requirements=revision,
                              plan_approved=review.implementation_plan(engine.store.root)['revision'])
    git(engine.store.root, 'add', 'requirements.md', 'plan.md')
    git(engine.store.root, 'commit', '-m', 'Approved test contract')
    def worker(parent, task, **kwargs):
        (Path(kwargs['workspace']) / 'a.py').write_text('saved partial work')
        parent._stopped.set()
        return {'status': 'completed', 'exit_reason': 'completed'}
    monkeypatch.setattr('lyra_lite.engines.codex_jobs._run', worker)
    result = json.loads(dispatch(engine, {'tasks': [{'goal': 'Code', 'context': json.dumps({'owned_paths': ['a.py']})}]}))
    assert 'did not finish' in result['error']
    assert not (tmp_path / 'a.py').exists()
    assert (Path(result['recovery']) / 'worker-0/a.py').read_text() == 'saved partial work'


def test_image_generation_uses_explicit_api_key_and_saves_valid_output(tmp_path, monkeypatch):
    from lyra_lite.imagine import imagine
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    target = tmp_path / 'image.png'
    assert not imagine('A tree', target)['success'] and not target.exists()
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-secret')
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            requests.append((url, kwargs))
            class Response:
                status_code = 200
                def json(self): return {'data': [{'b64_json': base64.b64encode(b'image-bytes').decode()}]}
            return Response()
    monkeypatch.setattr('lyra_lite.imagine.httpx.Client', Client)
    assert imagine('A tree', target)['success']
    assert target.read_bytes() == b'image-bytes'
    assert requests[0][0] == 'https://api.openai.com/v1/images/generations'
    assert requests[0][1]['headers']['Authorization'] == 'Bearer test-only-secret'
