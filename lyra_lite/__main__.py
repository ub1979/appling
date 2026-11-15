"""Start Appling: ``python -m lyra_lite [--port 9200] [--no-open]``."""

from __future__ import annotations

import argparse
import os
import secrets
import webbrowser


def _stable_token() -> str:
    """One private token per Appling home, so open tabs survive a restart."""
    from lyra_lite.config import app_home

    path = app_home() / "token"
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(value + "\n")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(prog="lyra_lite")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9201)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--token", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    import logging
    from lyra_lite.config import app_home
    from lyra_lite.server import create_app, projects_root

    home = app_home()
    (home / "logs").mkdir(parents=True, exist_ok=True, mode=0o700)
    logging.basicConfig(filename=home / "logs" / "appling.log", level=logging.INFO)

    # Never let a tool fall back to Lyra's own folder as its working directory.
    root = projects_root()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)

    import uvicorn

    token = args.token or _stable_token()
    app = create_app(token=token)
    url = f"http://{args.host}:{args.port}/"
    from lyra_lite import VERSION_LABEL

    print(f"Appling {VERSION_LABEL} is running at {url}", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
