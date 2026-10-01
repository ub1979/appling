"""A scripted OpenAI-compatible chat server on a real local socket.

Requests that carry ``tools`` (the main agent loop) consume the next scripted
step; tool-less side requests (titles, summaries) get a short canned reply so
they never eat the script. Every request body is recorded for assertions.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def text_step(text: str) -> dict:
    return {"text": text}


def tool_step(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    return {"tool": name, "arguments": arguments, "id": call_id}


class FakeOpenAIServer:
    def __init__(self, script: list[dict], *, step_delay: float = 0.0):
        self.script = list(script)
        self.step_delay = step_delay
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOpenAIServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    def next_step(self, body: dict) -> dict:
        with self._lock:
            self.requests.append(body)
            if not body.get("tools"):
                return text_step("ok")
            if self.script:
                return self.script.pop(0)
            return text_step("(script exhausted)")

    def main_requests(self) -> list[dict]:
        with self._lock:
            return [r for r in self.requests if r.get("tools")]

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def do_GET(self) -> None:
                if self.path.rstrip("/").endswith("/models"):
                    body = json.dumps({"object": "list", "data": [
                        {"id": "fake-model", "object": "model", "context_length": 128000}]})
                    self._send(200, body)
                else:
                    self._send(404, json.dumps({"error": "not found"}))

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
                if not self.path.rstrip("/").endswith("/chat/completions"):
                    self._send(404, json.dumps({"error": "not found"}))
                    return
                step = server.next_step(body)
                if server.step_delay and body.get("tools"):
                    time.sleep(server.step_delay)
                if body.get("stream"):
                    self._stream(step)
                else:
                    self._send(200, json.dumps(_completion(step)))

            def _send(self, code: int, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _stream(self, step: dict) -> None:
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                for chunk in _chunks(step):
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        return Handler


def _base(delta: dict, finish: str | None) -> dict:
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "fake-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _chunks(step: dict) -> list[dict[str, Any]]:
    if "tool" in step:
        call = {"index": 0, "id": step["id"], "type": "function",
                "function": {"name": step["tool"], "arguments": json.dumps(step["arguments"])}}
        return [_base({"role": "assistant", "tool_calls": [call]}, None),
                _base({}, "tool_calls"),
                {**_base({}, None), "choices": [], "usage": _usage()}]
    text = step.get("text", "")
    words = text.split(" ")
    out = [_base({"role": "assistant", "content": ""}, None)]
    for i, word in enumerate(words):
        out.append(_base({"content": word + (" " if i < len(words) - 1 else "")}, None))
    out.append(_base({}, "stop"))
    out.append({**_base({}, None), "choices": [], "usage": _usage()})
    return out


def _usage() -> dict:
    return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def _completion(step: dict) -> dict:
    if "tool" in step:
        message = {"role": "assistant", "content": None, "tool_calls": [{
            "id": step["id"], "type": "function",
            "function": {"name": step["tool"], "arguments": json.dumps(step["arguments"])}}]}
        finish = "tool_calls"
    else:
        message = {"role": "assistant", "content": step.get("text", "")}
        finish = "stop"
    return {"id": "chatcmpl-fake", "object": "chat.completion", "created": int(time.time()),
            "model": "fake-model",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": _usage()}
