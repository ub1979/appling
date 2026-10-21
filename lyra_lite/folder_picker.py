"""The computer's own folder dialog (Finder, Explorer, GTK/KDE), opened by Appling.

Appling runs on the owner's computer, so Browse can show the real system
dialog instead of a list drawn in the page. Where none exists (a Linux box
without zenity or kdialog, no display, a phone on the network) the caller
falls back to Appling's own folder list.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

PICK_TIMEOUT_S = 15 * 60  # the owner may wander off with the dialog open


class PickerUnavailable(RuntimeError):
    """This computer has no folder dialog Appling can open."""


def _applescript_text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _powershell_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def picker_command(start: str, title: str, *, system: str | None = None,
                   which: Callable[[str], str | None] = shutil.which,
                   env: dict[str, str] | None = None) -> list[str]:
    """The command that shows the folder dialog and prints the chosen path."""
    system = system or platform.system()
    env = os.environ if env is None else env
    if system == "Darwin":
        script = f"choose folder with prompt {_applescript_text(title)}"
        if start:
            script += f" default location (POSIX file {_applescript_text(start)})"
        # activate first, or the dialog can open behind the browser.
        return ["osascript", "-e", "activate", "-e", f"POSIX path of ({script})"]
    if system == "Windows":
        shell = which("powershell") or which("pwsh")
        if not shell:
            raise PickerUnavailable("PowerShell isn't available.")
        script = "; ".join([
            "Add-Type -AssemblyName System.Windows.Forms",
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8",
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog",
            f"$d.Description = {_powershell_text(title)}",
            f"$d.SelectedPath = {_powershell_text(start)}",
            "$d.ShowNewFolderButton = $true",
            # A hidden topmost owner window keeps the dialog in front of the browser.
            "$w = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}",
            "if ($d.ShowDialog($w) -eq 'OK') { [Console]::Out.Write($d.SelectedPath); exit 0 } else { exit 1 }",
        ])
        return [shell, "-NoProfile", "-STA", "-Command", script]
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        raise PickerUnavailable("No desktop to show a dialog on.")
    if which("zenity"):
        start_dir = start.rstrip("/") + "/" if start else ""
        return ["zenity", "--file-selection", "--directory", f"--title={title}",
                *([f"--filename={start_dir}"] if start_dir else [])]
    if which("kdialog"):
        return ["kdialog", "--getexistingdirectory", start or str(Path.home()), "--title", title]
    raise PickerUnavailable("Install zenity or kdialog for the system folder dialog.")


def pick_folder(start: str, title: str, *, system: str | None = None,
                which: Callable[[str], str | None] = shutil.which,
                run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                env: dict[str, str] | None = None) -> str | None:
    """Show the dialog and wait. The chosen folder, or None when cancelled."""
    if start and not Path(start).is_dir():
        start = ""
    command = picker_command(start, title, system=system, which=which, env=env)
    try:
        done = run(command, capture_output=True, text=True, encoding="utf-8", timeout=PICK_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise PickerUnavailable(f"{command[0]} isn't installed.") from exc
    except subprocess.TimeoutExpired:
        return None
    chosen = (done.stdout or "").strip()
    if done.returncode == 0 and chosen:
        return chosen.rstrip("/") or "/"  # macOS ends folders with "/"
    # Every dialog exits 1 on Cancel (macOS: "User canceled", -128).
    if done.returncode == 1:
        return None
    raise PickerUnavailable((done.stderr or "").strip() or f"{command[0]} failed ({done.returncode}).")
