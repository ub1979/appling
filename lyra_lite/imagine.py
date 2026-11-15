"""Generate or edit a project image through the OpenAI Images API.

Only run after the owner agrees to AI images and their API cost. Credentials
come from OPENAI_API_KEY; no Hermes auth or subscription credential extraction.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path

import httpx


def imagine(prompt: str, out: Path, aspect: str = "landscape", refs: list[str] | None = None) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"success": False, "error": "Image generation requires OPENAI_API_KEY and uses paid API credits. Ask the owner before generating."}
    from lyra_lite.settings import _section
    model = str(_section().get("image_model") or "gpt-image-1.5")
    size = {"landscape": "1536x1024", "square": "1024x1024", "portrait": "1024x1536"}[aspect]
    data = {"model": model, "prompt": prompt, "size": size, "n": 1}
    try:
        with ExitStack() as stack:
            client = stack.enter_context(httpx.Client(timeout=180))
            headers = {"Authorization": "Bearer " + key}
            if refs:
                files = [("image[]", (Path(r).name, stack.enter_context(open(Path(r).expanduser(), "rb")))) for r in refs]
                response = client.post("https://api.openai.com/v1/images/edits", headers=headers,
                                       data={k: str(v) for k, v in data.items()}, files=files)
            else:
                response = client.post("https://api.openai.com/v1/images/generations", headers=headers, json=data)
            if response.status_code != 200:
                return {"success": False, "error": f"OpenAI Images API returned HTTP {response.status_code}; no image was saved."}
            image = base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(image)
            return {"success": True, "path": str(out), "size": size}
    except (OSError, ValueError, KeyError, IndexError, httpx.HTTPError) as exc:
        return {"success": False, "error": f"Image generation failed ({type(exc).__name__}); no credentials were logged."}


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
