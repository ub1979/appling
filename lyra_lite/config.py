"""Appling's private configuration, independent of Hermes and Codex credentials."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_lock = threading.RLock()


def app_home() -> Path:
    return Path(os.environ.get("APPLING_HOME") or Path.home() / ".appling-codex").expanduser().resolve()


def load_config() -> dict:
    try:
        data = json.loads((app_home() / "settings.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(changes: dict) -> None:
    from lyra_lite.store import _atomic_write_json

    with _lock:
        home = app_home()
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        _atomic_write_json(home / "settings.json", {**load_config(), **changes})
