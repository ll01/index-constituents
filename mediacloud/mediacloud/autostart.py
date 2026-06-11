"""Install `mediacloud watch` (and optionally `serve`) into the OS's native
scheduler so they start at login: systemd user units on Linux, launchd agents
on macOS, Task Scheduler on Windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SYSTEMD_UNIT = """\
[Unit]
Description=MediaCloud {command}
After=network.target

[Service]
ExecStart={argv}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""

LAUNCHD_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.mediacloud.{command}</string>
  <key>ProgramArguments</key><array>
{args_xml}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
"""


def _argv(command: str, config: Path | None) -> list[str]:
    argv = [sys.executable, "-m", "mediacloud"]
    if config is not None:
        argv += ["--config", str(config)]
    return argv + [command]


def systemd_unit(command: str, config: Path | None) -> str:
    quoted = " ".join(f'"{a}"' if " " in a else a for a in _argv(command, config))
    return SYSTEMD_UNIT.format(command=command, argv=quoted)


def launchd_plist(command: str, config: Path | None) -> str:
    args_xml = "\n".join(f"    <string>{a}</string>" for a in _argv(command, config))
    return LAUNCHD_PLIST.format(command=command, args_xml=args_xml)


def schtasks_command(command: str, config: Path | None) -> list[str]:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    argv = [str(exe)] + _argv(command, config)[1:]
    tr = " ".join(f'"{a}"' if " " in a else a for a in argv)
    return ["schtasks", "/Create", "/F", "/SC", "ONLOGON",
            "/TN", f"MediaCloud {command}", "/TR", tr]


def install(commands: list[str], config: Path | None, dry_run: bool = False) -> None:
    if sys.platform.startswith("linux"):
        unit_dir = Path("~/.config/systemd/user").expanduser()
        for command in commands:
            unit = unit_dir / f"mediacloud-{command}.service"
            content = systemd_unit(command, config)
            if dry_run:
                print(f"would write {unit}:\n{content}")
                continue
            unit_dir.mkdir(parents=True, exist_ok=True)
            unit.write_text(content)
            print(f"wrote {unit}")
        if not dry_run:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            for command in commands:
                subprocess.run(
                    ["systemctl", "--user", "enable", "--now",
                     f"mediacloud-{command}.service"], check=True)
                print(f"enabled mediacloud-{command} (starts at login, running now)")
            print("Tip: `loginctl enable-linger $USER` keeps it running while logged out.")
    elif sys.platform == "darwin":
        agent_dir = Path("~/Library/LaunchAgents").expanduser()
        for command in commands:
            plist = agent_dir / f"com.mediacloud.{command}.plist"
            content = launchd_plist(command, config)
            if dry_run:
                print(f"would write {plist}:\n{content}")
                continue
            agent_dir.mkdir(parents=True, exist_ok=True)
            plist.write_text(content)
            subprocess.run(["launchctl", "load", "-w", str(plist)], check=True)
            print(f"loaded {plist}")
    elif sys.platform == "win32":
        for command in commands:
            cmd = schtasks_command(command, config)
            if dry_run:
                print(f"would run: {subprocess.list2cmdline(cmd)}")
                continue
            subprocess.run(cmd, check=True)
            print(f"registered scheduled task 'MediaCloud {command}' (runs at logon)")
    else:
        raise SystemExit(f"Don't know how to autostart on {sys.platform}.")


def uninstall(commands: list[str]) -> None:
    if sys.platform.startswith("linux"):
        for command in commands:
            unit = f"mediacloud-{command}.service"
            subprocess.run(["systemctl", "--user", "disable", "--now", unit], check=False)
            path = Path("~/.config/systemd/user").expanduser() / unit
            path.unlink(missing_ok=True)
            print(f"removed {unit}")
    elif sys.platform == "darwin":
        for command in commands:
            plist = Path("~/Library/LaunchAgents").expanduser() / f"com.mediacloud.{command}.plist"
            subprocess.run(["launchctl", "unload", str(plist)], check=False)
            plist.unlink(missing_ok=True)
            print(f"removed {plist}")
    elif sys.platform == "win32":
        for command in commands:
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", f"MediaCloud {command}"],
                           check=False)
            print(f"removed scheduled task 'MediaCloud {command}'")
    else:
        raise SystemExit(f"Don't know how to autostart on {sys.platform}.")
