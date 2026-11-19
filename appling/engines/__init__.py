"""Execution adapters. Project state never depends on a provider transcript."""
from __future__ import annotations
import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Run:
    root: Path
    instructions: str
    prompt: str
    model: str = ''
    effort: str = ''
    session: str | None = None
    readonly: bool = False
    connection_test: bool = False
    managed_worker: bool = False
    native_delegation: bool = False
    cancel: threading.Event = field(default_factory=threading.Event)
    emit: Callable = lambda *a, **k: None
    ask: Callable = lambda *a, **k: 'deny'
    recall: Callable = lambda q: []
    save_session: Callable = lambda s: None
    save_usage: Callable = lambda u: None


def result_json(text):
    try:
        data = json.loads(text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip())
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                data, end = decoder.raw_decode(text[i:])
                if isinstance(data, dict) and not text[i + end:].strip().strip('`'):
                    return data
            except ValueError:
                pass
    raise ValueError('The AI did not return a valid task result. Work is saved; retry this step or choose another connection.')


def available():
    return [dict(id=id_, label=label, installed=bool(shutil.which(binary))) for id_, label, binary in
            [('codex','Codex CLI','codex'),('claude-cli','Claude Code CLI','claude'),('copilot','GitHub Copilot CLI','copilot')]]


def environment():
    # CLI login stays in its normal credential store. Do not forward unrelated secrets.
    allowed = {'PATH','HOME','USER','LOGNAME','SHELL','TMPDIR','TEMP','TMP','LANG','LC_ALL','SYSTEMROOT',
               'OPENAI_API_KEY','ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN','GH_TOKEN','GITHUB_TOKEN',
               'GITHUB_COPILOT_TOKEN','COPILOT_GITHUB_TOKEN','CODEX_HOME','HTTPS_PROXY','HTTP_PROXY','NO_PROXY'}
    allowed.update({'PLAYWRIGHT_BROWSERS_PATH','npm_config_cache'})
    return {k:v for k,v in os.environ.items() if k in allowed}


def execute(connection, run):
    engine = connection['engine']
    if engine == 'codex':
        from .codex import execute as impl
    elif engine in {'claude-cli','copilot'}:
        from .cli import execute as impl
    elif engine in {'ollama','openai-compatible','anthropic'}:
        from .api import execute as impl
    else:
        raise ValueError(f'Unsupported engine: {engine}')
    return impl(connection, run)
