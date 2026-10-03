"""Install Clipdeck and its desktop integration for the current user.

System packages are installed through the distribution package manager. On
Ubuntu and Mint, GPU Screen Recorder must be installed separately because
their repositories may lack the CLI/IPC version that Clipdeck needs.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
USER_HOME = Path.home()
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", USER_HOME / ".local/share"))
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", USER_HOME / ".config"))
ARCH_PACKAGES = (
    "python", "python-gobject", "gtk3", "gtk4", "libadwaita",
    "gtk-layer-shell", "libayatana-appindicator", "gpu-screen-recorder",
    "ffmpeg", "mpv", "pipewire", "libpulse", "libnotify",
)
APT_PACKAGES = (
    "python3", "python3-gi", "gir1.2-gtk-3.0", "gir1.2-gtk-4.0",
    "gir1.2-adw-1", "gir1.2-gtklayershell-0.1",
    "gir1.2-ayatanaappindicator3-0.1", "ffmpeg", "mpv",
    "pipewire-bin", "pulseaudio-utils", "libnotify-bin",
    "libglvnd0", "libgl1", "libegl1",
)
REQUIRED_COMMANDS = ("gpu-screen-recorder", "gsr-cli", "ffmpeg", "ffprobe", "mpv")


def distro_family() -> str:
    values = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    names = {values.get("ID", ""), *values.get("ID_LIKE", "").split()}
    if "arch" in names:
        return "arch"
    if names.intersection({"ubuntu", "linuxmint"}):
        return "apt"
    raise RuntimeError(
        "Automatic dependencies are supported on Arch derivatives, Ubuntu "
        "and Linux Mint. Use --no-deps after installing dependencies manually."
    )


def as_root(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    if not shutil.which("sudo"):
        raise RuntimeError("sudo is required to install system dependencies.")
    return ["sudo", *command]


def install_dependencies() -> None:
    family = distro_family()
    if family == "arch":
        print("Installing Clipdeck dependencies from Arch repositories...", flush=True)
        subprocess.run(as_root(["pacman", "-S", "--needed", *ARCH_PACKAGES]), check=True)
        return

    print("Installing Clipdeck dependencies with apt...", flush=True)
    subprocess.run(as_root(["apt-get", "update"]), check=True)
    subprocess.run(as_root(["apt-get", "install", "-y", *APT_PACKAGES]), check=True)


def missing_commands() -> list[str]:
    missing = [name for name in REQUIRED_COMMANDS if not shutil.which(name)]
    if not (all(shutil.which(name) for name in ("pw-record", "pw-play"))
            or all(shutil.which(name) for name in ("parec", "paplay"))):
        missing.append("pw-record/pw-play or parec/paplay")
    return missing


def missing_gi_modules() -> list[str]:
    checks = (
        ("GTK 4 and Libadwaita",
         'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); '
         'from gi.repository import Gtk, Adw'),
        ("GTK 3 and a tray indicator",
         'import gi\n'
         'gi.require_version("Gtk", "3.0")\n'
         'from gi.repository import Gtk\n'
         'try:\n'
         '    gi.require_version("AyatanaAppIndicator3", "0.1")\n'
         '    from gi.repository import AyatanaAppIndicator3\n'
         'except (ImportError, ValueError):\n'
         '    gi.require_version("AppIndicator3", "0.1")\n'
         '    from gi.repository import AppIndicator3\n'),
    )
    missing = []
    for description, code in checks:
        if subprocess.run([sys.executable, "-c", code],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False).returncode:
            missing.append(description)
    return missing


def desktop_argument(value: Path) -> str:
    """Quote a path for an XDG Desktop Entry Exec field (not shell syntax)."""
    text = str(value).replace("%", "%%")
    if any(ord(char) < 32 for char in text):
        raise RuntimeError("Install path contains control characters unsupported by desktop launchers.")
    if any(char in text for char in ' \t\n"\\$' + chr(96)):
        for char in ("\\", '"', "$", chr(96)):
            text = text.replace(char, "\\" + char)
        return '"' + text + '"'
    return text


def render_desktop(template: Path) -> str:
    icon = str(ROOT / "assets/clipdeck.svg")
    if any(ord(char) < 32 for char in icon):
        raise RuntimeError("Install path contains control characters unsupported by desktop launchers.")
    return (template.read_text(encoding="utf-8")
            .replace("@CLIPDECK_RUN@", desktop_argument(ROOT / "run.sh"))
            .replace("@CLIPDECK_ICON@", icon))


def install_desktop(*, autostart: bool) -> Path:
    applications = DATA_HOME / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    target = applications / "io.github.clipdeck.Clipdeck.desktop"
    target.write_text(render_desktop(ROOT / "clipdeck.desktop"), encoding="utf-8")
    target.chmod(0o644)

    fonts = DATA_HOME / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets/fonts/Inter.ttf", fonts / "Clipdeck-Inter.ttf")
    if shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", str(fonts)], check=False)

    if autostart:
        install_autostart()
    return target


def install_autostart() -> None:
    hyprland = CONFIG_HOME / "hypr/hyprland/execs.lua"
    if hyprland.exists():
        content = hyprland.read_text(encoding="utf-8")
        marker = "-- Clipdeck background capture"
        if marker not in content:
            anchor = 'hl.on("hyprland.start", function()\n'
            if anchor in content:
                shutil.copy2(hyprland, hyprland.with_suffix(".lua.clipdeck-backup"))
                command = json.dumps(shlex.quote(str(ROOT / "run.sh")) + " --ensure-capture")
                hyprland.write_text(
                    content.replace(anchor, anchor + f"    {marker}\n    hl.exec_cmd({command})\n", 1),
                    encoding="utf-8",
                )
                print("Added background capture to Hyprland startup.")
                return
            print("Hyprland startup layout is unfamiliar; adding a standard autostart entry instead.")

    autostart_dir = CONFIG_HOME / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    target = autostart_dir / "io.github.clipdeck.Capture.desktop"
    target.write_text(render_desktop(ROOT / "clipdeck-autostart.desktop"), encoding="utf-8")
    target.chmod(0o644)
    print(f"Installed background autostart: {target}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Clipdeck for this user")
    parser.add_argument("--no-deps", action="store_true", help="skip system package installation")
    parser.add_argument("--no-autostart", action="store_true", help="do not start capture at login")
    parser.add_argument("--check", action="store_true", help="only check external tools")
    args = parser.parse_args(argv)
    if os.geteuid() == 0 and not args.check:
        raise RuntimeError("Run ./install.sh as your normal user. It invokes sudo only for system packages.")

    if not args.check and not args.no_deps:
        install_dependencies()

    missing = missing_commands() + missing_gi_modules()
    if missing:
        print("Missing required commands: " + ", ".join(missing), file=sys.stderr)
        print(
            "Install them and rerun ./install.sh. GPU Screen Recorder must include gsr-cli (IPC support).",
            file=sys.stderr,
        )
        if "gpu-screen-recorder" in missing or "gsr-cli" in missing:
            print(
                "If your distribution lacks a compatible package, install GPU Screen "
                "Recorder from its official source "
                "(https://git.dec05eba.com/gpu-screen-recorder/about/) and rerun "
                "./install.sh --no-deps. Clipdeck does not run an unpinned "
                "upstream build script as root.",
                file=sys.stderr,
            )
        return 1
    if args.check:
        print("Required external commands and GTK libraries found.")
        return 0

    target = install_desktop(autostart=not args.no_autostart)
    print(f"Installed launcher: {target}")
    print("Open Clipdeck from your application menu, or run ./run.sh from this checkout.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
