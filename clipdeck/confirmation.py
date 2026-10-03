"""Small top-left Wayland overlay for a saved Clipdeck replay."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOUNDS = {
    "chime": ROOT / "assets" / "sounds" / "clip-saved.wav",
    "pulse": ROOT / "assets" / "sounds" / "clip-pulse.wav",
}
ICON = ROOT / "assets" / "icons" / "check.svg"


def _play_sound(choice: str) -> None:
    sound = SOUNDS.get(choice)
    if sound is None:
        return
    if not sound.exists():
        return
    pulse_command = (["paplay", "--volume=36045", str(sound)]
                     if shutil.which("paplay") else None)

    def start(command):
        try:
            return subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return None

    if not shutil.which("pw-play"):
        if pulse_command:
            start(pulse_command)
        return
    process = start(["pw-play", "--volume", "0.55", str(sound)])
    if process is None:
        if pulse_command:
            start(pulse_command)
        return
    if not pulse_command:
        return

    def retry_if_pipewire_failed():
        try:
            result = process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return
        if result != 0:
            start(pulse_command)

    # Both clients may be installed while only PulseAudio is running.
    threading.Thread(target=retry_if_pipewire_failed, daemon=False).start()


def _fallback_notification() -> None:
    if not shutil.which("notify-send"):
        return
    try:
        subprocess.Popen(["notify-send", "-a", "Clipdeck", "-u", "low",
                          "-t", "2600", "-i", str(ROOT / "assets" / "clipdeck.svg"),
                          "Clip saved", "Ready in your Library"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _show_overlay(preview: bool = False, theme: str = "default", blur: bool = True) -> bool:
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import Gdk, GLib, Gtk, GtkLayerShell
    except (ImportError, ValueError):
        return False
    if not Gtk.init_check()[0] or not GtkLayerShell.is_supported():
        return False

    window = Gtk.Window()
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_accept_focus(False)
    window.set_focus_on_map(False)
    window.set_app_paintable(True)
    screen = window.get_screen()
    if screen and screen.get_rgba_visual():
        window.set_visual(screen.get_rgba_visual())
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "clipdeck-clip-saved")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    # Place the toast on the display the player is actually using.
    try:
        pointer_screen, x, y = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()
        monitor_index = pointer_screen.get_monitor_at_point(x, y)
        monitor = Gdk.Display.get_default().get_monitor(monitor_index)
        if monitor is not None:
            GtkLayerShell.set_monitor(window, monitor)
    except (AttributeError, TypeError):
        pass
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, 24)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.LEFT, 24)
    GtkLayerShell.set_exclusive_zone(window, 0)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)

    css = Gtk.CssProvider()
    css.load_from_data(b"""
      window { background: transparent; }
      .clipdeck-confirmation {
        background: rgba(24, 27, 33, .94);
        color: #f6f6f8;
        border: 1px solid rgba(255,255,255,.19);
        border-radius: 17px;
        padding: 12px 17px;
        box-shadow: 0 12px 28px rgba(0,0,0,.34);
      }
      .clipdeck-confirmation.liquid-glass {
        background: linear-gradient(135deg, rgba(126,159,181,.68), rgba(40,61,76,.78) 42%, rgba(16,28,39,.84));
        border: 1px solid rgba(232,246,255,.48);
        box-shadow: inset 0 1px rgba(255,255,255,.30), 0 18px 38px rgba(0,0,0,.37);
      }
      .clipdeck-confirmation.liquid-glass.solid {
        background: linear-gradient(135deg, #526879, #263a49 42%, #172734);
      }
      .clipdeck-confirmation.liquid-glass .confirmation-icon {
        background: rgba(255,255,255,.20);
      }
      .confirmation-title { color: #f7f7f8; font-family: Inter, sans-serif; font-size: 14px; font-weight: 700; }
      .confirmation-detail { color: #adb1ba; font-family: Inter, sans-serif; font-size: 11px; }
      .confirmation-icon { background: rgba(255,255,255,.11); border-radius: 11px; padding: 9px; }
    """)
    Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    card.get_style_context().add_class("clipdeck-confirmation")
    if theme == "liquid_glass":
        card.get_style_context().add_class("liquid-glass")
    if not blur:
        card.get_style_context().add_class("solid")
    image = Gtk.Image.new_from_file(str(ICON))
    image.get_style_context().add_class("confirmation-icon")
    card.pack_start(image, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text.set_valign(Gtk.Align.CENTER)
    title = Gtk.Label(label="Clip saved", xalign=0)
    title.get_style_context().add_class("confirmation-title")
    text.pack_start(title, False, False, 0)
    detail = Gtk.Label(label="Ready in your Library", xalign=0)
    detail.get_style_context().add_class("confirmation-detail")
    text.pack_start(detail, False, False, 0)
    card.pack_start(text, False, False, 0)
    window.add(card)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    GLib.timeout_add(2600, lambda: (window.destroy(), False)[1])
    Gtk.main()
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="show a silent layout preview")
    parser.add_argument("--sound", choices=("chime", "pulse", "off"), default="chime")
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument("--theme", choices=("default", "liquid_glass"), default="default")
    parser.add_argument("--no-blur", action="store_true")
    args = parser.parse_args()
    if not args.preview:
        _play_sound(args.sound)
    if not args.no_overlay and not _show_overlay(args.preview, args.theme, not args.no_blur) and not args.preview:
        _fallback_notification()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
