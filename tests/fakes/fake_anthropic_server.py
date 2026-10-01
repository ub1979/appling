"""A scripted Anthropic Messages API on a real local socket.

Lets the real Claude Code CLI (driven by the Claude Agent SDK) run against
scripted replies. Requests whose system prompt contains ``marker`` consume
the script; everything else (titles, summaries, side calls) gets "ok".
Side scripts are chosen by a marker in the first user message, so a parent
agent and its subagents can run at the same time.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def text_step(text: str) -> dict:
    return {"text": text}


def tool_step(name: str, arguments: dict, call_id: str | None = None) -> dict:
    return {"tool": name, "arguments": arguments, "id": call_id or f"toolu_{uuid.uuid4().hex[:12]}"}


def _flat(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(_flat(c.get("text") if isinstance(c, dict) else c) for c in content)
    return ""


class FakeAnthropicServer:
    def __init__(self, script: list[dict], *, marker: str = "Lyra",
                 side_scripts: dict[str, list[dict]] | None = None):
        self.script = list(script)
        self.marker = marker
        self.side_scripts = {k: list(v) for k, v in (side_scripts or {}).items()}
        self.requests: list[dict] = []
        self.paths: list[str] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeAnthropicServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    def main_requests(self) -> list[dict]:
        with self._lock:
            return [r for r in self.requests if self.marker in _flat(r.get("system"))]

    def next_step(self, body: dict) -> dict:
        with self._lock:
            self.requests.append(body)
            messages = body.get("messages") or []
            first = _flat(messages[0].get("content")) if messages else ""
            if body.get("tools"):
                for key, steps in self.side_scripts.items():
                    if key in first:
                        return steps.pop(0) if steps else text_step("(side script exhausted)")
            if self.marker in _flat(body.get("system")) and body.get("tools"):
                return self.script.pop(0) if self.script else text_step("(script exhausted)")
            return text_step("ok")

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:
                pass

            def _json(self, code: int, payload: dict) -> None:
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                server.paths.append("GET " + self.path)
                self._json(200, {"data": [], "has_more": False})

            def do_HEAD(self) -> None:
                self.send_response(200)
                self.send_header("content-length", "0")
                self.end_headers()

            def do_POST(self) -> None:
                server.paths.append("POST " + self.path)
                length = int(self.headers.get("content-length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
                path = self.path.split("?")[0]
                if path.endswith("/count_tokens"):
                    self._json(200, {"input_tokens": 100})
                    return
                if not path.endswith("/v1/messages"):
                    self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": path}})
                    return
                step = server.next_step(body)
                if step.get("delay"):
                    time.sleep(step["delay"])
                if body.get("stream"):
                    self._stream(body, step)
                else:
                    self._json(200, _message(body, step))

            def _stream(self, body: dict, step: dict) -> None:
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "close")
                self.end_headers()
                for name, data in _events(body, step):
                    self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
                    self.wfile.flush()
                self.close_connection = True

        return Handler


def _usage() -> dict:
    return {"input_tokens": 100, "output_tokens": 10,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def _message(body: dict, step: dict) -> dict:
    if "tool" in step:
        content = [{"type": "tool_use", "id": step["id"], "name": step["tool"], "input": step["arguments"]}]
        stop = "tool_use"
    else:
        content = [{"type": "text", "text": step.get("text", "")}]
        stop = "end_turn"
    return {"id": f"msg_{uuid.uuid4().hex[:12]}", "type": "message", "role": "assistant",
            "model": body.get("model") or "claude-fake", "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": _usage()}


def _events(body: dict, step: dict):
    msg = _message(body, step)
    start = {**msg, "content": [], "stop_reason": None}
    yield "message_start", {"type": "message_start", "message": start}
    block = msg["content"][0]
    if block["type"] == "text":
        yield "content_block_start", {"type": "content_block_start", "index": 0,
                                      "content_block": {"type": "text", "text": ""}}
        words = block["text"].split(" ")
        for i, word in enumerate(words):
            piece = word + (" " if i < len(words) - 1 else "")
            yield "content_block_delta", {"type": "content_block_delta", "index": 0,
                                          "delta": {"type": "text_delta", "text": piece}}
    else:
        yield "content_block_start", {"type": "content_block_start", "index": 0,
                                      "content_block": {**block, "input": {}}}
        yield "content_block_delta", {"type": "content_block_delta", "index": 0,
                                      "delta": {"type": "input_json_delta",
                                                "partial_json": json.dumps(block["input"])}}
    yield "content_block_stop", {"type": "content_block_stop", "index": 0}
    yield "message_delta", {"type": "message_delta",
                            "delta": {"stop_reason": msg["stop_reason"], "stop_sequence": None},
                            "usage": {"output_tokens": 10}}
    yield "message_stop", {"type": "message_stop"}
