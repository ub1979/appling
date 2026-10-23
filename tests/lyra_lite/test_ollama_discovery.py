"""Appling's picker discovers local Ollama before it has been configured.

Exercise real config, inventory, HTTP discovery and settings routes. Only the
unrelated cloud-provider inventory is stubbed; Ollama is a local HTTP server.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from hermes_cli import inventory, local_ollama, model_switch
from hermes_cli.config import load_config
from hermes_constants import get_hermes_home
from lyra_lite.server import create_app


@pytest.fixture
def picker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.yaml"
    config_path.write_text('model: {provider: "", default: ""}\nproviders: {}\n', encoding="utf-8")
    # Keep cloud discovery/pricing out of this local-provider regression.
    rows = []
    monkeypatch.setattr(model_switch, "list_authenticated_providers", lambda **kw: list(rows))
    monkeypatch.setattr(inventory, "_apply_pricing", lambda *a, **kw: None)
    monkeypatch.setattr(inventory, "_apply_capabilities", lambda *a, **kw: None)
    state = {"payload": {"models": [{"name": "local-test:latest"}]}, "status": 200, "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["paths"].append(self.path)
            self.send_response(state["status"])
            self.end_headers()
            self.wfile.write(json.dumps(state["payload"]).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(local_ollama, "LOCAL_OLLAMA_ROOT", root)
    monkeypatch.setattr(local_ollama, "LOCAL_OLLAMA_OPENAI_URL", root + "/v1")
    # Discovery must work even when a GUI launch lacks the Ollama CLI in PATH.
    monkeypatch.setattr(local_ollama.shutil, "which", lambda name: None)
    try:
        with TestClient(create_app(token="test-token"), base_url="http://localhost",
                        headers={"x-lyra-token": "test-token"}) as client:
            yield client, state, rows, config_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("refresh", [False, True])
def test_fresh_settings_discovers_ollama_without_changing_config(picker, refresh):
    client, state, _, config_path = picker
    before = config_path.read_bytes()
    response = client.get("/api/settings/models", params={"refresh": refresh})
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"] == [{
        "slug": "ollama-local", "name": "Ollama — this computer",
        "models": ["local-test:latest"], "current": False,
    }]
    assert payload["provider"] == payload["model"] == ""
    assert state["paths"] == ["/api/tags"]
    assert config_path.read_bytes() == before


@pytest.mark.parametrize("status,payload", [(503, {}), (200, {"models": []}), (200, [])])
def test_unavailable_or_empty_ollama_keeps_other_providers_usable(picker, status, payload):
    client, state, rows, _ = picker
    rows.append({"slug": "saved-provider", "name": "Saved provider",
                 "models": ["saved-model"], "is_current": True})
    state.update(status=status, payload=payload)
    response = client.get("/api/settings/models")
    assert response.status_code == 200
    assert [p["slug"] for p in response.json()["providers"]] == ["saved-provider"]


def test_existing_ollama_row_is_not_duplicated_or_reprobed(picker):
    client, state, rows, _ = picker
    rows.append({"slug": "ollama-local", "name": "Saved Ollama",
                 "models": ["saved-model"], "is_current": True})
    payload = client.get("/api/settings/models").json()
    assert len(payload["providers"]) == 1
    assert payload["providers"][0]["models"] == ["saved-model"]
    assert state["paths"] == []


def test_refresh_discovers_new_models_without_registering_provider(picker):
    client, state, _, _ = picker
    initial = client.get("/api/settings/models").json()["providers"][0]["models"]
    state["payload"]["models"].append({"name": "new-model:latest"})
    refreshed = client.get("/api/settings/models?refresh=true").json()["providers"][0]["models"]
    assert refreshed == initial + ["new-model:latest"]
    assert "ollama-local" not in load_config().get("providers", {})


def test_other_picker_defaults_do_not_start_discovering_local_providers(picker):
    _, state, _, _ = picker
    payload = inventory.build_model_options_payload(inventory.load_picker_context(), explicit_only=True)
    assert payload["providers"] == []
    assert state["paths"] == []


def test_selecting_discovered_ollama_saves_the_existing_keyless_route(picker):
    client, _, _, _ = picker
    provider = client.get("/api/settings/models").json()["providers"][0]
    response = client.post("/api/settings/model", json={
        "provider": provider["slug"], "model": provider["models"][0], "confirm": True,
    })
    assert response.status_code == 200 and response.json()["ok"]
    cfg = load_config()
    assert cfg["model"]["provider"] == "ollama-local"
    assert cfg["model"]["default"] == "local-test:latest"
    assert cfg["model"]["base_url"] == local_ollama.LOCAL_OLLAMA_OPENAI_URL
    assert not cfg["providers"]["ollama-local"].get("api_key")
