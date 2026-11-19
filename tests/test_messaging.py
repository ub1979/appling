import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from appling.messaging import PhoneConnections, PhoneError, Telegram, WhatsApp
from appling.server import create_app
from appling.store import Store
from appling.workflow import Workflow

TOKEN = '123456:' + 'a' * 30


class Bot:
    def __init__(self, token=''):
        self.sent, self.calls = [], []
        self.closed = False

    def call(self, method, **data):
        self.calls.append((method, data))
        return {'username': 'appling_test_bot'} if method == 'getMe' else True

    def send(self, owner, text, buttons=None):
        self.sent.append(dict(owner=owner, text=text, buttons=buttons))
        return str(len(self.sent))

    def close(self):
        self.closed = True


def message(text, *, user='42', chat='42', type='private', seq=1, reply=None):
    msg = dict(text=text, message_id=100 + seq, chat=dict(id=chat, type=type), **{'from': dict(id=user, is_bot=False)})
    if reply:
        msg['reply_to_message'] = {'message_id': reply}
    return dict(update_id=seq, message=msg)


@pytest.fixture
def phone(tmp_path, monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    store = Store(tmp_path / 'home')
    workflow = Workflow(store)
    # Exercise the real answer/state transition path without starting paid model work.
    workflow._start = lambda pid: None
    manager = PhoneConnections(store, workflow, tmp_path, factories={'telegram': Bot})
    yield manager, store, workflow, tmp_path
    manager.close()
    workflow.shutdown()


def paired(manager, bot=None, channel='telegram'):
    bot = bot or Bot()
    if channel == 'telegram':
        manager.action(channel, dict(action='configure', bot_token=TOKEN))
    else:
        manager.action(channel, dict(action='configure', enabled=True))
    code = manager.action(channel, dict(action='pair'))[channel]['pairing_code']
    update = message('/pair ' + code) if channel == 'telegram' else dict(event='message', self_chat=True, from_me=True, account='42@s.whatsapp.net', text='/pair ' + code, message_id='pair')
    manager.receive(channel, bot, update)
    return bot


def test_credentials_are_private_and_never_returned_or_stored_in_project_db(phone):
    manager, store, _, _ = phone
    view = manager.action('telegram', dict(action='configure', bot_token=TOKEN))
    assert TOKEN not in json.dumps(view)
    assert TOKEN not in store.db.read_bytes().decode(errors='ignore')
    path = manager.home / 'telegram.token'
    assert path.read_text() == TOKEN
    assert path.stat().st_mode & 0o777 == 0o600
    assert manager.home.stat().st_mode & 0o777 == 0o700
    assert not view['telegram']['paired']
    assert manager.action('telegram', dict(action='test'))['telegram']['bot_username'] == 'appling_test_bot'


def test_pairing_requires_unexpired_single_use_code_and_private_chat(phone):
    manager, store, _, _ = phone
    manager.action('telegram', dict(action='configure', bot_token=TOKEN))
    code = manager.action('telegram', dict(action='pair'))['telegram']['pairing_code']
    bot = Bot()
    manager.receive('telegram', bot, message('/pair ' + code, type='group'))
    assert not manager.config('telegram')['owner']
    manager.receive('telegram', bot, message('/pair wrong'))
    assert not manager.config('telegram')['owner']
    manager.receive('telegram', bot, message('/pair ' + code))
    assert manager.config('telegram')['owner'] == dict(chat='42', user='42')
    manager.receive('telegram', bot, message('/pair ' + code, user='99', chat='99', seq=2))
    assert manager.config('telegram')['owner']['user'] == '42'
    code = manager.action('telegram', dict(action='pair'))['telegram']['pairing_code']
    state = manager.config('telegram'); state['pair_expires'] = 0; manager.save('telegram', state)
    manager.receive('telegram', bot, message('/pair ' + code, user='99', chat='99', seq=3))
    assert manager.config('telegram')['owner'] is None


def test_questions_map_exactly_across_projects_and_survive_restart(phone):
    manager, store, workflow, tmp = phone
    p1, p2 = store.add(tmp / 'one'), store.add(tmp / 'two')
    q1 = store.ask(p1['id'], 'question', 'First project question?', [])
    q2 = store.ask(p2['id'], 'question', 'Second project question?', [])
    bot = paired(manager)
    manager.deliver('telegram', bot)
    count = len(bot.sent)
    manager = PhoneConnections(store, workflow, tmp)
    manager.deliver('telegram', bot)
    assert len(bot.sent) == count
    requests = manager.config('telegram')['requests']
    code = next(k for k, r in requests.items() if r['iid'] == q1['id'])
    manager.receive('telegram', bot, message('/reply ' + code + ' Not yours', user='99', chat='99', seq=2))
    assert store.inbox(p1['id'])
    manager.receive('telegram', bot, message('yes', seq=3))
    assert store.inbox(p1['id']) and store.inbox(p2['id'])
    manager.receive('telegram', bot, message('Multiline\nanswer', reply=requests[code]['messages'][0], seq=4))
    assert not store.inbox(p1['id'])
    assert store.inbox(p2['id'])[0]['id'] == q2['id']
    assert any(m['content'] == 'Multiline\nanswer' for m in store.messages(p1['id']))
    before = store.messages(p1['id'])
    manager.receive('telegram', bot, message('/reply ' + code + ' Duplicate', seq=5))
    assert store.messages(p1['id']) == before
    assert 'already been answered' in bot.sent[-1]['text']


def test_approval_buttons_are_owner_message_and_revision_bound(phone):
    manager, store, workflow, tmp = phone
    project = store.add(tmp / 'review')
    root = Path(project['root']); (root / 'requirements.md').write_text('FR-001: Build a counter.')
    store.update(project['id'], phase='requirements_review')
    workflow.review(project['id'], 'requirements')
    bot = paired(manager); manager.deliver('telegram', bot)
    state = manager.config('telegram'); code, request = next(iter(state['requests'].items()))
    def callback(user='42', message_id=None, seq=2):
        return dict(update_id=seq, callback_query=dict(id='callback', data=f'a:{code}:0', **{'from': dict(id=user)}, message=dict(message_id=message_id or request['messages'][-1], chat=dict(id='42', type='private'))))
    manager.receive('telegram', bot, callback(user='99'))
    assert store.inbox(project['id'])
    manager.receive('telegram', bot, callback(message_id='9999', seq=3))
    assert store.inbox(project['id'])
    (root / 'requirements.md').write_text('FR-001: A different app.')
    manager.receive('telegram', bot, callback(seq=4))
    assert store.inbox(project['id']) and not store.get(project['id'])['approvals']
    assert 'changed' in bot.calls[-1][1]['text']
    # Reopen sends a new request; the old one can never approve the new revision.
    store.close(project['id'], request['iid']); workflow.review(project['id'], 'requirements')
    manager.deliver('telegram', bot)
    code = next(k for k, r in manager.config('telegram')['requests'].items() if r['iid'] != request['iid'])
    manager.receive('telegram', bot, message('/approve ' + code, seq=5))
    assert not store.inbox(project['id'])
    assert store.get(project['id'])['phase'] == 'build'
    assert store.get(project['id'])['approvals']['requirements']


def test_secret_prompts_are_never_forwarded_and_disconnect_revokes_access(phone):
    manager, store, _, tmp = phone
    project = store.add(tmp / 'private')
    store.ask(project['id'], 'secret', 'Enter secret', [])
    bot = paired(manager)
    manager.deliver('telegram', bot)
    assert not any('Enter secret' in m['text'] for m in bot.sent)
    manager.action('telegram', dict(action='disconnect'))
    assert not manager.config('telegram')['enabled']
    assert not manager.config('telegram')['owner']
    assert not manager.snapshot()['telegram']['paired']


def test_whatsapp_requires_verified_owner_self_chat_and_ignores_echoes(phone):
    manager, store, _, tmp = phone
    project = store.add(tmp / 'wa')
    question = store.ask(project['id'], 'question', 'Who uses it?', [])
    bot = paired(manager, channel='whatsapp')
    manager.status['whatsapp']['connected'] = True
    manager.deliver('whatsapp', bot)
    request = next(iter(manager.config('whatsapp')['requests'].values()))
    update = dict(event='message', self_chat=True, from_me=True, account='42@s.whatsapp.net', text='Me', reply_to=request['messages'][0], message_id='answer')
    manager.receive('whatsapp', bot, dict(update, self_chat=False))
    manager.receive('whatsapp', bot, dict(update, from_me=False))
    assert store.inbox(project['id'])[0]['id'] == question['id']
    count = len(bot.sent)
    manager.receive('whatsapp', bot, dict(update, text='Appling is paired.', reply_to=''))
    assert len(bot.sent) == count
    manager.receive('whatsapp', bot, update)
    assert not store.inbox(project['id'])


def test_telegram_transport_uses_long_polling_and_redacts_token_errors():
    calls = []
    def transport(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={'ok': True, 'result': []})
    client = Telegram(TOKEN, transport=httpx.MockTransport(transport))
    assert client.poll(17) == []
    assert calls[0][1]['offset'] == 17
    assert calls[0][1]['allowed_updates'] == ['message', 'callback_query']
    client.close()
    client = Telegram(TOKEN, transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError(str(request.url)))))
    with pytest.raises(PhoneError) as error:
        client.poll(17)
    assert TOKEN not in str(error.value)
    client.close()


def test_whatsapp_stdio_real_child_protocol_and_shutdown(tmp_path):
    script = tmp_path / 'bridge.py'
    script.write_text('''import sys,json
print(json.dumps({'event':'status','connected':True}),flush=True)
for line in sys.stdin:
 data=json.loads(line)
 print(json.dumps({'id':data['id'],'result':{'message_id':'outgoing'}}),flush=True)
''')
    client = WhatsApp(tmp_path / 'auth', command=[sys.executable, str(script)])
    try:
        assert client.send({}, 'A question') == 'outgoing'
        events = client.poll()
        assert any(e.get('connected') for e in events)
    finally:
        client.close()
    assert client.proc.poll() is not None


def test_phone_routes_require_session_auth_and_do_not_expose_tokens(tmp_path):
    app = create_app(tmp_path / 'studio')
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/settings/phone').status_code == 401
        client.headers['x-lyra-token'] = app.state.token
        assert not client.get('/api/settings/phone').json()['telegram']['enabled']
        response = client.post('/api/settings/phone/telegram', json=dict(action='configure', bot_token=TOKEN, enabled=False))
        assert response.status_code == 200
        assert TOKEN not in response.text
        assert client.post('/api/settings/phone/bogus', json=dict(action='pair')).status_code == 400
        assert client.post('/api/settings/phone/telegram', json=dict(action='pair')).status_code == 200
