"""Non-blocking confirmation after a replay has actually been saved."""

from __future__ import annotations

import os
import subprocess
import sys

from .config import Settings


def _launch(*arguments: str) -> None:
    environment = os.environ.copy()
    if environment.get("WAYLAND_DISPLAY"):
        environment["GDK_BACKEND"] = "wayland"
    try:
        subprocess.Popen([sys.executable, "-m", "clipdeck.confirmation", *arguments],
                         env=environment, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def clip_saved(settings: Settings) -> None:
    """Confirm a completed replay according to the saved user preferences."""
    if not settings.clip_notifications and settings.clip_sound == "off":
        return
    options = ["--sound", settings.clip_sound, "--theme", settings.theme]
    if not settings.blur_enabled:
        options.append("--no-blur")
    if not settings.clip_notifications:
        options.append("--no-overlay")
    _launch(*options)


def preview_notification(theme: str, blur: bool) -> None:
    """Show the selected appearance without playing a save sound."""
    options = ["--preview", "--theme", theme]
    if not blur:
        options.append("--no-blur")
    _launch(*options)


def preview_sound(sound: str) -> None:
    """Play a pending sound choice without pretending that a clip was saved."""
    if sound != "off":
        _launch("--sound", sound, "--no-overlay")
