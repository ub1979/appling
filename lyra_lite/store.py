"""Per-project files that hold everything Appling knows about a project.

Everything lives under ``<project>/.lyra/`` so a refresh, a sleep or a restart
loses nothing — the UI and the daemon simply re-read the files:

- ``events.jsonl``   append-only activity: user text, reply deltas, tools,
                     helpers, inbox items, turn boundaries. Readers tail it by
                     byte offset.
- ``messages.jsonl`` the conversation the engine resumes from, rewritten
                     atomically at the end of each turn (it may be compressed).
- ``transcript.jsonl`` what the owner sees: every message, append-only, never
                     compressed.
- ``inbox/<id>.json`` one file per question for the owner (approval,
                     clarify, secret). Secret answers are never written.
- ``state.json``     small mutable status (running, queue, chat id, offsets).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

LYRA_DIR = ".lyra"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data: Any) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class ProjectStore:
    """File-backed state for one project folder. Thread-safe within a process."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        self.dir = self.root / LYRA_DIR
        self.events_path = self.dir / "events.jsonl"
        self.messages_path = self.dir / "messages.jsonl"
        self.transcript_path = self.dir / "transcript.jsonl"
        self.state_path = self.dir / "state.json"
        self.inbox_dir = self.dir / "inbox"
        self.chats_dir = self.dir / "chats"
        self._lock = threading.RLock()

    # -- setup ---------------------------------------------------------------

    def init(self) -> "ProjectStore":
        with self._lock:
            self.inbox_dir.mkdir(parents=True, exist_ok=True)
            self.chats_dir.mkdir(parents=True, exist_ok=True)
            self.events_path.touch(exist_ok=True)
            ignore = self.dir / ".gitignore"
            if not ignore.exists():
                # Activity and chat files are personal working state; the
                # project's own git history should not carry them.
                _atomic_write_text(ignore, "*\n")
            if not self.state_path.exists():
                _atomic_write_json(self.state_path, self._new_state())
        return self

    @staticmethod
    def _new_state() -> dict:
        return {
            "chat_id": uuid.uuid4().hex[:12],
            "running": False,
            "queue": [],
            "turn": None,
            "turn_start_offset": 0,
            "engine": None,  # None: follow Lyra's default engine
            "rules_hash": "",
        }

    # -- state ---------------------------------------------------------------

    def state(self) -> dict:
        with self._lock:
            data = _read_json(self.state_path, None)
            if not isinstance(data, dict):
                data = self._new_state()
            return data

    def update_state(self, **changes: Any) -> dict:
        with self._lock:
            data = self.state()
            data.update(changes)
            _atomic_write_json(self.state_path, data)
            return data

    # -- events --------------------------------------------------------------

    def append_event(self, type_: str, **data: Any) -> dict:
        event = {"ts": round(time.time(), 3), "type": type_, **data}
        line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with open(self.events_path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                if type_ not in {"delta", "reasoning"}:
                    os.fsync(fh.fileno())
        return event

    def events_size(self) -> int:
        try:
            return self.events_path.stat().st_size
        except OSError:
            return 0

    def read_events(self, offset: int = 0) -> tuple[list[dict], int]:
        """Return complete events from *offset* and the offset after them.

        A trailing half-written line is left for the next read.
        """
        try:
            with open(self.events_path, "rb") as fh:
                fh.seek(max(0, offset))
                chunk = fh.read()
        except OSError:
            return [], offset
        end = chunk.rfind(b"\n")
        if end < 0:
            return [], offset
        events: list[dict] = []
        for raw in chunk[: end + 1].splitlines():
            try:
                events.append(json.loads(raw))
            except ValueError:
                continue
        return events, offset + end + 1

    # -- messages ------------------------------------------------------------

    def messages(self) -> list[dict]:
        return self._read_jsonl(self.messages_path)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        out: list[dict] = []
        try:
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(item, dict):
                        out.append(item)
        except OSError:
            pass
        return out

    def save_messages(self, messages: list[dict]) -> None:
        text = "".join(
            json.dumps(m, ensure_ascii=False, default=str) + "\n" for m in messages
        )
        with self._lock:
            _atomic_write_text(self.messages_path, text)

    def transcript(self) -> list[dict]:
        return self._read_jsonl(self.transcript_path)

    def has_transcript(self) -> bool:
        return self.transcript_path.exists()

    def append_transcript(self, entries: list[dict]) -> None:
        if not entries:
            return
        text = "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in entries)
        with self._lock:
            with open(self.transcript_path, "a", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())

    def write_transcript(self, entries: list[dict]) -> None:
        with self._lock:
            _atomic_write_text(self.transcript_path, "".join(
                json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in entries))

    def archive_chat(self) -> str:
        """Move the current conversation aside and start a new chat id."""
        with self._lock:
            old = self.state().get("chat_id") or uuid.uuid4().hex[:12]
            if self.messages_path.exists():
                os.replace(self.messages_path, self.chats_dir / f"{old}.messages.jsonl")
            if self.transcript_path.exists():
                os.replace(self.transcript_path, self.chats_dir / f"{old}.transcript.jsonl")
            new_id = uuid.uuid4().hex[:12]
            self.update_state(chat_id=new_id, rules_hash="")
            return new_id

    # -- inbox ---------------------------------------------------------------

    def _inbox_path(self, item_id: str) -> Path:
        safe = "".join(ch for ch in item_id if ch.isalnum() or ch in "-_")
        if not safe:
            raise ValueError("bad inbox id")
        return self.inbox_dir / f"{safe}.json"

    def add_inbox(self, kind: str, **fields: Any) -> dict:
        item = {
            "id": f"{kind}-{uuid.uuid4().hex[:10]}",
            "kind": kind,
            "status": "open",
            "created": round(time.time(), 3),
            **fields,
        }
        with self._lock:
            _atomic_write_json(self._inbox_path(item["id"]), item)
        return item

    def inbox_item(self, item_id: str) -> dict | None:
        data = _read_json(self._inbox_path(item_id), None)
        return data if isinstance(data, dict) else None

    def close_inbox(self, item_id: str, status: str, answer: Any = None) -> dict | None:
        with self._lock:
            item = self.inbox_item(item_id)
            if item is None:
                return None
            item["status"] = status
            item["closed"] = round(time.time(), 3)
            if item.get("kind") != "secret" and answer is not None:
                item["answer"] = answer
            _atomic_write_json(self._inbox_path(item_id), item)
            return item

    def inbox(self, status: str | None = None) -> list[dict]:
        items: list[dict] = []
        for path in sorted(self.inbox_dir.glob("*.json")):
            data = _read_json(path, None)
            if isinstance(data, dict) and (status is None or data.get("status") == status):
                items.append(data)
        items.sort(key=lambda it: it.get("created", 0))
        return items

    def iter_open_inbox(self) -> Iterator[dict]:
        yield from self.inbox(status="open")
