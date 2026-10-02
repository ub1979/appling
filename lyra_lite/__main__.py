"""Start APP IT: ``python -m lyra_lite [--port 9200] [--no-open]``."""

from __future__ import annotations

import argparse
import os
import secrets
import webbrowser


def _stable_token() -> str:
    """One private token per APP IT home, so open tabs survive a restart."""
    from hermes_constants import get_hermes_home

    path = get_hermes_home() / "lyra-lite" / "token"
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
    parser.add_argument("--port", type=int, default=9200)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--token", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv()
    try:
        from hermes_logging import setup_logging

        setup_logging(mode="gateway")
    except Exception:
        pass

    from lyra_lite.engines.hermes import enable_gateway_approvals
    from lyra_lite.server import create_app, projects_root

    enable_gateway_approvals()

    # Never let a tool fall back to Lyra's own folder as its working directory.
    root = projects_root()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)

    try:
        from tools.approval import load_permanent_allowlist

        load_permanent_allowlist()
    except Exception:
        pass

    import uvicorn

    token = args.token or _stable_token()
    app = create_app(token=token)
    url = f"http://{args.host}:{args.port}/"
    from lyra_lite import VERSION_LABEL

    print(f"APP IT {VERSION_LABEL} is running at {url}", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
