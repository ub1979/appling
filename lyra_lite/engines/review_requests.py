"""Review checkpoints shared by Codex host tools and native questions."""
from __future__ import annotations
import threading
import time
from typing import Any

CLARIFY_TIMEOUT_S = 30 * 60

class ReviewRequests:
    def _on_clarify(self, question: str, choices) -> str:
        if self.store is not None:
            from lyra_lite import review

            state = self.store.state()
            root = self.store.root
            update = review.active_update(root, state) or {}
            if list(choices or []) == list(review.PLAN_CHOICES) or (
                state.get("plan_review_required") and not state.get("requirements_review")
                and state.get("requirements_approved") == review.requirements_revision(root)
                and review.requests_plan_approval(question, choices)
            ):
                if (review.plan_execution_started(state)
                        and review.requirements_revision(root) == state.get("requirements_approved")):
                    return ("Implementation has already started from the approved plan. Report progress or "
                            "delivery instead of reopening pre-development approval. New scope belongs in "
                            "a project update with its own requirements review.")
                plan = review.implementation_plan(root)
                if not plan:
                    return "Save the implementation plan before asking the owner to approve it."
                if (state.get("requirements_review") or review.requirements_revision(root) != state.get("requirements_approved")):
                    return "Finish requirements approval before asking for implementation plan approval."
                if review.visual_project(root, state) and review.prototype_revision(root) != state.get("prototype_approved"):
                    return "Review the current prototype before reviewing its implementation plan."
                self.store.update_state(plan_review_required=True)
                return self._ask_blocking(
                    "plan", timeout=None, on_timeout="Implementation plan review is pending.",
                    question="Review this implementation plan before development starts.\n\n" + plan["text"],
                    choices=list(review.PLAN_CHOICES), revision=plan["revision"], path=plan["path"],
                    requirements=state.get("requirements_approved"),
                )
            if list(choices or []) == list(review.PROTOTYPE_CHOICES):
                revision = review.prototype_revision(root)
                if not revision or revision in (update.get("baseline_prototype_revision"),
                                                 state.get("prototype_needs_changes")):
                    return ("The prototype needs work before review. Create or revise prototypes/index.html "
                            "and its clickable flows, then call this checkpoint again.")
                self.store.update_state(requirements_review=True, requirements_started=True)
                return self._ask_blocking(
                    "prototype", question=str(question), choices=list(review.PROTOTYPE_CHOICES),
                    revision=revision, timeout=None,
                    on_timeout="Prototype review is still pending. Wait for the owner's decision.",
                )
            if list(choices or []) == list(review.REQUIREMENTS_CHOICES):
                revision = review.requirements_revision(root)
                if not revision or revision == update.get("baseline_requirements_revision"):
                    return "Write the new requirements draft before asking for approval."
                prototype = None
                if review.visual_project(root, state):
                    prototype = review.prototype_revision(root)
                    if not prototype or prototype != state.get("prototype_approved"):
                        return "The owner must open and approve the current clickable prototype first."
                self.store.update_state(requirements_review=True, requirements_started=True)
                draft = (root / "requirements.md").read_text(encoding="utf-8")
                question = str(question)
                if draft not in question:
                    question += "\n\n---\n\n" + draft
                return self._ask_blocking(
                    "requirements", question=question,
                    choices=list(review.REQUIREMENTS_CHOICES),
                    revision=revision, prototype=prototype, timeout=None,
                    on_timeout="Requirements approval is still pending. Wait for the owner.",
                )
        return self._ask_blocking(
            "question",
            question=str(question),
            choices=list(choices or []),
            timeout=CLARIFY_TIMEOUT_S,
            on_timeout="The owner has not answered yet. Continue with safe defaults, "
            "or end your reply with the question so they can answer later.",
        )

    def _ask_blocking(self, kind: str, *, timeout: float | None, on_timeout: str, **fields) -> str:
        hooks = self._hooks
        if hooks is None:
            return on_timeout
        done = threading.Event()
        box: dict[str, Any] = {}

        def _answer(value: Any) -> None:
            box["value"] = value
            done.set()

        item_id = hooks.ask(kind, _answer, **fields)
        request_id = self._request_id
        with self._request_lock:
            self._waiting_inboxes[request_id] = item_id
            resolved = request_id in self._resolved_requests
        if resolved:
            self._expire_request(request_id)
        deadline = None if timeout is None else time.monotonic() + timeout
        while not done.wait(0.2):
            with self._request_lock:
                resolved = request_id in self._resolved_requests
            if resolved or self._stopped.is_set() or (deadline is not None and time.monotonic() >= deadline):
                break
        if not done.is_set():
            self._expire_request(request_id)
            return on_timeout
        with self._request_lock:
            self._waiting_inboxes.pop(request_id, None)
        value = box.get("value")
        return "" if value is None else str(value)
