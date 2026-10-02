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
    meta["has_demo"] = (folder / "demo" / "index.html").is_file()
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
