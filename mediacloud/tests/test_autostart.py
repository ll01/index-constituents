import sys
from pathlib import Path

from mediacloud.autostart import launchd_plist, schtasks_command, systemd_unit


def test_systemd_unit_contents():
    unit = systemd_unit("watch", Path("/home/me/mediacloud.toml"))
    assert f"ExecStart={sys.executable} -m mediacloud --config /home/me/mediacloud.toml watch" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit


def test_systemd_unit_quotes_spaced_paths():
    unit = systemd_unit("serve", Path("/home/me/My Files/mediacloud.toml"))
    assert '"/home/me/My Files/mediacloud.toml"' in unit


def test_launchd_plist_contents():
    plist = launchd_plist("watch", Path("/Users/me/mediacloud.toml"))
    assert "<string>com.mediacloud.watch</string>" in plist
    assert f"<string>{sys.executable}</string>" in plist
    assert "<string>--config</string>" in plist
    assert "<string>/Users/me/mediacloud.toml</string>" in plist
    assert "<key>RunAtLoad</key><true/>" in plist


def test_schtasks_command_contents():
    cmd = schtasks_command("watch", None)
    assert cmd[:2] == ["schtasks", "/Create"]
    assert "MediaCloud watch" in cmd
    tr = cmd[cmd.index("/TR") + 1]
    assert "-m mediacloud watch" in tr
