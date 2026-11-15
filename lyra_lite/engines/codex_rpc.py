"""Small stdio JSON-RPC client for the official Codex app-server protocol.

Only the reader owns stdout. Requests can be made while a tool or approval is
waiting, so Stop never depends on the model completing its current request.
"""
from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading


class CodexRPC:
    def __init__(self, *, cwd: str, command: list[str] | None = None, on_notification=None, env=None):
        executable = shutil.which("codex")
        if command is None and executable is None:
            raise RuntimeError("Install Codex CLI, then restart Appling. Codex was not found on PATH.")
        self.events = queue.Queue()
        self._lock = threading.RLock()
        self._pending = {}
        self._next_id = 0
        self._closed = False
        self._on_notification = on_notification
        self.process = subprocess.Popen(command or [executable, "app-server"], cwd=cwd,
                                        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._reader = threading.Thread(target=self._read, name="appling-codex-rpc", daemon=True)
        self._reader.start()
        try:
            from lyra_lite import __version__
            self.request("initialize", {"clientInfo": {"name": "appling", "title": "Appling", "version": __version__},
                                        "capabilities": {"experimentalApi": True}})
            self.notify("initialized", {})
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                message = json.loads(line)
                if "id" in message and "method" not in message:
                    with self._lock:
                        waiter = self._pending.get(message["id"])
                    if waiter is not None:
                        waiter.put(message)
                else:
                    if self._on_notification and "id" not in message:
                        self._on_notification(message)
                    self.events.put(message)
        except (OSError, ValueError):
            pass
        finally:
            failure = {"error": {"message": "Codex app-server disconnected. Work is saved; resume explicitly."}}
            with self._lock:
                self._closed = True
                for waiter in self._pending.values():
                    waiter.put(failure)
            self.events.put(failure)

    def _write(self, message):
        with self._lock:
            if self._closed:
                raise RuntimeError("Codex app-server is closed")
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

    def request(self, method: str, params: dict, timeout: float = 30):
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            waiter = self._pending[request_id] = queue.Queue()
        try:
            self._write({"id": request_id, "method": method, "params": params})
            try:
                response = waiter.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError(f"Codex did not acknowledge {method}; the action was not retried.") from None
            if "error" in response:
                raise RuntimeError(str(response["error"].get("message") or "Codex request failed"))
            return response.get("result") or {}
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: dict):
        self._write({"method": method, "params": params})

    def respond(self, request_id, result: dict):
        self._write({"id": request_id, "result": result})

    def reject(self, request_id):
        self._write({"id": request_id, "error": {"code": -32601, "message": "Unsupported host request; no permission granted"}})

    def close(self):
        with self._lock:
            self._closed = True
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        self._reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
