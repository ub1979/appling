"""Make a picture with AI from the command line, on the owner's ChatGPT plan.

    python -m lyra_lite.imagine "prompt" --out assets/hero.png
        [--aspect landscape|square|portrait] [--ref picture.png ...]

It uses Hermes' ``openai-codex`` image provider, so it needs only the Codex /
ChatGPT sign-in Appling already has — no API key. ``--ref`` sends existing
pictures to edit or to keep a scene consistent ("same car, sheet removed").
Every picture uses the owner's plan allowance: only run it when the owner
agreed to AI pictures for this project.

Website projects get a wrapper at ``.lyra/kit/imagine`` so agents on any
engine can call it from a terminal.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROVIDER = REPO / "plugins" / "image_gen" / "openai-codex" / "__init__.py"


def _provider():
    spec = importlib.util.spec_from_file_location("lyra_codex_image", PROVIDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for value in vars(module).values():
        if isinstance(value, type) and value.__module__ == module.__name__ and hasattr(value, "generate"):
            return value()
    raise RuntimeError("The Codex image provider could not be loaded.")


def imagine(prompt: str, out: Path, aspect: str = "landscape", refs: list[str] | None = None) -> dict:
    provider = _provider()
    if not provider.is_available():
        return {"success": False, "error": "Not signed in to Codex/ChatGPT. Sign in once with `hermes auth codex`."}
    refs = [str(Path(r).expanduser().resolve()) for r in refs or []]
    result = provider.generate(prompt, aspect_ratio=aspect, image_url=refs[0] if refs else None,
                               reference_image_urls=refs[1:] or None)
    if not result.get("success"):
        return {"success": False, "error": result.get("error") or "image generation failed"}
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result["image"], out)
    return {"success": True, "path": str(out), "size": result.get("size")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="imagine", description=__doc__.split("\n\n")[0])
    parser.add_argument("prompt")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--aspect", default="landscape", choices=["landscape", "square", "portrait"])
    parser.add_argument("--ref", action="append", default=[], help="existing picture to edit or match (repeatable)")
    args = parser.parse_args(argv)
    result = imagine(args.prompt, args.out, args.aspect, args.ref)
    print(json.dumps(result))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
