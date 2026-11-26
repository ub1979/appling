"""Opt-in private phone channels. Messages never bypass controller approvals."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx

from . import procs
from .context import ROOT
from .workflow import ARTIFACTS

CHANNELS = ('telegram', 'whatsapp')
SUPPORTED = {'question', 'approval', *ARTIFACTS}


class PhoneError(ValueError):
    pass


class Telegram:
    def __init__(self, token, transport=None):
        self.token = token
        self.client = httpx.Client(timeout=10, transport=transport)

    def call(self, method, **data):
        try:
            response = self.client.post(f'https://api.telegram.org/bot{self.token}/{method}', json=data)
            payload = response.json()
            if not response.is_success or not payload.get('ok'):
                raise PhoneError('Telegram rejected the request. Check the bot token, connection and whether another app is polling this bot.')
            return payload['result']
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            if isinstance(exc, PhoneError):
                raise
            raise PhoneError('Telegram is unavailable. Check the bot token and internet connection.') from None

    def send(self, owner, text, buttons=None):
        data = dict(chat_id=owner['chat'], text=text, link_preview_options={'is_disabled': True})
        if buttons:
            data['reply_markup'] = {'inline_keyboard': buttons}
        return str(self.call('sendMessage', **data)['message_id'])

    def poll(self, offset):
        return self.call('getUpdates', offset=offset, timeout=3, allowed_updates=['message', 'callback_query'])

    def close(self):
        self.client.close()


class WhatsApp:
    """Private stdio bridge; no listening port and no inherited AI credentials."""
    def __init__(self, auth_dir, command=None):
        bridge = ROOT / 'bridge' / 'whatsapp'
        if command is None and not (bridge / 'node_modules' / 'baileys').is_dir():
            raise PhoneError('Install WhatsApp support first: cd bridge/whatsapp && npm install')
        if command is None and not shutil.which('node'):
            raise PhoneError('WhatsApp support requires Node.js 20 or newer.')
        self.events = queue.Queue()
        self.replies = {}
        self.lock = threading.Lock()
        self.seq = 0
        env = procs.pick({'PATH', 'HOME', 'TMPDIR', 'TEMP', 'TMP', 'LANG', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'})
        self.proc = procs.spawn(command or ['node', str(bridge / 'index.mjs'), str(auth_dir)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding='utf-8', errors='replace', env=env, bufsize=1)
        threading.Thread(target=self._read, daemon=True, name='appling-whatsapp-reader').start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if 'id' in data:
                with self.lock:
                    target = self.replies.get(data['id'])
                if target:
                    target.put(data)
            else:
                self.events.put(data)
        self.events.put({'event': 'status', 'connected': False, 'message': 'WhatsApp bridge stopped. Reconnect from Settings.'})

    def call(self, method, **data):
        with self.lock:
            self.seq += 1
            ident = self.seq
            reply = queue.Queue()
            self.replies[ident] = reply
            try:
                self.proc.stdin.write(json.dumps(dict(id=ident, method=method, **data)) + '\n')
                self.proc.stdin.flush()
            except (OSError, ValueError):
                self.replies.pop(ident, None)
                raise PhoneError('WhatsApp bridge is disconnected.') from None
        try:
            result = reply.get(timeout=15)
            if result.get('error'):
                raise PhoneError('WhatsApp could not complete the request. Check its connection in Settings.')
            return result.get('result', {})
        except queue.Empty:
            raise PhoneError('WhatsApp did not respond. Check its connection in Settings.') from None
        finally:
            with self.lock:
                self.replies.pop(ident, None)

    def send(self, owner, text, buttons=None):
        return self.call('send', text=text)['message_id']

    def poll(self, offset=0):
        result = []
        while True:
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                return result

    def close(self, logout=False):
        if logout and self.proc.poll() is None:
            try:
                self.call('logout')
            except PhoneError:
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        procs.stop(self.proc)   # nothing left on Linux and macOS; on Windows this also ends the bridge's own children
        self.proc.stdin.close()
        self.proc.stdout.close()


class PhoneConnections:
    def __init__(self, store, workflow, home, factories=None):
        self.store, self.workflow = store, workflow
        self.home = Path(home) / 'phone'
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.clients = {}
        self.threads = []
        self.status = {key: dict(connected=False, message='Not connected.') for key in CHANNELS}
        self.pairing_codes = {}
        self.factories = factories or {}

    def config(self, channel):
        return self.store.setting('phone.' + channel, dict(enabled=False, token_env='TELEGRAM_BOT_TOKEN', owner=None, offset=0, requests={}, cursors={}))

    def save(self, channel, state):
        self.store.save_setting('phone.' + channel, state)

    def _credential(self, state):
        value = os.environ.get(state.get('token_env', 'TELEGRAM_BOT_TOKEN'), '')
        path = self.home / 'telegram.token'
        if not value and path.is_file():
            value = path.read_text().strip()
        return value

    def snapshot(self):
        with self.lock:
            result = {}
            for channel in CHANNELS:
                conf = self.config(channel)
                view = dict(enabled=bool(conf['enabled']), configured=bool(self._credential(conf)) if channel == 'telegram' else (ROOT / 'bridge/whatsapp/node_modules/baileys').is_dir(),
                    paired=bool(conf.get('owner')), token_env=conf.get('token_env', ''), **self.status[channel])
                code = self.pairing_codes.get(channel)
                if code and conf.get('pair_expires', 0) > time.time():
                    view.update(pairing_code=code, expires_at=conf['pair_expires'])
                    if channel == 'telegram' and view.get('bot_username'):
                        view['pairing_url'] = f'https://t.me/{view["bot_username"]}?start={code}'
                result[channel] = view
            return result

    def start(self):
        for channel in CHANNELS:
            thread = threading.Thread(target=self._loop, args=(channel,), daemon=True, name='appling-phone-' + channel)
            self.threads.append(thread)
            thread.start()

    def close(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=18)
        for client in list(self.clients.values()):
            client.close()
        self.clients.clear()

    def action(self, channel, data):
        if channel not in CHANNELS:
            raise PhoneError('Unknown phone connection.')
        action = data.get('action')
        with self.lock:
            state = self.config(channel)
            if action == 'configure':
                if channel == 'telegram':
                    env = data.get('token_env', state.get('token_env', 'TELEGRAM_BOT_TOKEN'))
                    if not isinstance(env, str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,100}', env):
                        raise PhoneError('Use an environment variable name such as TELEGRAM_BOT_TOKEN.')
                    token = data.get('bot_token', '').strip()
                    if token:
                        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token):
                            raise PhoneError('Enter the bot token supplied by BotFather.')
                        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
                        os.chmod(self.home, 0o700)
                        path = self.home / 'telegram.token'
                        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                        with os.fdopen(fd, 'w') as out:
                            out.write(token)
                        os.chmod(path, 0o600)
                        # A different bot must be paired again; never reuse its old owner or request IDs.
                        self._reset(state)
                    if env != state.get('token_env', 'TELEGRAM_BOT_TOKEN'):
                        self._reset(state)
                    state['token_env'] = env
                state['enabled'] = bool(data.get('enabled', True))
                if channel == 'telegram' and state['enabled'] and not self._credential(state):
                    raise PhoneError('Enter a Telegram bot token or configure its environment variable first.')
                self._drop_client(channel)
                self.save(channel, state)
                self.status[channel] = dict(connected=False, message='Connecting…' if state['enabled'] else 'Disabled.')
            elif action == 'pair':
                if channel == 'telegram' and not self._credential(state):
                    raise PhoneError('Configure a Telegram bot token first.')
                self._reset(state)
                state['enabled'] = True
                code = secrets.token_hex(8)
                self.pairing_codes[channel] = code
                state.update(pair_hash=hashlib.sha256(code.encode()).hexdigest(), pair_expires=time.time() + 600)
                self.save(channel, state)
            elif action == 'disconnect':
                state['enabled'] = False
                self._reset(state)
                self.save(channel, state)
                self.pairing_codes.pop(channel, None)
                self._drop_client(channel, logout=True)
                if channel == 'whatsapp':
                    shutil.rmtree(self.home / 'whatsapp', ignore_errors=True)
                self.status[channel] = dict(connected=False, message='Disconnected. Pair again to enable phone access.')
            elif action == 'test':
                if channel == 'telegram':
                    token = self._credential(state)
                    if not token:
                        raise PhoneError('Configure a Telegram bot token first.')
                    client = self.factories.get('telegram', Telegram)(token)
                    try:
                        info = client.call('getMe')
                    finally:
                        client.close()
                    self.status[channel].update(connected=True, bot_username=info['username'], message='Bot connection works. Pair your private chat to receive questions.')
                    if state.get('owner'):
                        client = self.factories.get('telegram', Telegram)(token)
                        try:
                            self._send(channel, client, state, 'Appling phone connection works. Questions and approvals will arrive in this chat.')
                        finally:
                            client.close()
                        self.status[channel]['message'] = 'Test message sent to your paired phone.'
                elif not self.status[channel].get('connected'):
                    raise PhoneError('WhatsApp is not connected. Enable it and scan the QR code first.')
                elif not state.get('owner'):
                    raise PhoneError('Pair your Message yourself chat first.')
                else:
                    self._send(channel, self._client(channel, state), state, 'Appling phone connection works. Questions and approvals will arrive here.')
                    self.status[channel]['message'] = 'Test message sent to your paired phone.'
            else:
                raise PhoneError('Unknown phone connection action.')
            return self.snapshot()

    @staticmethod
    def _reset(state):
        state.update(owner=None, offset=0, requests={}, cursors={})
        state.pop('pair_hash', None)
        state.pop('pair_expires', None)

    def _drop_client(self, channel, logout=False):
        client = self.clients.pop(channel, None)
        if client:
            if channel == 'whatsapp':
                client.close(logout=logout)
            else:
                client.close()

    def _client(self, channel, state):
        with self.lock:
            previous = self.clients.get(channel)
            if channel == 'whatsapp' and previous and previous.proc.poll() is not None:
                self._drop_client(channel)
            if channel not in self.clients:
                if channel == 'telegram':
                    client = self.factories.get(channel, Telegram)(self._credential(state))
                    try:
                        info = client.call('getMe')
                    except BaseException:
                        client.close()
                        raise
                    self.status[channel].update(connected=True, bot_username=info['username'], message='Connected. Pair your private chat.' if not state.get('owner') else 'Connected to your phone.')
                else:
                    self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
                    client = self.factories.get(channel, WhatsApp)(self.home / 'whatsapp')
                self.clients[channel] = client
            return self.clients[channel]

    def _loop(self, channel):
        while not self.stop_event.is_set():
            try:
                state = self.config(channel)
                if state['enabled']:
                    client = self._client(channel, state)
                    updates = client.poll(state.get('offset', 0))
                    if channel == 'telegram':
                        with self.lock:
                            current = self.config(channel)
                            if client is self.clients.get(channel) and current['enabled']:
                                self.status[channel].update(connected=True, message='Connected to your phone.' if current.get('owner') else 'Connected. Pair your private chat.')
                    for update in updates:
                        with self.lock:
                            # Disabling/reconfiguring in Settings invalidates an in-flight poll.
                            if client is not self.clients.get(channel) or not self.config(channel)['enabled']:
                                break
                            self.receive(channel, client, update)
                    with self.lock:
                        if client is self.clients.get(channel) and self.config(channel)['enabled']:
                            self.deliver(channel, client)
                self.stop_event.wait(1)
            except Exception as exc:
                with self.lock:
                    if not self.stop_event.is_set() and self.config(channel)['enabled']:
                        self.status[channel].update(connected=False, message=str(exc) if isinstance(exc, PhoneError) else 'Phone connection interrupted. Retrying; pending questions remain saved.')
                self.stop_event.wait(5)

    def _send(self, channel, client, state, text, buttons=None):
        message_ids = []
        parts = [text[i:i+3500] for i in range(0, len(text), 3500)] or ['']
        for index, part in enumerate(parts):
            if self.stop_event.is_set():
                raise InterruptedError('Phone connections are stopping.')
            message_ids.append(str(client.send(state['owner'], part, buttons if index == len(parts)-1 else None)))
        return message_ids

    def deliver(self, channel, client):
        state = self.config(channel)
        if not state.get('owner') or (channel == 'whatsapp' and not self.status[channel].get('connected')):
            return
        requests = state.setdefault('requests', {})
        open_ids = set()
        for project in self.store.projects():
            pid = project['id']
            for item in self.store.inbox(pid):
                if item['kind'] not in SUPPORTED:
                    continue  # Never forward secret/password prompts.
                open_ids.add(item['id'])
                if any(r['iid'] == item['id'] for r in requests.values()):
                    continue
                code = secrets.token_hex(6)
                row = dict(pid=pid, iid=item['id'], revision=item.get('revision'), choices=item.get('choices', []), kind=item['kind'], messages=[])
                requests[code] = row
                # Persist the request before transmission; incomplete delivery is retried below.
                self.save(channel, state)
            for code, row in list(requests.items()):
                if row['pid'] != pid or row.get('messages'):
                    continue
                item = next((i for i in self.store.inbox(pid) if i['id'] == row['iid']), None)
                if not item:
                    continue
                text = f'Appling · {project["name"]}\nRequest {code}\n\n{item["question"]}'
                if item.get('role') or item.get('worker_id'):
                    text += f'\n\nWorker: {item.get("role", "")} {item.get("worker_id", "")}'
                text += f'\n\nReply to this message, or send: /reply {code} your answer'
                buttons = None
                if row['kind'] != 'question':
                    if row['kind'] == 'prototype':
                        text += '\nThe clickable prototype is local to your PC. Review it in Appling before approving.'
                    text += f'\nTo approve: /approve {code}\nTo decline/request changes: /deny {code} your feedback'
                if channel == 'telegram' and row['choices']:
                    buttons = [[dict(text=str(choice)[:60], callback_data=f'a:{code}:{index}')]
                               for index, choice in enumerate(row['choices'][:20])]
                row['messages'] = self._send(channel, client, state, text, buttons)
                self.save(channel, state)
            cursor = state.setdefault('cursors', {}).get(pid)
            if cursor is None:
                state['cursors'][pid] = self.store.event_cursor(pid)
            else:
                for event in self.store.events(pid, cursor):
                    if event['type'] == 'problem' or (event['type'] == 'turn_end' and event.get('status') == 'error'):
                        self._send(channel, client, state, f'Appling · {project["name"]}\nWork needs attention. Open the project to inspect its saved error and evidence.')
                    state['cursors'][pid] = event['seq']
                if project['phase'] == 'delivered' and state.setdefault('completed', {}).get(pid) != project.get('revision'):
                    self._send(channel, client, state, f'Appling · {project["name"]}\nYour app is ready. Verified checks are saved in the project.')
                    state['completed'][pid] = project.get('revision')
        # Keep a bounded stale-request history for clear duplicate rejection across restarts.
        for key in list(requests):
            if requests[key]['iid'] not in open_ids and len(requests) > 300:
                requests.pop(key)
        self.save(channel, state)

    def receive(self, channel, client, update):
        state = self.config(channel)
        if channel == 'whatsapp' and update.get('event') == 'status':
            self.status[channel].update({k: update[k] for k in ('connected', 'message', 'qr') if k in update})
            if update.get('connected'):
                self.status[channel].pop('qr', None)
            return
        callback = None
        if channel == 'telegram':
            callback = update.get('callback_query')
            msg = callback.get('message', {}) if callback else update.get('message', {})
            who = callback.get('from', {}) if callback else msg.get('from', {})
            if msg.get('chat', {}).get('type') != 'private' or who.get('is_bot'):
                self._ack_update(channel, state, update)
                return
            owner = dict(chat=str(msg['chat']['id']), user=str(who['id']))
            text = msg.get('text', '') if not callback else ''
            reply_to = str(msg.get('reply_to_message', {}).get('message_id', ''))
        else:
            if not update.get('self_chat') or not update.get('from_me'):
                return
            owner = dict(chat=update['account'], user=update['account'])
            text = update.get('text', '')
            reply_to = update.get('reply_to', '')
            if not reply_to and not re.match(r'^/(?:pair|start|reply|approve|deny)\b', text.strip()):
                return  # Ignore self-chat notes and bridge confirmations; never create an echo loop.
            if any(str(update.get('message_id')) in row.get('messages', []) for row in state.get('requests', {}).values()):
                return
        pair = re.fullmatch(r'/(?:start|pair)(?:@\w+)?\s+([0-9a-f]{16})', text.strip())
        if pair and state.get('pair_hash') and state.get('pair_expires', 0) > time.time():
            if secrets.compare_digest(hashlib.sha256(pair[1].encode()).hexdigest(), state['pair_hash']):
                state.update(owner=owner, requests={}, cursors={p['id']: self.store.event_cursor(p['id']) for p in self.store.projects()})
                state.pop('pair_hash', None)
                state.pop('pair_expires', None)
                self.pairing_codes.pop(channel, None)
                self.save(channel, state)
                self.status[channel].update(connected=True, message='Paired. Questions and approvals will arrive here.')
                self._send(channel, client, state, 'Appling is paired. Reply to a question to answer it. Approval requests include their own request code. Only this private chat can control your projects.')
            self._ack_update(channel, state, update)
            return
        if owner != state.get('owner'):
            if callback:
                client.call('answerCallbackQuery', callback_query_id=callback['id'], text='This account is not paired.')
            self._ack_update(channel, state, update)
            return
        try:
            code, answer, index = None, None, None
            if callback:
                match = re.fullmatch(r'a:([0-9a-f]{12}):(\d{1,2})', callback.get('data', ''))
                if match:
                    code, index = match[1], int(match[2])
            else:
                match = re.fullmatch(r'/(reply|approve|deny)\s+([0-9a-f]{12})(?:\s+([\s\S]+))?', text.strip())
                if match:
                    action, code, answer = match[1], match[2], match[3] or ''
                elif reply_to:
                    code = next((key for key, row in state.get('requests', {}).items() if str(reply_to) in row.get('messages', [])), None)
                    action, answer = 'reply', text.strip()
                else:
                    # No ambient "yes" approval or guessed project routing.
                    raise PhoneError('Reply to the specific Appling message, or use /reply REQUEST_CODE your answer.')
            row = state.get('requests', {}).get(code)
            if not row:
                raise PhoneError('Unknown request. Use the code from the current Appling message.')
            if callback:
                if str(msg.get('message_id')) not in row.get('messages', []):
                    raise PhoneError('That button does not belong to this request.')
                if index is None or index >= len(row['choices']):
                    raise PhoneError('Unknown approval option.')
                answer = row['choices'][index]
            elif action == 'approve':
                if row['kind'] == 'question':
                    raise PhoneError('This question needs an answer, not an approval.')
                answer = next((c for c in row['choices'] if str(c).lower().startswith('approve') or c in {'once', 'accept', 'allow'}), None)
                if answer is None:
                    raise PhoneError('Reply with one of the exact choices in this request.')
            elif action == 'deny':
                choice = next((c for c in row['choices'] if c in {'deny', 'decline', 'Request changes'}), None)
                if choice is None:
                    raise PhoneError('Reply with one of the exact choices in this request.')
                answer = dict(choice=choice, feedback=answer or 'Please ask what needs changing.')
            if not answer:
                raise PhoneError('Write an answer first.')
            if row['kind'] in ARTIFACTS:
                answer = dict(answer, revision=row['revision']) if isinstance(answer, dict) else dict(choice=answer, revision=row['revision'])
            # Workflow owns locking, current inbox existence and artifact revision checks.
            self.workflow.answer(row['pid'], row['iid'], answer)
            response = 'Saved in Appling. Work will continue when its other pending requests are resolved.'
        except (ValueError, KeyError) as exc:
            # Controller errors are user-facing, but arbitrary engine/network errors are never forwarded.
            response = str(exc) if isinstance(exc, ValueError) else 'This project is no longer available.'
        if callback:
            client.call('answerCallbackQuery', callback_query_id=callback['id'], text=response[:180])
        else:
            self._send(channel, client, state, response)
        self._ack_update(channel, state, update)

    def _ack_update(self, channel, state, update):
        if channel == 'telegram' and 'update_id' in update:
            # Reload: answering may have triggered another delivery or settings change.
            state = self.config(channel)
            state['offset'] = max(state.get('offset', 0), update['update_id'] + 1)
            self.save(channel, state)
