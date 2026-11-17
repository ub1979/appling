"""Transactional project state; the conversation is never the task database."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def ident() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self, home: Path):
        self.home = home.resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = self.home / "studio.sqlite"
        self.lock = threading.RLock()
        with self.connect() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, root TEXT UNIQUE NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(seq INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY, project TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS memories(project TEXT, source TEXT, content TEXT, revision TEXT, PRIMARY KEY(project,source));
            CREATE VIRTUAL TABLE IF NOT EXISTS recall USING fts5(project UNINDEXED, source UNINDEXED, content);
            CREATE TABLE IF NOT EXISTS checkpoints(project TEXT, role TEXT, data TEXT, PRIMARY KEY(project,role));
            """)

    @contextmanager
    def connect(self):
        with self.lock:
            c = sqlite3.connect(self.db, timeout=20)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise
            finally:
                c.close()

    def setting(self, key, default=None):
        with self.connect() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def save_setting(self, key, value):
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def add(self, root: Path, **options):
        root = root.resolve()
        if root == Path(root.anchor) or root == Path.home():
            raise ValueError("Choose a dedicated project folder.")
        root.mkdir(parents=True, exist_ok=True)
        state = dict(id=ident()[:12], root=str(root), name=root.name, phase="requirements",
                     team=["req-engineer", "task-planner"], style="app-it", profile="personal",
                     kind="app", platforms=["web"], running=False, paused=False, queue=[],
                     tasks=[], approvals={}, sessions={}, chat_id=ident(), updated=time.time(),
                     requirements_started=False, revision=1, engine="codex")
        state.update(options)
        with self.connect() as c:
            c.execute("INSERT INTO projects VALUES (?,?,?)", (state['id'], str(root), json.dumps(state)))
        (root / ".appling").mkdir(exist_ok=True)
        (root / ".appling" / ".gitignore").write_text("*\n")
        return state

    def get(self, pid):
        with self.connect() as c:
            row = c.execute("SELECT state FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError(pid)
        return json.loads(row[0])

    def update(self, pid, **fields):
        with self.connect() as c:
            state = self.get(pid)
            state.update(fields, updated=time.time())
            c.execute("UPDATE projects SET state=? WHERE id=?", (json.dumps(state), pid))
        return state

    def projects(self):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT state FROM projects ORDER BY rowid DESC")]

    def event(self, pid, type_, **fields):
        data = dict(ts=time.time(), type=type_, **fields)
        with self.connect() as c:
            seq = c.execute("INSERT INTO events(project,data) VALUES (?,?)", (pid, json.dumps(data))).lastrowid
        return dict(data, seq=seq)

    def events(self, pid, after=0, limit=500):
        with self.connect() as c:
            return [dict(json.loads(r['data']), seq=r['seq']) for r in c.execute(
                "SELECT seq,data FROM events WHERE project=? AND seq>? ORDER BY seq LIMIT ?", (pid, after, limit))]

    def event_cursor(self,pid):
        with self.connect() as c:
            return c.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?',(pid,)).fetchone()[0]

    def message(self, pid, role, content, kind="chat"):
        with self.connect() as c:
            c.execute("INSERT INTO messages(project,data) VALUES (?,?)", (pid, json.dumps(dict(role=role, content=content, kind=kind))))
        self.remember(pid, "conversation/" + ident(), f"{role}: {content}")

    def messages(self, pid):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT data FROM messages WHERE project=? ORDER BY seq", (pid,))]

    def ask(self, pid, kind, question, choices, **extra):
        item = dict(id=ident(), kind=kind, question=question, choices=choices, created=time.time(), **extra)
        with self.connect() as c:
            c.execute("INSERT INTO inbox VALUES (?,?,?)", (item['id'], pid, json.dumps(item)))
        self.event(pid, "inbox", item=item)
        return item

    def inbox(self, pid):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT data FROM inbox WHERE project=? ORDER BY rowid", (pid,))]

    def close(self, pid, iid):
        with self.connect() as c:
            c.execute("DELETE FROM inbox WHERE id=? AND project=?", (iid, pid))
        self.event(pid, "inbox_closed", id=iid)

    def remember(self, pid, source, content):
        revision = hashlib.sha256(content.encode()).hexdigest()
        with self.connect() as c:
            old = c.execute("SELECT revision FROM memories WHERE project=? AND source=?", (pid, source)).fetchone()
            if old and old[0] == revision:
                return
            c.execute("INSERT OR REPLACE INTO memories VALUES (?,?,?,?)", (pid, source, content, revision))
            c.execute("DELETE FROM recall WHERE project=? AND source=?", (pid, source))
            c.execute("INSERT INTO recall VALUES (?,?,?)", (pid, source, content))

    def search(self, pid, query, limit=6):
        import re
        words = re.findall(r"\w+", query)[:30]
        if not words:
            return []
        q = " OR ".join('"' + w + '"' for w in words)
        with self.connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT source,snippet(recall,2,'','', ' … ',70) AS content FROM recall WHERE recall MATCH ? AND project=? ORDER BY rank LIMIT ?",
                (q, pid, min(10, max(1, limit))))]

    def forget(self,pid,source):
        with self.connect() as c:
            c.execute('DELETE FROM memories WHERE project=? AND source=?',(pid,source))
            c.execute('DELETE FROM recall WHERE project=? AND source=?',(pid,source))

    def memory_sources(self,pid):
        with self.connect() as c:
            return [r[0] for r in c.execute('SELECT source FROM memories WHERE project=?',(pid,))]

    def checkpoint(self, pid, role, data):
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?)", (pid, role, json.dumps(data)))

    def last_checkpoint(self, pid, role):
        with self.connect() as c:
            r = c.execute("SELECT data FROM checkpoints WHERE project=? AND role=?", (pid, role)).fetchone()
            return json.loads(r[0]) if r else None


def safe_path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or ".git" in path.relative_to(root.resolve()).parts:
        raise ValueError("Path is outside the project or inside Git metadata.")
    return path


def revision(root: Path, name: str) -> str | None:
    path = safe_path(root, name)
    if not path.is_file():
        return None
    h = hashlib.sha256()
    paths = [path]
    if name == "prototypes/index.html":
        paths = sorted(p for p in path.parent.rglob('*') if p.is_file())
    for p in paths:
        p = safe_path(root, str(p.relative_to(root)))
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()
