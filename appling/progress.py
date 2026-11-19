"""Persist periodic, observed progress in the project conversation, without inference."""
from __future__ import annotations
import json
import threading
import time
import logging

from .engines.claude_support import safe_diagnostic

INTERVAL = 300


def publish_due(store, pid, *, now=None, interval=INTERVAL):
    now = time.time() if now is None else now
    # One transaction claims a cadence slot and saves its message/event. Multiple
    # watchers cannot duplicate updates; messages never advance controller state.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT state FROM projects WHERE id=?', (pid,)).fetchone()
        if not row:return False
        state = json.loads(row[0]); turn = state.get('turn') or {}
        if not state.get('running') or state.get('paused') or not turn.get('id'):return False
        key = 'progress:'+pid
        saved = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        previous = json.loads(saved[0]) if saved else {}
        if previous.get('turn') == turn['id']:
            since = previous['at']; cursor = previous['cursor']
        else:
            started = db.execute("SELECT seq,data FROM events WHERE project=? AND json_extract(data,'$.type')='turn_start' AND json_extract(data,'$.turn')=? ORDER BY seq DESC LIMIT 1", (pid,turn['id'])).fetchone()
            if not started:return False
            cursor = started[0]; since = json.loads(started[1])['ts']
        if now-since < interval:return False
        # Exclude deltas and raw commands, which can be large or contain secrets.
        events = [json.loads(r[0]) for r in db.execute(
            "SELECT data FROM events WHERE project=? AND seq>? AND json_extract(data,'$.type') IN ('tool','worker_commentary','worker','native_agent') ORDER BY seq", (pid,cursor))]
        recent = [e for e in events if e.get('ts',0) >= now-interval]
        commands = [e for e in recent if e['type']=='tool' and e.get('phase')=='complete' and e.get('name')=='commandExecution']
        failed = sum(type(e.get('exit_code')) is int and e['exit_code']!=0 for e in commands)
        labels = {'build':'Coding and integration','qa':'Independent QA','security':'Security review','prototype':'Prototype design','requirements':'Requirements','plan':'Implementation planning','code-review':'Code review','accessibility':'Accessibility review'}
        lines = [f"Progress update — {labels.get(state['phase'],state['phase'])} is active."]
        if commands:lines.append(f"In the last five minutes, {len(commands)} command(s) finished; {failed} returned a nonzero exit code. These results do not establish release acceptance.")
        else:lines.append('No completed commands were reported in the last five minutes. The job is still marked running; this alone does not prove progress.')
        if any(e['type']=='native_agent' or e.get('name')=='subAgentActivity' for e in recent):
            lines.append('Native coding-agent activity was reported; an exact concurrent agent count is unavailable.')
        reports = [e for e in recent if e['type']=='worker_commentary' and isinstance(e.get('text'),str)]
        if reports:lines.append('Latest agent report (not independent verification): '+safe_diagnostic(reports[-1]['text'])[:800])
        current = {t['id'] for t in state.get('tasks',[]) if t.get('status')!='done'}
        latest = {w['task_id']:w for w in state.get('workers',[])}
        blocked = [w['task_id'] for w in latest.values() if w['task_id'] in current and w['status'] in {'blocked','conflict'}]
        if blocked:lines.append('Blocked work: '+', '.join(blocked)+'. Retained changes are not treated as completed.')
        waiting = db.execute('SELECT COUNT(*) FROM inbox WHERE project=?',(pid,)).fetchone()[0]
        if waiting:lines.append(f'{waiting} question or approval request(s) are waiting for your input.')
        message = dict(role='assistant',kind='progress',content='\n\n'.join(lines))
        cursor = db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?',(pid,)).fetchone()[0]
        db.execute('INSERT INTO messages(project,data) VALUES (?,?)',(pid,json.dumps(message)))
        db.execute('INSERT INTO events(project,data) VALUES (?,?)',(pid,json.dumps(dict(type='status_update',ts=now,text=message['content'],turn=turn['id']))))
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(dict(turn=turn['id'],at=now,cursor=cursor))))
    return True


def watch(store, pid, stopped, *, alive=lambda:True):
    while not stopped.is_set() and alive():
        try:
            for project in ([pid] if pid else [p['id'] for p in store.projects()]):
                if stopped.is_set():break
                publish_due(store,project)
        except Exception:logging.getLogger(__name__).exception('Could not save periodic progress')
        stopped.wait(5)


def start(store, pid):
    stopped = threading.Event()
    thread = threading.Thread(target=watch,args=(store,pid,stopped),daemon=True,name='appling-progress')
    thread.start()
    return stopped,thread


if __name__ == '__main__':
    # Attach the same publisher to a pre-update service without interrupting its
    # model turn. The instance guard ends this bridge when that service changes.
    import argparse
    import signal
    from pathlib import Path
    from .store import Store
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',required=True)
    parser.add_argument('--project')
    parser.add_argument('--instance',required=True)
    args=parser.parse_args()
    store=Store(Path(args.home));stopped=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopped.set())
    def alive():
        try:
            service=json.loads((store.home.parent/'run/server.json').read_text())
            return service.get('instance')==args.instance
        except (OSError,ValueError,KeyError):return False
    watch(store,args.project,stopped,alive=alive)
