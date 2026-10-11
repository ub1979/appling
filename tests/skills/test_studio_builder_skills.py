"""website-builder, deck-builder and video-builder: shaped like every other
playbook, reachable from the routing that uses them, and the deck check
finds real slide problems in a real browser."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = (REPO / "plugins" / "ultimate-builder" / "skills" / "ultimate-app-builder"
             / "references" / "workflows")
SKILLS = ("website-builder", "deck-builder", "video-builder")
DECK_CHECK = WORKFLOWS / "deck-builder" / "scripts" / "deck-check.mjs"
# The deck check drives a real Chrome and loads reveal.js and playwright-core
# from the network, so it runs only when asked for (never in CI):
#   APPLING_BROWSER_TESTS=1 pytest tests/skills/test_studio_builder_skills.py
browser = pytest.mark.skipif(
    not os.environ.get("APPLING_BROWSER_TESTS") or shutil.which("node") is None,
    reason="browser test: set APPLING_BROWSER_TESTS=1 (needs node, Chrome and the network)")


@pytest.mark.parametrize("name", SKILLS)
def test_skill_frontmatter_follows_the_rules(name):
    text = (WORKFLOWS / name / "SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"^name: (.*)$", text, re.MULTILINE).group(1) == name
    desc = re.search(r"^description: (.*)$", text, re.MULTILINE).group(1)
    assert len(desc) <= 60 and desc.endswith("."), desc
    body = text.split("---", 2)[2]
    assert len(body.splitlines()) <= 500
    for section in ("## When to Use", "## Prerequisites", "## How to Run", "## Quick Reference",
                    "## Procedure", "## Pitfalls", "## Verification"):
        assert section in body, (name, section)


@pytest.mark.parametrize("name", SKILLS)
def test_every_referenced_file_ships_with_the_skill(name):
    folder = WORKFLOWS / name
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    refs = set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", text))
    assert refs, name
    for ref in refs:
        assert (folder / ref).is_file(), (name, ref)


def test_routing_points_at_registered_playbooks():
    import importlib.util

    from lyra_lite import agents

    spec = importlib.util.spec_from_file_location("ub_plugin", REPO / "plugins" / "ultimate-builder" / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    for kind, skill in agents.KIND_SKILLS.items():
        name = skill.split(":", 1)[1]
        assert name in plugin._SPECIALIST_SKILLS, (kind, skill)
        assert (WORKFLOWS / name / "SKILL.md").is_file(), (kind, skill)
    # Every agent the team picker offers has a playbook to be delegated into.
    for agent_id in agents.AGENT_IDS:
        assert (WORKFLOWS / agent_id / "SKILL.md").is_file(), agent_id


def test_slides_get_their_playbook_with_or_without_a_template(tmp_path):
    from lyra_lite import agents

    for template in (None, {"id": "deck-pitch", "name": "Investor Pitch", "spec": "x"}):
        text = agents.setup_message(tmp_path, ["req-engineer"], None, "A deck", kind="slides", template=template)
        payload = json.loads(text[len(agents.SETUP_BEGIN):text.rindex(agents.SETUP_END)])
        assert payload["kind_skill"] == agents.KIND_SKILLS["slides"]


def _deck(tmp_path: Path, body: str) -> Path:
    reveal = REPO / "lyra_lite" / "templates" / "deck-pitch" / "demo" / "index.html"
    # Reuse the template's own reveal.js tags so the test needs no extra network.
    tags = re.findall(r'<(?:link[^>]+reveal[^>]+|script src="[^"]+reveal[^"]+"></script)>', reveal.read_text())
    deck = tmp_path / "deck"
    deck.mkdir()
    (deck / "index.html").write_text(
        "<!doctype html><html><head>" + "".join(t for t in tags if t.startswith("<link")) + "</head><body>"
        '<div class="reveal"><div class="slides">' + body + "</div></div>"
        + "".join(t for t in tags if t.startswith("<script"))
        + '<script>Reveal.initialize({hash:true,width:1280,height:720,margin:0});</script></body></html>')
    return deck


def _check(deck: Path, out: Path, *extra: str) -> tuple[int, dict]:
    run = subprocess.run(["node", str(DECK_CHECK), str(deck), "--out", str(out), *extra],
                         capture_output=True, text=True, timeout=240)
    if run.returncode == 3:
        pytest.skip("no browser for the deck check: " + run.stdout.strip()[:200])
    return run.returncode, json.loads((out / "report.json").read_text())


@browser
def test_deck_check_flags_cut_off_tiny_and_crowded_slides(tmp_path):
    words = " ".join(f"word{i}" for i in range(60))
    deck = _deck(tmp_path, (
        '<section><h2>A clear point.</h2><p style="font-size:28px">Short.</p>'
        '<div style="position:absolute;left:1100px;top:0;width:600px;height:600px"></div></section>'
        '<section><h2>Crowded</h2><p style="font-size:11px">tiny label</p>'
        '<p style="position:absolute;left:1150px;top:300px;width:500px;font-size:28px">This line runs off</p>'
        f'<p style="font-size:24px">{words}</p><aside class="notes">{words} {words}</aside></section>'))
    code, report = _check(deck, tmp_path / "report", "--pdf", str(tmp_path / "deck.pdf"))
    assert code == 1 and report["slides"] == 2
    found = "\n".join(report["findings"])
    assert "[slide 2" in found and "[slide 1" not in found  # a decorative shape may bleed
    assert "runs off the slide" in found and "smaller than 16px" in found and "words on screen" in found
    pages = re.findall(rb"/Type\s*/Page[^s]", (tmp_path / "deck.pdf").read_bytes())
    assert len(pages) == 2


@browser
def test_deck_check_blocks_a_page_that_is_not_a_deck(tmp_path):
    page = tmp_path / "site"
    page.mkdir()
    (page / "index.html").write_text("<p>not a deck</p>")
    run = subprocess.run(["node", str(DECK_CHECK), str(page), "--out", str(tmp_path / "r")],
                         capture_output=True, text=True, timeout=240)
    assert run.returncode == 3 and "BLOCKED" in run.stdout
