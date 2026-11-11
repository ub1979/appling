"""Reviews outlive clarify's ordinary timeout and expired cards can be restored safely."""
from concurrent.futures import ThreadPoolExecutor
import time

import pytest

from lyra_lite import review
from lyra_lite.engines.base import TurnResult
from lyra_lite.engines.hermes import HermesEngine
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore


class RecordingEngine:
    def __init__(self):
        self.texts = []

    def run_turn(self, text, history, hooks):
        self.texts.append(text)
        return TurnResult(reply="Decision received.", messages=history + [
            {"role": "user", "content": text}, {"role": "assistant", "content": "Decision received."}])

    def close(self): pass
    def interrupt(self): pass


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr("lyra_lite.runner.checkpoint", lambda *a, **kw: None)
    (tmp_path / "prototypes").mkdir()
    (tmp_path / "prototypes/index.html").write_text("<button>Try the prototype</button>")
    (tmp_path / "requirements.md").write_text("# Requirements\nStatus: Draft\nLoad CSV files.\n")
    store = ProjectStore(tmp_path).init()
    store.update_state(project_kind="app", requirements_review=True)
    recording = RecordingEngine()
    runner = ProjectRunner(store, lambda *_: recording)
    yield runner, recording
    runner.shutdown()


def _open(runner):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        cards = runner.store.inbox(status="open")
        if cards:
            return cards[0]
        time.sleep(0.005)
    raise AssertionError("No review card opened")


@pytest.mark.parametrize("kind", ["prototype", "requirements"])
def test_review_does_not_use_ordinary_question_timeout(project, monkeypatch, kind):
    runner, _ = project
    monkeypatch.setattr("lyra_lite.engines.hermes.CLARIFY_TIMEOUT_S", 0.01)
    revision = review.prototype_revision(runner.root)
    if kind == "requirements":
        runner.store.update_state(prototype_approved=revision)
    engine = HermesEngine(workspace=str(runner.root), session_key=runner.session_key(), store=runner.store)
    engine._hooks = runner._hooks
    choices = review.PROTOTYPE_CHOICES if kind == "prototype" else review.REQUIREMENTS_CHOICES
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(engine._on_clarify, "Approve this draft?", choices)
        try:
            card = _open(runner)
            time.sleep(0.05)
            assert not pending.done()
            assert runner.store.inbox_item(card["id"])["status"] == "open"
            if kind == "prototype":
                with pytest.raises(ValueError, match="Open the current prototype"):
                    runner.answer(card["id"], "Approve prototype")
            assert runner.answer(card["id"], "Request changes")
            assert pending.result(2) == "Request changes"
        finally:
            runner.stop_turn()


def _expired(runner, kind="prototype", **fields):
    revision = (review.prototype_revision if kind == "prototype" else review.requirements_revision)(runner.root)
    item = runner.store.add_inbox(kind, question="Review the draft?", revision=revision,
                                 choices=list(review.PROTOTYPE_CHOICES if kind == "prototype" else review.REQUIREMENTS_CHOICES), **fields)
    runner.store.close_inbox(item["id"], "expired")
    return item


def test_expired_review_reopens_without_model_call_and_answer_resumes_once(project):
    runner, recording = project
    original = _expired(runner)
    recovered = runner.reopen_review(original["id"])
    assert not recording.texts
    assert runner.store.state().get("prototype_approved") is None
    assert runner.recoverable_review() is None
    with pytest.raises(RuntimeError, match="no longer current"):
        runner.reopen_review(original["id"])
    assert runner.answer(recovered, {"choice": "Approve prototype", "revision": original["revision"]})
    deadline = time.monotonic() + 5
    while not recording.texts and time.monotonic() < deadline:
        time.sleep(0.01)
    assert recording.texts == ["Owner's prototype review decision:\n\nApprove prototype"]
    assert runner.store.state()["prototype_approved"] == original["revision"]
    assert not runner.answer(recovered, "Request changes")


@pytest.mark.parametrize("change", ["files", "changes_requested", "approved", "new_chat"])
def test_stale_or_answered_prototype_cannot_reopen(project, change):
    runner, _ = project
    original = _expired(runner)
    if change == "files":
        (runner.root / "prototypes/index.html").write_text("<button>Different version</button>")
    elif change == "new_chat":
        runner.new_chat()
    else:
        key = "prototype_needs_changes" if change == "changes_requested" else "prototype_approved"
        runner.store.update_state(**{key: original["revision"]})
    assert runner.recoverable_review() is None
    with pytest.raises(RuntimeError, match="no longer current"):
        runner.reopen_review(original["id"])


def test_requirements_recovery_requires_the_same_approved_prototype(project):
    runner, _ = project
    prototype = review.prototype_revision(runner.root)
    original = _expired(runner, "requirements", prototype=prototype)
    assert runner.recoverable_review() is None
    runner.store.update_state(prototype_approved=prototype)
    assert runner.recoverable_review()["id"] == original["id"]
    reopened = runner.reopen_review(original["id"])
    (runner.root / "prototypes/index.html").write_text("<button>New design</button>")
    with pytest.raises(ValueError, match="Review the current prototype"):
        runner.answer(reopened, "Approve requirements")
