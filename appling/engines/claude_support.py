"""Claude-specific CLI environment, diagnostics and versioned picker defaults."""
from __future__ import annotations
import os
import re
from . import environment

# Public IDs checked against https://platform.claude.com/docs/en/models/overview
# on 2026-11-17.
# A selectable fallback catalogue, not a claim of account entitlement.
MODEL_IDS = [
    'claude-fable-5-2','claude-opus-5-5','claude-sonnet-5-5','claude-haiku-5-5',
    'claude-fable-5-1','claude-fable-5','claude-opus-5','claude-sonnet-5',
    'claude-opus-4-8','claude-opus-4-7','claude-opus-4-6','claude-sonnet-4-6',
    'claude-opus-4-5-20251101','claude-sonnet-4-5-20250929','claude-haiku-4-5-20251001',
]


def claude_environment():
    env=environment()
    for name,value in os.environ.items():
        if name.startswith('ANTHROPIC_') or name in {'CLAUDE_CONFIG_DIR','XDG_CONFIG_HOME','http_proxy','https_proxy','no_proxy'}:
            env[name]=value
    env.pop('CLAUDECODE',None)
    return env


def safe_diagnostic(text):
    text=str(text)
    for name,value in os.environ.items():
        if len(value)>5 and any(part in name.upper() for part in ['TOKEN','KEY','PASSWORD','SECRET']):
            text=text.replace(value,'[REDACTED]')
    text=re.sub(r'(?i)\bBearer\s+\S+','Bearer [REDACTED]',text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]+','[REDACTED]',text)
    text=re.sub(r'(?i)([?&](?:api_key|key|token|password)=)[^\s&]+',r'\1[REDACTED]',text)
    return text.strip()[-1800:]


class CliError(RuntimeError):
    def __init__(self,message):
        super().__init__(safe_diagnostic(message))
