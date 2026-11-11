"""The main composer answers owner questions without bypassing approval gates."""
import time

import pytest

from lyra_lite import review
from lyra_lite.runner import ProjectRunner
from lyra_lite.store import ProjectStore

FEEDBACK = ('Inset the dropdown arrows so they do not cut the border.\n\n'
            'Change this part of the app (picked in the preview):\n'
            '- element: select#dateMeaning\n- selector: select#amountMeaning\n'
            '- html: <select id="dateMeaning"></select>')


@pytest.fixture
def runner(tmp_path):
    runner = ProjectRunner(ProjectStore(tmp_path), lambda *_: None)
    # Keep the real worker from consuming test queue entries; these tests
    # exercise the public submit/answer and inbox callbacks directly.
    with runner._cond:
        runner._busy = True
        runner.store.update_state(turn={"id": "active", "text": "Review the prototype", "started": time.time() - 1})
    yield runner
    runner.shutdown()


def test_composer_answers_the_question_and_preserves_picked_context(runner):
    answers = []
    card = runner._open_inbox("question", answers.append, question="What should change?")
    result = runner.submit(FEEDBACK)
    assert result["answered"] == card
    assert answers == [FEEDBACK]
    assert runner.snapshot()["queue"] == []
    assert runner.store.inbox_item(card)["answer"] == FEEDBACK
    assert any(m["content"] == FEEDBACK for m in runner.store.conversation())
    # A background report cannot answer an owner question.
    next_card = runner._open_inbox("question", answers.append, question="Which date?")
    runner.submit("agent completed", kind="helper_done")
    assert runner.store.inbox_item(next_card)["status"] == "open"
    assert len(answers) == 1


def test_messages_arriving_before_clarify_answer_it_once_and_keep_reports(runner):
    first = runner.submit(FEEDBACK)
    report = runner.submit("background handoff", kind="helper_done")
    second = runner.submit("Keep the rest of the prototype as it is.")
    answers = []
    card = runner._open_inbox("question", answers.append, question="What should change?")
    assert answers == [FEEDBACK + "\n\nKeep the rest of the prototype as it is."]
    assert [q["id"] for q in runner.snapshot()["queue"]] == [report["id"]]
    events, _ = runner.store.read_events()
    consumed, = [e for e in events if e["type"] == "queue_consumed"]
    assert set(consumed["ids"]) == {first["id"], second["id"]}
    assert consumed["inbox"] == card
    assert not runner.answer(card, "duplicate")
    assert len(answers) == 1


@pytest.mark.parametrize("kind", ["prototype", "requirements"])
def test_review_feedback_requests_changes_and_cannot_approve(runner, kind):
    answers = []
    runner.store.update_state(**{kind + "_approved": "old"})
    card = runner._open_inbox(kind, answers.append, revision="current", question="Approve?")
    result = runner.submit(FEEDBACK)
    assert result["answered"] == card
    assert answers == ["Request changes\n\nOwner feedback:\n" + FEEDBACK]
    assert runner.store.state()[kind + "_approved"] is None
    if kind == "prototype":
        assert runner.store.state()["prototype_needs_changes"] == "current"


@pytest.mark.parametrize("kind", ["approval", "secret"])
def test_normal_chat_never_resolves_a_permission_or_secret_card(runner, kind):
    answers = []
    card = runner._open_inbox(kind, answers.append, question="Protected request")
    result = runner.submit(FEEDBACK)
    assert "answered" not in result
    assert answers == []
    assert runner.store.inbox_item(card)["status"] == "open"
    assert runner.snapshot()["queue"][0]["text"] == FEEDBACK


def test_queued_messages_do_not_auto_approve_a_new_review(runner):
    runner.submit("yes")
    answers = []
    card = runner._open_inbox("prototype", answers.append, revision="current", question="Approve?")
    assert not answers
    assert runner.store.inbox_item(card)["status"] == "open"
    with pytest.raises(ValueError, match="Open the current prototype"):
        runner.answer(card, {"choice": review.PROTOTYPE_CHOICES[0], "feedback": "yes"})


def test_multiple_open_questions_require_an_explicit_card_answer(runner):
    answers = []
    for question in ("First?", "Second?"):
        runner._open_inbox("question", answers.append, question=question)
    result = runner.submit(FEEDBACK)
    assert "answered" not in result
    assert not answers
    assert len(runner.store.inbox(status="open")) == 2
