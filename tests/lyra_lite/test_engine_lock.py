"""Legacy project migration uses real config and file-backed state."""
import pytest

from lyra_lite.settings import effective_engine, save_section
from lyra_lite.store import ProjectStore


@pytest.mark.parametrize("default", ["hermes", "claude"])
@pytest.mark.parametrize("override", [None, "hermes", "claude"])
def test_existing_projects_pin_their_effective_engine_once(tmp_path, default, override):
    save_section({"engine": default})
    store = ProjectStore(tmp_path / "legacy").init()
    # Reproduce old state, including the old explicit per-project option.
    store.update_state(engine=override, engine_override=bool(override), engine_locked=False)
    state = ProjectStore(store.root).init().state()
    chosen = override or default
    assert state["engine"] == chosen and state["engine_locked"]
    save_section({"engine": "claude" if chosen == "hermes" else "hermes"})
    reopened = ProjectStore(store.root).init()
    assert effective_engine(reopened.state()) == chosen
    reopened.archive_chat()
    assert effective_engine(reopened.state()) == chosen
    assert effective_engine(ProjectStore(tmp_path / "new").init().state()) != chosen
