"""Every Appling test gets private configuration; never touch a real registry."""
import pytest

@pytest.fixture(autouse=True)
def private_appling_home(tmp_path, monkeypatch):
    monkeypatch.setenv("APPLING_HOME", str(tmp_path / "appling-home"))
