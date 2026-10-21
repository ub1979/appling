"""Browse opens the computer's own folder dialog; where there is none, the
screen falls back to Appling's folder list."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient

from lyra_lite.folder_picker import PickerUnavailable, pick_folder, picker_command


def _done(code: int, out: str = "", err: str = ""):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, code, out, err)


def _which(*found: str):
    return lambda name: f"/usr/bin/{name}" if name in found else None


def test_each_system_gets_its_own_dialog(tmp_path):
    mac = picker_command(str(tmp_path), 'Pick "it"', system="Darwin")
    assert mac[0] == "osascript" and 'Pick \\"it\\"' in mac[-1] and str(tmp_path) in mac[-1]
    win = picker_command("C:\\Users\\o'neil", "Pick", system="Windows", which=_which("powershell"))
    assert win[0].endswith("powershell") and "-STA" in win and "o''neil" in win[-1]
    gtk = picker_command("/home/a", "Pick", system="Linux", which=_which("zenity", "kdialog"),
                         env={"DISPLAY": ":0"})
    assert gtk[0] == "zenity" and "--directory" in gtk and "--filename=/home/a/" in gtk
    kde = picker_command("/home/a", "Pick", system="Linux", which=_which("kdialog"),
                         env={"WAYLAND_DISPLAY": "w"})
    assert kde[:3] == ["kdialog", "--getexistingdirectory", "/home/a"]


def test_no_dialog_means_unavailable_not_a_crash():
    with pytest.raises(PickerUnavailable):
        picker_command("", "Pick", system="Linux", which=_which("zenity"), env={})
    with pytest.raises(PickerUnavailable):
        picker_command("", "Pick", system="Linux", which=_which(), env={"DISPLAY": ":0"})
    with pytest.raises(PickerUnavailable):
        picker_command("", "Pick", system="Windows", which=_which())


def test_chosen_cancelled_and_failed(tmp_path):
    pick = dict(system="Linux", which=_which("zenity"), env={"DISPLAY": ":0"})
    assert pick_folder(str(tmp_path), "Pick", run=_done(0, "/home/a/app/\n"), **pick) == "/home/a/app"
    assert pick_folder("", "Pick", run=_done(1), **pick) is None  # Cancel
    with pytest.raises(PickerUnavailable, match="cannot open display"):
        pick_folder("", "Pick", run=_done(5, err="cannot open display"), **pick)

    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    with pytest.raises(PickerUnavailable):
        pick_folder("", "Pick", run=missing, **pick)


def test_a_start_folder_that_does_not_exist_is_dropped(tmp_path):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 1, "", "")

    pick_folder(str(tmp_path / "gone"), "Pick", system="Linux", which=_which("zenity"),
                env={"DISPLAY": ":0"}, run=run)
    assert not any(part.startswith("--filename") for part in seen["cmd"])


def test_the_dialog_never_opens_for_a_page_on_another_device():
    from lyra_lite.server import create_app

    client = TestClient(create_app(token="t"), base_url="http://127.0.0.1")  # caller is "testclient"
    res = client.post("/api/folders/pick", json={"start": "", "title": "Pick"}, headers={"x-lyra-token": "t"})
    assert res.status_code == 501
