"""The agent team catalogue and the project setup / team messages.

The wording of the setup and team-update messages is the Studio's protocol
that the app-it playbook already understands (IDRAK_INTERNAL_SETUP_* and
IDRAK_INTERNAL_SKILLS_UPDATE_*), so Lyra behaves the same in Lite.
"""

from __future__ import annotations

import json
from pathlib import Path

AGENTS: list[tuple[str, str, str]] = [
    ("req-engineer", "Requirements", "Clarify goals, users, scope, and acceptance criteria."),
    ("researcher", "Research", "Investigate markets, competitors, standards, and technical choices with verified sources."),
    ("spec", "Technical specification", "Turn the request into detailed, testable behavior."),
    ("ui-designer", "Design", "Set the look and feel from real references, then review the build against it."),
    ("sw-architect", "Architecture", "Design the system, data, APIs, and boundaries."),
    ("task-planner", "Task planning", "Create an ordered implementation graph."),
    ("proj-manager", "Project planning", "Build milestones, checkpoints, and delivery plans."),
    ("sw-developer", "Development", "Write and integrate working application code."),
    ("oop-restructurer", "Code restructuring", "Improve modules, classes, and maintainability."),
    ("debugger", "Debugging", "Find root causes and add regression coverage."),
    ("code-reviewer", "Code review", "Review correctness, quality, and maintainability."),
    ("ux-writer", "UX writing", "Write the labels, empty states, and error messages users read."),
    ("qa-engineer", "Quality assurance", "Test real user journeys and report reproducible bugs."),
    ("a11y-auditor", "Accessibility", "Audit against WCAG 2.2 with measured contrast and keyboard paths."),
    ("security-auditor", "Security", "Audit authentication, data, dependencies, and secrets."),
    ("devops-engineer", "Deployment", "Prepare CI/CD, containers, operations, and rollback."),
    ("tech-writer", "Documentation", "Write user, developer, and API documentation."),
    ("benchmark", "Benchmarks", "Measure speed, reliability, and resource usage."),
    ("health", "Health checks", "Record operational health and stability baselines."),
    ("context-save", "Project Brain", "Keep verified decisions, architecture, progress, and next actions available as projects grow."),
    ("learn", "Controlled learning", "Record evidence-backed improvement candidates."),
]
AGENT_IDS = [a[0] for a in AGENTS]
LABELS = {a[0]: a[1] for a in AGENTS}
REQUIRED = ["req-engineer", "task-planner"]

STYLES: list[dict] = [
    {"id": "app-it", "name": "Let Lyra guide me", "accent": "violet",
     "description": "Start with your idea. Lyra asks a few questions and recommends the smallest useful team.",
     "team": []},
    {"id": "sdlc", "name": "Complete build", "accent": "violet",
     "description": "Take the product from a clear idea through building, checks, documentation, and launch preparation.",
     "team": ["req-engineer", "sw-architect", "sw-developer", "qa-engineer", "security-auditor", "devops-engineer"]},
    {"id": "mvp", "name": "Fast first version", "accent": "coral",
     "description": "Build the smallest useful version quickly, test it, and leave clear instructions for using it.",
     "team": ["req-engineer", "sw-developer", "qa-engineer", "tech-writer"]},
    {"id": "planning", "name": "Plan before building", "accent": "blue",
     "description": "Work out the product, structure, and delivery plan without writing application code yet.",
     "team": ["req-engineer", "spec", "sw-architect", "task-planner", "proj-manager", "context-save"]},
    {"id": "review", "name": "Review and improve", "accent": "purple",
     "description": "Open an existing project to find problems, test important journeys, and recommend improvements.",
     "team": ["code-reviewer", "qa-engineer", "debugger", "security-auditor", "tech-writer"]},
]

INSTRUCTION = (
    "Lyra is the permanent user-facing project guide. Use the internal ultimate-builder:app-it skill, "
    "keep internal skill names and orchestration out of user-facing messages, and work only inside the "
    "selected workspace. Vocabulary: when speaking to the user these are AGENTS — the requirements agent, "
    "the development agent, the QA agent. Never call them skills, specialists, playbooks, or subagents in a "
    "user-facing message; those are internal words. Agents verify and commit their own work; Lyra "
    "coordinates and judges it from their reports, and her own edits are saved automatically. Never push "
    "remotely unless the user explicitly asks."
)
FIRST_TURN_GATE = (
    "The project listing below, together with your workspace snapshot, IS the inspection — do not call file, "
    "search, or terminal tools before greeting. Greet the user warmly as Lyra, briefly say what the project "
    "appears to be (or that it is empty) from what you were given, and ask exactly ONE short question about "
    "what they want to build or change. Inspect files later, once you know what they actually want. "
    "Recommend the smallest useful agent team later and ask permission before changing it."
)
REQUIREMENTS_GATE = (
    "Requirements is a permanent project capability, not the speaker for every turn. Activate it for the first "
    "meaningful product brief when no approved requirements exist, while its interview is active, when the user "
    "explicitly asks to revise requirements, or when a request materially changes product scope, user-visible "
    "behavior, data, permissions, integrations, or acceptance criteria. Do not activate or reload it for "
    "greetings, status questions, explanations, approvals, pause/stop commands, ordinary in-scope feedback, "
    "implementation details already covered by approved requirements, or minor fixes. If requirements.md "
    "already covers the request, Lyra handles the turn directly. When Requirements is genuinely needed, load "
    'skill_view(name="ultimate-builder:req-engineer") and run its interactive playbook in this conversation; '
    "do not delegate it. Complete its relevant interview, Grill, design-space exploration, prototype choice, "
    "requirements.md update, and approval gate before downstream work affected by that change. Once approved, "
    "emit the done marker and do not restart it unless a later material change requires a focused delta."
)
TEAM_GATE = (
    "Recommend only the smallest useful team. Emit APP_IT_SKILLS_SET to open editable checkboxes, but do not "
    "treat that marker as approval and do not use newly proposed agents. Wait for the user's dashboard "
    "confirmation, delivered as IDRAK_INTERNAL_SKILLS_UPDATE; that confirmed selection is authoritative."
)

SETUP_BEGIN, SETUP_END = "IDRAK_INTERNAL_SETUP_BEGIN", "IDRAK_INTERNAL_SETUP_END"
TEAM_BEGIN, TEAM_END = "IDRAK_INTERNAL_SKILLS_UPDATE_BEGIN", "IDRAK_INTERNAL_SKILLS_UPDATE_END"
GREETING_REQUEST = "Start this project conversation now with Lyra's greeting and first focused question."


def normalise_team(ids: list[str] | None) -> list[str]:
    chosen = {i for i in (ids or []) if i in LABELS}
    chosen.update(REQUIRED)
    return [i for i in AGENT_IDS if i in chosen]


def project_listing(root: Path, limit: int = 40) -> str:
    try:
        entries = sorted(p for p in root.iterdir() if not p.name.startswith("."))
    except OSError:
        return "(listing unavailable)"
    if not entries:
        return "(empty folder)"
    lines = [f"{p.name}{'/' if p.is_dir() else ''}" for p in entries[:limit]]
    if len(entries) > limit:
        lines.append(f"… and {len(entries) - limit} more")
    readme = root / "README.md"
    if readme.is_file():
        try:
            lines.append("README.md starts: " + readme.read_text(encoding="utf-8", errors="replace")[:400])
        except OSError:
            pass
    return "\n".join(lines)


PROFILES = ("personal", "reusable", "production")


WEBSITE_GATE = (
    "Websites are judged the way a visitor sees them. Developers: when "
    ".lyra/kit/reference/index.html exists it is the template's live demo — the "
    "approved look and motion; read it and reuse its techniques (or code) for each "
    "effect instead of re-inventing them from the spec text. QA (every website, "
    "every profile): after `npm run build`, run `node .lyra/kit/site-check.mjs dist "
    "--compare .lyra/kit/reference/index.html` (drop --compare when there is no "
    "reference), fix-route every problem it lists, then open each contact sheet it "
    "names and check every section and effect against the reference and "
    "requirements.md. Exit code 3 means no browser: the verdict is BLOCKED, never "
    "APPROVED. A website that was not opened in a real browser cannot pass QA.")

KIND_SKILLS = {
    "website": "ultimate-builder:web-cinematic",
    "video": "ultimate-builder:business-motion-film",
    "slides": "powerpoint",
}


def setup_message(root: Path, team: list[str], models: dict | None, brief: str,
                  profile: str | None = None, kind: str | None = None,
                  template: dict | None = None) -> str:
    payload = {
        "instruction": INSTRUCTION,
        "first_turn_gate": FIRST_TURN_GATE,
        "requirements_gate": REQUIREMENTS_GATE,
        "team_selection_gate": TEAM_GATE,
        "project_listing": project_listing(root),
        "workspace": str(root),
        "enabled_specialists": team,
        "enabled_specialist_labels": [LABELS[i] for i in team],
        "specialist_models": models or {},
        "user_request": brief.strip() or GREETING_REQUEST,
    }
    if profile in PROFILES:
        payload["build_profile"] = profile
    if kind in KIND_SKILLS or kind == "app":
        payload["project_kind"] = kind
        if kind in KIND_SKILLS:
            payload["kind_skill"] = KIND_SKILLS[kind]
        if kind == "website":
            payload["website_gate"] = WEBSITE_GATE
    if template:
        payload["template"] = {"id": template["id"], "name": template.get("name", template["id"])}
        payload["template_spec"] = template.get("spec", "")
        payload["template_gate"] = (
            "The owner chose this template as the starting design. Requirements runs a delta "
            "interview: confirm the template fits, then ask what to change (brand, words, "
            "colours, sections, images), one question per message. Do not re-ask what the "
            "template already decides. Record the template and the agreed changes in requirements.md.")
        media = template.get("media") or {}
        if media.get("ask"):
            payload["media_gate"] = (
                "This template is built on real footage or photos. In the requirements "
                f"interview ask this as its own question: \"{media['ask']}\" Files the owner "
                "attaches land in assets/uploads/. Video → `.lyra/kit/frames`; cut-outs → "
                "`.lyra/kit/cutout`; AI pictures (only after the owner says yes; each uses "
                "their ChatGPT plan) → `.lyra/kit/imagine`. Never pass AI pictures off as "
                "real photos of a real product, place or person.")
    return f"{SETUP_BEGIN} {json.dumps(payload, ensure_ascii=False)} {SETUP_END}"


def team_message(team: list[str], models: dict | None) -> str:
    payload = {
        "enabled_specialists": team,
        "enabled_specialist_labels": [LABELS[i] for i in team],
        "specialist_models": models or {},
    }
    return f"{TEAM_BEGIN} {json.dumps(payload, ensure_ascii=False)} {TEAM_END}"


def _payload(text: str, begin: str, end: str) -> dict | None:
    if not text.startswith(begin):
        return None
    body = text[len(begin):]
    if end in body:
        body = body[: body.rindex(end)]
    try:
        data = json.loads(body.strip())
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def describe_internal(text: str) -> dict | None:
    """How an internal setup/team message is shown in the chat, or None."""
    setup = _payload(text, SETUP_BEGIN, SETUP_END)
    if setup is not None:
        request = str(setup.get("user_request") or "")
        if request and request != GREETING_REQUEST:
            return {"role": "user", "content": request, "kind": "chat"}
        return {"role": "user", "content": "Project opened", "kind": "auto"}
    team = _payload(text, TEAM_BEGIN, TEAM_END)
    if team is not None:
        labels = team.get("enabled_specialist_labels") or []
        return {"role": "user", "content": "Team updated: " + ", ".join(map(str, labels)), "kind": "auto"}
    return None


_GOAL_HINTS = {
    "qa-engineer": r"\bqa\b|quality assurance",
    "sw-developer": r"\bdevelop",
    "task-planner": r"task[- ]planner|task planning",
    "req-engineer": r"requirements",
    "debugger": r"\bdebug",
}


def agent_for_goal(goal: str) -> str | None:
    """Which team member a delegated goal is for ("Act as … sw-developer …")."""
    import re

    text = (goal or "").lower()
    for agent_id in AGENT_IDS:
        if agent_id in text:
            return agent_id
    for agent_id, label in LABELS.items():
        if label.lower() in text:
            return agent_id
    for agent_id, pattern in _GOAL_HINTS.items():
        if re.search(pattern, text):
            return agent_id
    return None
