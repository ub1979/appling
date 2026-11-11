"""A real provider 429 is visible before the retry finishes; owner can stop/apply rules."""
import json
import time

from tests.fakes.fake_openai_server import FakeOpenAIServer, text_step
from tests.lyra_lite.test_lyrad_real_path import (
    Daemon, _new_project, _wait_event, _write_config, env,  # noqa: F401
)


class RateLimitedProvider(FakeOpenAIServer):
    def _handler(self):
        parent = super()._handler()
        class Handler(parent):
            def _limited(self):
                data = json.dumps({"error": {"type": "rate_limit_error", "message": "Rate limit exceeded"}}).encode()
                self.send_response(429)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.send_header("retry-after", "600")
                self.end_headers()
                self.wfile.write(data)
            def _stream(self, step):
                self._limited()
            def _send(self, code, body):
                self._limited()
        return Handler


def test_rate_limit_visible_and_stop_allows_rule_update(env):
    with RateLimitedProvider([text_step("unused")]) as llm:
        _write_config(env["hermes_home"], llm.base_url, lyra_lite={"watchdog": {"enabled": False}})
        daemon = Daemon(env).start()
        try:
            pid, path = _new_project(daemon, env, "Rate limited")
            prefix = f"/api/projects/{pid}"
            assert daemon.post(prefix + "/messages", {"text": "Please begin"}).status_code == 200
            event = _wait_event(path, lambda e: e["type"] == "provider_status" and e.get("state") == "retrying", 45)
            assert event["retry_at"] > time.time() + 500
            assert event["reason"] == "rate_limit"
            snapshot = daemon.get(prefix).json()
            assert snapshot["provider_statuses"]["main"]["model"] == "fake-model"
            assert daemon.post(prefix + "/apply-rules", {}).status_code == 409
            assert daemon.post(prefix + "/stop", {}).status_code == 200
            _wait_event(path, lambda e: e["type"] == "turn_end", 15)
            assert daemon.get(prefix).json()["provider_statuses"] == {}
            assert daemon.post(prefix + "/apply-rules", {}).status_code == 200
        finally:
            daemon.stop()
