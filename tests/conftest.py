"""Shared test safety: no test may read, write or act on the owner's real Appling data."""
import pytest

from appling import __main__ as launcher
from appling import children


@pytest.fixture(autouse=True)
def leftover_cleanup_stays_off(monkeypatch):
    """Starting the real launcher would turn the process ledger on in the real data folder and stop
    what it lists. Tests that want the ledger turn it on themselves, in a temporary folder."""
    calls = []
    monkeypatch.setattr(launcher, 'stop_leftovers', lambda home=None: calls.append(home))
    yield calls
    children.disable()
