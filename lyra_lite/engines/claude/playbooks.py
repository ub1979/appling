"""Appling's builder playbooks as a Claude Code plugin, and the notes that
teach Claude Code to follow them."""

from __future__ import annotations

import json
from pathlib import Path

from lyra_lite.engines.claude.common import RECALL_TOOL

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / "plugins" / "ultimate-builder" / "skills"
# The shared design skills the playbooks load by bare name
# (skill_view(name="design-taste-frontend"), "design-tokens", "a11y-audit" …).
DESIGN_SKILLS_ROOT = REPO_ROOT / "skills" / "ui-ux"
# Other repo skills the playbooks name for a project kind (slides → .pptx).
EXTRA_SKILLS = [REPO_ROOT / "skills" / "productivity" / "powerpoint" / "SKILL.md"]
PLUGIN_NAME = "ultimate-builder"


def _skill_name(skill_md: Path) -> str:
    try:
        for line in skill_md.read_text(encoding="utf-8").splitlines()[:8]:
            if line.startswith("name:"):
                return line.split(":", 1)[1].strip().strip("'\"") or skill_md.parent.name
    except OSError:
        pass
    return skill_md.parent.name


def _skill_index() -> str:
    lines = []
    for path in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        lines.append(f"- ultimate-builder:{path.parent.name} → {path}")
    return "\n".join(lines)


def builder_plugin_dir() -> Path:
    """Appling's builder playbooks as a native Claude Code plugin.

    The playbooks are already SKILL.md files. Linked into a plugin called
    ``ultimate-builder`` they load with Claude Code's own Skill tool under the
    same names Hermes uses (``ultimate-builder:req-engineer`` …), instead of
    relying on the model choosing to read a file.
    """
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "lyra-lite" / "claude-plugin" / PLUGIN_NAME
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    manifest = {"name": PLUGIN_NAME, "version": "1.0.0",
                "description": "Appling's application-builder playbooks."}
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    skills = root / "skills"
    skills.mkdir(exist_ok=True)
    wanted = {path.parent.name: path.parent for path in SKILLS_ROOT.rglob("SKILL.md")}
    for path in [*sorted(DESIGN_SKILLS_ROOT.rglob("SKILL.md")), *EXTRA_SKILLS]:
        if path.is_file():
            wanted.setdefault(_skill_name(path), path.parent)
    for link in skills.iterdir():
        if link.name not in wanted or not link.is_symlink() or link.resolve() != wanted[link.name].resolve():
            if link.is_symlink() or link.is_file():
                link.unlink()
    for name, target in wanted.items():
        link = skills / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)
    return root


def engine_notes() -> str:
    try:
        app_it = (SKILLS_ROOT / "app-it" / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        app_it = ""
    return f"""
## Running on Claude Code

Appling's playbooks are installed as Claude Code skills named
`{PLUGIN_NAME}:<name>`. Translate the playbooks' tool names:
- `skill_view(name="{PLUGIN_NAME}:X")` → load it with the **Skill** tool as
  `{PLUGIN_NAME}:X`, then follow it exactly. Never improvise a phase whose
  playbook you have not loaded. A bare `skill_view(name="X")` (design skills
  such as `design-taste-frontend`, `design-tokens`, `a11y-audit`) is
  `{PLUGIN_NAME}:X` too.
- Any interface: load `{PLUGIN_NAME}:color-and-ux` before choosing colours,
  type or layout, and run its `palette.py check` on the final palette.
- `delegate_task` → the Agent (Task) tool. Agents always run in the
  background: start them (several in one message to work in parallel), tell
  the owner in a sentence or two what is now running, and end your turn.
  Each agent's report arrives later as its own message; react to it then.
  Never wait or poll for an agent. The owner can message you at any time
  while agents work — answer from the project files and what you know.
  Tell each agent which `{PLUGIN_NAME}:` skill to load, its task, the files
  it owns and the test command.
- `clarify` → ask in your reply and end the turn.
- `project_recall` → the `{RECALL_TOOL}` tool (search this project's memory).
- `terminal` → Bash; `read_file`/`write_file`/`patch`/`search_files` →
  Read/Write/Edit/Grep/Glob; `todo` → TodoWrite.

Requirements: before asking any requirements question, load
`{PLUGIN_NAME}:req-engineer` with the Skill tool and follow its conversation
contract — one question per message.

## The app-it playbook (already loaded)

{app_it}
"""
