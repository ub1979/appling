"""Project memory: everything a project has said and written, searchable.

One SQLite full-text index per project (``.lyra/memory.db``) over the full
chat transcript, the project's documents (requirements, plan, progress,
Project Brain, reports, README …) and its Git history. Appling and its agents
query it with the ``project_recall`` tool to find earlier decisions and the
owner's exact words without carrying the whole history in context.

Each project only ever searches itself: nothing crosses between projects.
The index is rebuilt incrementally from the files, so it can always be
deleted and regenerated.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

DB_NAME = "memory.db"
CHUNK = 1200
OVERLAP = 120
DOC_SUFFIXES = {".md", ".txt"}
SKIP_DIRS = {".git", ".lyra", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".next"}
MAX_DOC_BYTES = 400_000
MAX_DOC_DEPTH = 3
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be",
    "it", "this", "that", "with", "as", "at", "by", "what", "did", "do", "does", "we", "i", "you",
    "about", "how", "which", "when", "where", "why", "who", "should", "would", "could", "can",
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(path), threading.Lock())


def chunks(text: str, size: int = CHUNK, overlap: int = OVERLAP) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if cut > start + size // 2:
                end = cut + 1
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in out if c]


def fts_query(query: str) -> str:
    words = [w for w in re.findall(r"[\w'-]+", query.lower()) if w not in STOPWORDS and len(w) > 1]
    words = list(dict.fromkeys(words))[:16]
    return " OR ".join('"' + w.replace('"', "") + '"' for w in words)


class ProjectMemory:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.path = self.root / ".lyra" / DB_NAME
        self._lock = _lock_for(self.path)

    # -- storage -----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
            "text, source UNINDEXED, ref UNINDEXED, ts UNINDEXED, tokenize='porter unicode61')")
        conn.execute("CREATE TABLE IF NOT EXISTS seen(source TEXT PRIMARY KEY, mark TEXT)")
        return conn

    @staticmethod
    def _mark(conn, source: str) -> str | None:
        row = conn.execute("SELECT mark FROM seen WHERE source = ?", (source,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _set_mark(conn, source: str, mark: str) -> None:
        conn.execute("INSERT OR REPLACE INTO seen(source, mark) VALUES (?, ?)", (source, mark))

    @staticmethod
    def _replace(conn, source: str, rows: list[tuple[str, str, str]]) -> None:
        conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        conn.executemany("INSERT INTO chunks(text, source, ref, ts) VALUES (?, ?, ?, ?)",
                         [(text, source, ref, ts) for text, ref, ts in rows])

    # -- indexing ----------------------------------------------------------

    def refresh(self) -> int:
        """Index anything new or changed. Returns the number of chunks added."""
        with self._lock:
            conn = self._connect()
            try:
                added = self._index_transcript(conn) + self._index_documents(conn) + self._index_git(conn)
                conn.commit()
                return added
            finally:
                conn.close()

    def _index_transcript(self, conn) -> int:
        added = 0
        for path in sorted((self.root / ".lyra").glob("transcript.jsonl")) + sorted(
                (self.root / ".lyra" / "chats").glob("*.transcript.jsonl")):
            source = f"chat:{path.name}"
            done = int(self._mark(conn, source) or 0)
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rows = []
            for n, raw in enumerate(lines[done:], start=done + 1):
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                text = str(entry.get("content") or "")
                if not text.strip() or text.startswith("IDRAK_INTERNAL"):
                    continue
                speaker = "Owner" if entry.get("role") == "user" else "Appling"
                if text.startswith("[ASYNC DELEGATION") or text.startswith(("While Appling was stopped", "While APP IT was stopped", "While Lyra was stopped")):
                    speaker = "Agent report"
                ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["ts"])) if entry.get("ts") else ""
                for piece in chunks(text):
                    rows.append((f"{speaker}: {piece}", f"chat message {n}", ts))
            if rows:
                conn.executemany("INSERT INTO chunks(text, source, ref, ts) VALUES (?, ?, ?, ?)",
                                 [(t, source, r, ts) for t, r, ts in rows])
                added += len(rows)
            self._set_mark(conn, source, str(len(lines)))
        return added

    def _documents(self):
        def walk(folder: Path, depth: int):
            try:
                entries = sorted(folder.iterdir())
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith(".") and entry.name != ".sdlc":
                    continue
                if entry.is_dir():
                    if entry.name not in SKIP_DIRS and depth < MAX_DOC_DEPTH:
                        yield from walk(entry, depth + 1)
                elif entry.suffix.lower() in DOC_SUFFIXES:
                    yield entry
        yield from walk(self.root, 0)

    def _index_documents(self, conn) -> int:
        added = 0
        present = set()
        for path in self._documents():
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > MAX_DOC_BYTES:
                continue
            rel = path.relative_to(self.root).as_posix()
            source = f"file:{rel}"
            present.add(source)
            mark = f"{stat.st_mtime_ns}:{stat.st_size}"
            if self._mark(conn, source) == mark:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            rows = [(f"{rel}: {piece}", rel, ts) for piece in chunks(text)]
            self._replace(conn, source, rows)
            self._set_mark(conn, source, mark)
            added += len(rows)
        for (source,) in conn.execute("SELECT source FROM seen WHERE source LIKE 'file:%'").fetchall():
            if source not in present:  # file deleted
                conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
                conn.execute("DELETE FROM seen WHERE source = ?", (source,))
        return added

    def _index_git(self, conn) -> int:
        try:
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except Exception:
            return 0
        if not head or self._mark(conn, "git") == head:
            return 0
        try:
            log = subprocess.run(["git", "log", "-300", "--format=%h%x1f%ad%x1f%s%x1f%b%x1e", "--date=format:%Y-%m-%d %H:%M"],
                                 cwd=self.root, capture_output=True, text=True, timeout=20).stdout
        except Exception:
            return 0
        rows = []
        for record in log.split("\x1e"):
            parts = record.strip().split("\x1f")
            if len(parts) < 3:
                continue
            sha, date, subject = parts[0], parts[1], parts[2]
            body = parts[3].strip() if len(parts) > 3 else ""
            rows.append((f"Commit {sha}: {subject}\n{body}".strip()[:CHUNK], f"commit {sha}", date))
        self._replace(conn, "git", rows)
        self._set_mark(conn, "git", head)
        return len(rows)

    # -- search ------------------------------------------------------------

    def search(self, query: str, limit: int = 6) -> list[dict]:
        q = fts_query(query)
        if not q:
            return []
        self.refresh()
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT text, source, ref, ts, bm25(chunks) AS rank FROM chunks WHERE chunks MATCH ? "
                    "ORDER BY rank LIMIT ?", (q, int(limit))).fetchall()
            except sqlite3.OperationalError:
                rows = []
            finally:
                conn.close()
        return [{"text": text[:900], "source": source.split(":", 1)[-1], "ref": ref, "when": ts}
                for text, source, ref, ts, _rank in rows]


def format_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"No project memory matched “{query}”. Try other words, or ask the owner."
    lines = [f"Project memory for “{query}” (most relevant first):"]
    for i, r in enumerate(results, 1):
        where = r["ref"] + (f", {r['when']}" if r["when"] else "")
        lines.append(f"\n{i}. [{where}]\n{r['text']}")
    return "\n".join(lines)


RECALL_DESCRIPTION = (
    "Search this project's memory: the full chat with the owner (their exact words), "
    "requirements, plans, progress notes, agent reports and change history. Use it before "
    "relying on your memory of an earlier decision or asking the owner something they may "
    "already have answered."
)
