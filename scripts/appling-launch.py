#!/usr/bin/env python3
"""Start/stop the two local Appling checkouts without crossing engine boundaries."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

BASE = Path(__file__).resolve().parents[1]


def main(engine: str, action: str) -> int:
    codex = engine == "codex"
    root = BASE / ".worktrees/appling-codex-base" if codex else BASE
    python = root / ("apps/appling-runtime/.venv/bin/python" if codex else ".venv/bin/python")
    port = 9201 if codex else 9200
    label = "Codex" if codex else "Hermes"
    url = f"http://127.0.0.1:{port}/"
    home = Path(os.environ.get("APPLING_HOME" if codex else "HERMES_HOME")
                or Path.home() / (".appling-codex" if codex else ".hermes")).expanduser().resolve()

    def matches(command: str) -> bool:
        try:
            prefix = f"{python} -m lyra_lite "
            if not command.startswith(prefix):
                return False
            args = shlex.split(command[len(prefix):])
            return args[args.index("--port") + 1] == str(port)
        except (ValueError, IndexError):
            return False

    def processes() -> set[int]:
        output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
        found = set()
        for line in output.splitlines():
            fields = line.strip().split(None, 1)
            if len(fields) == 2 and matches(fields[1]):
                found.add(int(fields[0]))
        return found

    def listeners() -> set[int]:
        result = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                                capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise RuntimeError("Could not inspect the server port safely.")
        return {int(pid) for pid in result.stdout.split()}

    def open_page():
        if os.environ.get("APPLING_NO_OPEN") != "1":
            webbrowser.open(url)

    if not shutil.which("lsof"):
        raise RuntimeError("lsof is required to check which server owns the port.")
    owned = processes()
    if action == "stop":
        if not owned:
            print(f"{label} Appling is not running from {root}.")
            return 0
        for pid in owned:
            # Recheck identity immediately before sending the signal.
            if pid in processes():
                os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not (owned & processes()):
                print(f"Stopped {label} Appling. The other version was left running.")
                return 0
            time.sleep(.2)
        raise RuntimeError(f"{label} is still shutting down. Work was not force-killed; rerun its stop script shortly.")

    occupied = listeners()
    if occupied:
        if not occupied <= owned:
            raise RuntimeError(f"Port {port} belongs to another process. Nothing was stopped.")
        print(f"{label} Appling is already running: {url}")
        open_page()
        return 0
    if owned:
        raise RuntimeError(f"{label} Appling is already starting or shutting down. Try again shortly.")
    if not root.is_dir():
        raise RuntimeError(f"The separate {label} checkout is missing: {root}")
    if not python.is_file():
        if codex:
            raise RuntimeError(f"The Codex runtime is missing: {python}. Restore its runtime environment first.")
        if not shutil.which("uv"):
            raise RuntimeError("Install uv first: https://docs.astral.sh/uv/")
        subprocess.run(["uv", "sync", "--extra", "dev"], cwd=root, check=True)

    ui = root / "lyra_lite/ui"
    built = ui / "dist/index.html"
    sources = [ui / "index.html", ui / "package.json", *list((ui / "src").rglob("*"))]
    if not built.exists() or any(p.is_file() and p.stat().st_mtime > built.stat().st_mtime for p in sources):
        print(f"Building {label} Appling's screen...", flush=True)
        if not (ui / "node_modules").is_dir():
            subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ui, check=True)
        subprocess.run(["npm", "run", "build"], cwd=ui, check=True)
    env = {**os.environ, "PYTHONPATH": str(root)}
    env["APPLING_HOME" if codex else "HERMES_HOME"] = str(home)
    if not codex:
        subprocess.run([str(root / ".venv/bin/hermes"), "plugins", "enable", "ultimate-builder"],
                       cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / ("appling-codex-launch.log" if codex else "appling.log")
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as output:
        proc = subprocess.Popen([str(python), "-m", "lyra_lite", "--no-open", "--port", str(port)],
                                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
    if shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(proc.pid)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(120):
        if proc.poll() is not None:
            raise RuntimeError(f"{label} did not start. Inspect {log}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                ready = response.status == 200
            if ready and listeners() <= processes() and listeners():
                print(f"{label} Appling is running: {url}\nLog: {log}")
                open_page()
                return 0
        except OSError:
            pass
        time.sleep(.25)
    raise RuntimeError(f"{label} is still starting (PID {proc.pid}). Inspect {log} before retrying.")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in {"hermes", "codex"} or sys.argv[2] not in {"start", "stop"}:
            raise RuntimeError("Usage: appling-launch.py hermes|codex start|stop")
        sys.exit(main(*sys.argv[1:]))
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
