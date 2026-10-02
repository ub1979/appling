"""Starting templates: Lyra's own set plus the owner's private ones.

Built-in templates live in ``lyra_lite/templates/<id>/`` (``template.json``,
``spec.md``, optional ``demo/index.html``). The owner's own templates — for
example prompts they bought — live only in
``<HERMES_HOME>/lyra-lite/templates/<id>/`` on their machine and are never
copied into Lyra's source.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

BUILTIN_ROOT = Path(__file__).resolve().parent / "templates"
REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_CHECK = (Path(__file__).resolve().parent.parent / "plugins" / "ultimate-builder" / "skills"
              / "ultimate-app-builder" / "references" / "workflows" / "web-cinematic" / "scripts"
              / "site-check.mjs")
KIT_DIR = Path(".lyra") / "kit"
SKILL_SCRIPTS = SITE_CHECK.parent
KINDS = ("app", "website", "slides", "video")
MAX_SPEC_CHARS = 20_000


def user_root() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "lyra-lite" / "templates"


def _load(folder: Path, own: bool) -> dict | None:
    try:
        meta = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    meta["id"] = folder.name
    meta["own"] = own
    meta["local_demo"] = (folder / "demo" / "index.html").is_file()
    preview = meta.get("preview") if isinstance(meta.get("preview"), dict) else {}
    # Video templates show the published preview of the blocks they build on.
    meta["has_demo"] = meta["local_demo"] or bool(preview.get("video"))
    meta.setdefault("kind", "website")
    meta.setdefault("palette", [])
    return meta


def list_templates(kind: str | None = None) -> list[dict]:
    out = []
    for root, own in ((BUILTIN_ROOT, False), (user_root(), True)):
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir()):
            meta = _load(folder, own) if folder.is_dir() else None
            if meta and (kind is None or meta.get("kind") == kind):
                out.append(meta)
    return out


def _folder(tid: str) -> tuple[Path, bool] | None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", tid or ""):
        return None
    for root, own in ((user_root(), True), (BUILTIN_ROOT, False)):
        if (root / tid / "template.json").is_file():
            return root / tid, own
    return None


def get_template(tid: str) -> dict | None:
    found = _folder(tid)
    if not found:
        return None
    folder, own = found
    meta = _load(folder, own)
    if meta is None:
        return None
    try:
        meta["spec"] = (folder / "spec.md").read_text(encoding="utf-8")[:MAX_SPEC_CHARS]
    except OSError:
        meta["spec"] = ""
    return meta


def demo_dir(tid: str) -> Path | None:
    found = _folder(tid)
    if not found:
        return None
    demo = found[0] / "demo"
    return demo if (demo / "index.html").is_file() else None


def save_user_template(name: str, kind: str, spec: str, tagline: str = "") -> dict:
    name = name.strip()[:80]
    spec = spec.strip()[:MAX_SPEC_CHARS]
    if not name or not spec:
        raise ValueError("Give the template a name and paste its prompt.")
    if kind not in KINDS:
        raise ValueError("Unknown kind")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "template"
    tid, n = f"my-{slug}", 2
    while (user_root() / tid).exists():
        tid, n = f"my-{slug}-{n}", n + 1
    folder = user_root() / tid
    folder.mkdir(parents=True)
    meta = {"kind": kind, "name": name, "tagline": tagline.strip()[:140], "best_for": "", "palette": []}
    (folder / "template.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (folder / "spec.md").write_text(spec + "\n", encoding="utf-8")
    return _load(folder, True) or {}


def delete_user_template(tid: str) -> bool:
    found = _folder(tid)
    if not found or not found[1]:
        return False
    shutil.rmtree(found[0])
    return True


def _copy_if_changed(src: Path, dst: Path) -> None:
    try:
        if dst.is_file() and dst.read_bytes() == src.read_bytes():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    except OSError:
        pass


def _write_tools(kit: Path) -> None:
    """Small commands that run with Lyra's own Python (Pillow, the Codex image
    provider), whatever the project's own setup is."""
    import os
    import sys

    from hermes_constants import get_hermes_home

    py, repo, home = sys.executable, str(REPO_ROOT), str(get_hermes_home())
    tools = {
        "imagine": f'exec env PYTHONPATH="{repo}" HERMES_HOME="${{HERMES_HOME:-{home}}}" "{py}" -m lyra_lite.imagine "$@"',
        "cutout": f'exec "{py}" "{SKILL_SCRIPTS / "cutout.py"}" "$@"',
        "frames": f'exec "{py}" "{SKILL_SCRIPTS / "frames.py"}" "$@"',
    }
    kit.mkdir(parents=True, exist_ok=True)
    for name, line in tools.items():
        path = kit / name
        body = f"#!/bin/sh\n# Lyra kit: {name} — see the web-cinematic skill.\n{line}\n"
        try:
            if not path.is_file() or path.read_text() != body:
                path.write_text(body)
                os.chmod(path, 0o755)
        except OSError:
            pass


def ensure_website_kit(root: Path, tid: str | None) -> None:
    """Put the site checker, and the chosen template's live demo as the
    reference design, inside the project (``.lyra/kit/``, git-ignored) so
    every helper on any engine can run and read them."""
    kit = Path(root) / KIT_DIR
    if SITE_CHECK.is_file():
        _copy_if_changed(SITE_CHECK, kit / "site-check.mjs")
    _write_tools(kit)
    demo = demo_dir(tid) if tid else None
    if demo is None:
        return
    for src in demo.rglob("*"):
        if src.is_file() and not any(part.startswith(".") for part in src.relative_to(demo).parts):
            _copy_if_changed(src, kit / "reference" / src.relative_to(demo))
