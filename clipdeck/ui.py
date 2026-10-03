from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import __version__
from .config import Settings
from .feedback import clip_saved, preview_notification, preview_sound
from .audio_filter import FILTER_SOURCE
from .hotkeys import HotkeyError, load_hotkeys, parse_combo, save_hotkeys
from .media import clip_preview, recent_clips, rename_clip, trim_clip
from .microphone import MicrophoneError, test_microphone
from .player import ClipPlayer, HEIGHT, WIDTH, video_duration
from .recorder import Recorder, RecorderError, list_audio_devices, list_monitors


ASSETS = Path(__file__).resolve().parent.parent / "assets"


STYLE = """
* { font-family: Inter, "Noto Sans", sans-serif; }
window { background: rgba(10, 11, 14, .86); color: #f5f5f7; }
window.no-blur { background: #0d0e11; }
window.liquid-glass.blur-enabled { background: rgba(10, 12, 17, .52); }
.shell { background: transparent; }
.sidebar { background: rgba(18, 19, 22, .74); border-right: 1px solid rgba(255,255,255,.08); }
.brand { color: #f8f8fa; font-size: 20px; font-weight: 730; letter-spacing: -1px; }
.brand-glyph { background: #f2f2f4; color: #17181c; border-radius: 11px; font-size: 20px; font-weight: 800; padding: 5px 11px; }
.micro { color: #a0a2a9; font-size: 12px; font-weight: 550; letter-spacing: 0; }
.eyebrow { color: #b7b9c0; font-size: 12px; font-weight: 580; letter-spacing: 0; }
.headline { color: #f6f6f8; font-size: 38px; font-weight: 780; letter-spacing: -1.8px; }
.subtle { color: #9699a1; font-size: 13px; }
.section-title { color: #f1f1f3; font-size: 18px; font-weight: 720; letter-spacing: -.4px; }
.stat-value { color: #f6f6f8; font-size: 22px; font-weight: 740; letter-spacing: -.8px; }
.card { background: linear-gradient(145deg, rgba(255,255,255,.075), rgba(255,255,255,.025)); border: 1px solid rgba(255,255,255,.065); border-radius: 24px; box-shadow: 0 14px 36px rgba(0,0,0,.19); }
.hero { background: linear-gradient(125deg, rgba(58,60,67,.60), rgba(27,29,35,.91) 50%, rgba(18,19,24,.96)); border: 1px solid rgba(255,255,255,.075); border-radius: 27px; box-shadow: 0 20px 56px rgba(0,0,0,.34); }
.hero-title { color: #fff; font-size: 30px; font-weight: 750; letter-spacing: -1.1px; }
.hero-copy { color: #c7c8cc; font-size: 13px; }
.liquid-glass .card { background: linear-gradient(135deg, rgba(255,255,255,.13), rgba(255,255,255,.035)); border-color: rgba(255,255,255,.12); }
.liquid-glass .hero { background: linear-gradient(125deg, rgba(83,91,107,.47), rgba(31,36,49,.57) 55%, rgba(18,23,34,.65)); border-color: rgba(255,255,255,.14); }
.liquid-glass .card, .liquid-glass .hero, .liquid-glass .clip-tile, .liquid-glass .nav-button, .liquid-glass .sidebar-action, .liquid-glass .settings-tab, .liquid-glass .secondary-button { transition: background 180ms ease-out, border-color 180ms ease-out, box-shadow 180ms ease-out; }
.liquid-glass .sidebar { background: linear-gradient(155deg, rgba(89,124,144,.34), rgba(29,49,64,.53) 44%, rgba(13,23,32,.66)); border-right: 1px solid rgba(221,241,255,.23); box-shadow: inset -1px 0 rgba(255,255,255,.10), 10px 0 32px rgba(0,0,0,.12); transition: background 220ms ease-out, border-color 220ms ease-out; }
.liquid-glass .sidebar:hover { background: linear-gradient(155deg, rgba(114,153,175,.40), rgba(36,60,77,.56) 44%, rgba(14,27,38,.66)); border-color: rgba(230,248,255,.31); }
.liquid-glass .nav-button.active { background: linear-gradient(125deg, rgba(229,245,255,.23), rgba(180,214,239,.09)); border-color: rgba(239,249,255,.23); box-shadow: inset 0 1px rgba(255,255,255,.18); }
.liquid-glass .nav-button:hover, .liquid-glass .sidebar-action:hover, .liquid-glass .settings-tab:hover { background: linear-gradient(125deg, rgba(233,247,255,.20), rgba(168,204,230,.08)); border-color: rgba(234,249,255,.24); box-shadow: inset 0 1px rgba(255,255,255,.15), 0 8px 22px rgba(0,0,0,.14); }
.liquid-glass .card:hover, .liquid-glass .hero:hover, .liquid-glass .clip-tile:hover { border-color: rgba(232,247,255,.32); box-shadow: inset 0 1px rgba(255,255,255,.14), 0 20px 46px rgba(0,0,0,.25); }
.liquid-glass .card:hover { background: linear-gradient(145deg, rgba(222,244,255,.18), rgba(127,183,218,.06)); }
.liquid-glass .hero:hover { background: linear-gradient(125deg, rgba(121,161,187,.54), rgba(43,65,84,.64) 55%, rgba(18,31,43,.68)); }
.liquid-glass .secondary-button:hover { background: linear-gradient(120deg, rgba(245,251,255,.24), rgba(149,196,227,.10)); border-color: rgba(240,251,255,.33); box-shadow: inset 0 1px rgba(255,255,255,.20), 0 7px 18px rgba(0,0,0,.13); }
.no-blur .card, .no-blur .hero, .no-blur .sidebar { background-color: #1b1c21; }
.nav-button { background: transparent; color: #a1a3aa; border: 1px solid transparent; border-radius: 17px; padding: 13px 17px; box-shadow: none; font-weight: 620; }
.nav-button:hover { background: rgba(255,255,255,.06); color: #fff; }
.nav-button.active { background: rgba(255,255,255,.11); color: #fff; border: 1px solid rgba(255,255,255,.04); }
.nav-icon { opacity: .86; }
.primary-button { background: #f4f4f5; color: #17181b; border: 1px solid #fff; border-radius: 16px; padding: 12px 20px; font-weight: 750; box-shadow: 0 8px 24px rgba(0,0,0,.2); }
.primary-button:hover { background: #fff; }
.secondary-button { background: rgba(255,255,255,.07); color: #f5f5f6; border: 1px solid rgba(255,255,255,.16); border-radius: 16px; padding: 12px 20px; font-weight: 650; box-shadow: none; }
.secondary-button:hover { background: rgba(255,255,255,.13); }
.status-pill { background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14); border-radius: 999px; padding: 9px 14px; color: #b6b7bc; font-size: 11px; font-weight: 760; letter-spacing: .7px; }
.status-pill.live { background: rgba(255,255,255,.15); color: #fff; }
.field { background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.13); border-radius: 15px; color: #f5f5f6; padding: 10px 13px; }
.field:focus { border-color: rgba(255,255,255,.55); }
.file-card { background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.055); border-radius: 18px; padding: 16px; }
.clip-tile { background: #1a1c22; color: #f3f3f5; border: 1px solid rgba(255,255,255,.055); border-radius: 18px; padding: 0; box-shadow: none; }
.clip-tile:hover { background: #22252d; border-color: rgba(255,255,255,.16); }
.clip-main { background: transparent; border: none; border-radius: 18px 18px 0 0; padding: 0; box-shadow: none; color: inherit; }
.clip-main:hover { background: transparent; box-shadow: none; }
.clip-action { background: rgba(255,255,255,.055); border: 1px solid transparent; border-radius: 999px; padding: 6px; min-width: 28px; min-height: 28px; box-shadow: none; }
.clip-action:hover { background: rgba(255,255,255,.15); border-color: rgba(255,255,255,.08); }
.clip-action.danger:hover { background: rgba(241,139,139,.16); }
.clip-thumb { background: #262a33; border-radius: 17px 17px 0 0; }
.clip-duration { background: rgba(7,9,13,.78); color: #f7f7f8; border-radius: 7px; padding: 3px 7px; font-size: 11px; font-weight: 700; }
.clip-title { color: #f4f4f6; font-size: 13px; font-weight: 700; }
.clip-meta { color: #979aa4; font-size: 11px; }
.preview-surface { background: #08090c; border-radius: 14px; }
.preview-frame { background: #090a0d; border: 1px solid rgba(255,255,255,.06); border-radius: 18px; }
.preview-fullscreen .preview-frame { background: #000; border: none; border-radius: 0; }
.speed-choice { background: rgba(255,255,255,.045); color: #e8e9eb; border: 1px solid transparent; border-radius: 11px; padding: 9px 12px; box-shadow: none; }
.speed-choice:hover, .speed-choice.active { background: rgba(255,255,255,.13); border-color: rgba(255,255,255,.09); }
.danger-button { background: transparent; color: #f18b8b; border: none; border-radius: 11px; padding: 10px; box-shadow: none; }
.danger-button:hover { background: rgba(241,139,139,.11); }
.settings-tabs { background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.07); border-radius: 18px; padding: 5px; }
.settings-tab { background: transparent; color: #a6a8b0; border: none; border-radius: 13px; padding: 10px 15px; box-shadow: none; font-weight: 650; }
.settings-tab:hover { background: rgba(255,255,255,.07); color: #fff; }
.settings-tab.active { background: rgba(255,255,255,.14); color: #fff; }
.settings-section-title { color: #f4f4f6; font-size: 19px; font-weight: 740; letter-spacing: -.4px; }
.about-name { color: #f4f4f6; font-size: 21px; font-weight: 750; letter-spacing: -.5px; }
.about-copy { color: #c5c8cf; font-size: 14px; line-height: 1.45; }
.settings-row { padding: 7px 0; }
.settings-row-title { color: #f0f0f3; font-size: 15px; font-weight: 750; }
.settings-row-detail { color: #a2a5ae; font-size: 12px; }
.shortcut-name { background: rgba(255,255,255,.055); color: #f0f0f3; border: 1px solid rgba(255,255,255,.12); border-radius: 14px; padding: 11px 16px; font-size: 15px; font-weight: 720; }
.settings-save-bar { background: rgba(28,30,36,.78); border: 1px solid rgba(255,255,255,.15); border-radius: 18px; padding: 11px 13px 11px 20px; box-shadow: 0 16px 40px rgba(0,0,0,.35); }
.settings-save-title { color: #f0f0f3; font-size: 14px; font-weight: 650; }
.settings-discard { background: transparent; border: none; box-shadow: none; color: #aeb5d7; font-weight: 650; padding: 9px 13px; border-radius: 11px; }
.settings-discard:hover { background: rgba(255,255,255,.08); color: #fff; }
.settings-commit { background: #167a58; border: 1px solid rgba(255,255,255,.12); color: #fff; border-radius: 12px; padding: 10px 15px; font-weight: 720; box-shadow: none; }
.settings-commit:hover { background: #209569; }
.mic-test-controls { background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.09); border-radius: 16px; padding: 6px; }
.mic-meter-shell { background: rgba(0,0,0,.17); border-radius: 12px; padding: 8px 10px; }
.mic-meter-label { color: #a6a9b1; font-size: 11px; font-weight: 650; }
.sidebar-action { background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.085); box-shadow: none; border-radius: 13px; color: #c4c6ce; font-size: 15px; font-weight: 680; padding: 10px 8px; }
.sidebar-action:hover { background: rgba(255,255,255,.08); color: #fff; }
.sidebar-action.quit:hover { color: #f18b8b; }
.recent-arrow { background: rgba(25,28,34,.92); color: #fff; border: 1px solid rgba(255,255,255,.2); min-width: 38px; min-height: 38px; padding: 5px; border-radius: 999px; box-shadow: 0 5px 18px rgba(0,0,0,.3); }
.recent-arrow:hover { background: rgba(55,62,72,.96); }
.recent-arrow:disabled { opacity: .42; }
.unit-field { padding-right: 62px; }
.unit-suffix { color: #a6adb7; font-size: 12px; font-weight: 700; }
.clip-tool { background: rgba(255,255,255,.065); color: #f1f2f4; border: 1px solid rgba(255,255,255,.13); border-radius: 11px; padding: 5px 9px; font-size: 13px; font-weight: 680; box-shadow: none; }
.clip-tool:hover { background: rgba(255,255,255,.12); }
.trim-timeline { background: rgba(255,255,255,.035); border-radius: 14px; }
.quit-scrim { background: rgba(3,5,8,0); transition: background 200ms ease-out; }
.quit-scrim.visible { background: rgba(3,5,8,.68); }
.quit-card { background: #20242b; border: 1px solid rgba(255,255,255,.17); border-radius: 22px; padding: 24px; box-shadow: 0 24px 70px rgba(0,0,0,.5); }
.quit-card .danger-button { background: rgba(190,68,75,.2); border: 1px solid rgba(239,119,124,.3); }
.quit-card .danger-button:hover { background: rgba(190,68,75,.33); }
.trim-scrim { background: rgba(3,5,8,.78); }
.trim-dialog { background: #26272b; border: 1px solid rgba(255,255,255,.19); border-radius: 21px; padding: 17px; box-shadow: 0 26px 80px rgba(0,0,0,.55); }
.liquid-glass .trim-dialog { background: linear-gradient(135deg, #344652, #202b34 58%, #1b252e); border-color: rgba(230,246,255,.3); }
.trim-video { background: #07090b; border-radius: 12px; }
.trim-marker { color: #d3d8dd; font-size: 12px; font-weight: 670; }
.liquid-glass .quit-card { background: linear-gradient(135deg, #354958, #1b2934); border-color: rgba(229,246,255,.3); }
.notification-preview { background: rgba(24,27,33,.94); border: 1px solid rgba(255,255,255,.19); border-radius: 17px; padding: 12px 17px; box-shadow: 0 12px 28px rgba(0,0,0,.22); }
.notification-preview-icon { background: rgba(255,255,255,.11); border-radius: 11px; padding: 9px; }
.notification-preview-title { color: #f7f7f8; font-size: 14px; font-weight: 700; }
.notification-preview-detail { color: #adb1ba; font-size: 11px; }
.liquid-glass .notification-preview { background: linear-gradient(135deg, rgba(126,159,181,.68), rgba(40,61,76,.78) 42%, rgba(16,28,39,.84)); border-color: rgba(232,246,255,.48); box-shadow: inset 0 1px rgba(255,255,255,.30), 0 18px 38px rgba(0,0,0,.24); }
.liquid-glass.no-blur .notification-preview { background: linear-gradient(135deg, #526879, #263a49 42%, #172734); }
.liquid-glass .notification-preview-icon { background: rgba(255,255,255,.20); }
.meter-area { background: transparent; }
.toast-label { color: #d4d5da; font-size: 12px; }
dropdown button { background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.13); border-radius: 15px; padding: 9px 13px; color: #f5f5f6; }
switch { background: #35363a; border-radius: 999px; }
switch:checked { background: #727b86; }
switch slider { background: #fff; }
"""


def label(text: str, css: str | None = None, xalign: float = 0) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=xalign)
    widget.set_wrap(True)
    if css:
        widget.add_css_class(css)
    return widget


def box(orientation=Gtk.Orientation.VERTICAL, spacing=0) -> Gtk.Box:
    return Gtk.Box(orientation=orientation, spacing=spacing)


def button(text: str, css: str, callback) -> Gtk.Button:
    widget = Gtk.Button(label=text)
    widget.add_css_class(css)
    widget.connect("clicked", callback)
    return widget


def icon(name: str, size: int = 20) -> Gtk.Image:
    widget = Gtk.Image.new_from_file(str(ASSETS / "icons" / f"{name}.svg"))
    widget.set_pixel_size(size)
    return widget


def nav_button(name: str, title: str, callback) -> Gtk.Button:
    widget = Gtk.Button()
    widget.add_css_class("nav-button")
    row = box(Gtk.Orientation.HORIZONTAL, 13)
    image = icon(name, 19)
    image.add_css_class("nav-icon")
    row.append(image)
    row.append(label(title))
    widget.set_child(row)
    widget.connect("clicked", callback)
    return widget


def padded_card(content: Gtk.Widget, css="card") -> Gtk.Box:
    card = box()
    card.add_css_class(css)
    content.set_margin_top(24)
    content.set_margin_bottom(24)
    content.set_margin_start(25)
    content.set_margin_end(25)
    card.append(content)
    return card


class MicrophoneMeter(Gtk.Picture):
    def __init__(self):
        super().__init__()
        self.level = 0.0
        self.display_level = 0.0
        self.set_hexpand(False)
        self.set_size_request(174, 30)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_content_fit(Gtk.ContentFit.FILL)
        self.set_can_shrink(True)
        self._render()
        GLib.timeout_add(33, self._animate)

    def set_level(self, value: float):
        self.level = max(0.0, min(1.0, value))

    def _animate(self):
        self.display_level += (self.level - self.display_level) * 0.24
        if abs(self.display_level - self.level) > .002 or self.display_level > .002:
            self._render()
        return True

    def _render(self):
        width, height, bars = 174, 30, 22
        pixels = bytearray(width * height * 4)
        active = round(self.display_level * bars)
        for index in range(bars):
            if index < active:
                amount = index / max(1, bars - 1)
                color = (int(250 - 165 * amount), int(184 + 30 * amount),
                         int(43 + 64 * amount), 255)
            else:
                color = (76, 81, 91, 255)
            left = index * 8 + 1
            for y in range(5, 25):
                for x in range(left, left + 4):
                    if (y in (5, 24)) and (x == left or x == left + 3):
                        continue
                    offset = (y * width + x) * 4
                    pixels[offset:offset + 4] = bytes(color)
        texture = Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.R8G8B8A8,
                                        GLib.Bytes.new(bytes(pixels)), width * 4)
        self.set_paintable(texture)


class TrimTimeline(Gtk.Picture):
    def __init__(self, changed, released=None):
        super().__init__()
        self.duration = 1.0
        self.start = 0.0
        self.end = 1.0
        self.changed = changed
        self.released = released
        self.dragged_handle = "start"
        self.drag_origin = 0.0
        self.set_size_request(250, 58)
        self.set_hexpand(True)
        self.set_can_shrink(True)
        self.set_content_fit(Gtk.ContentFit.FILL)
        self.add_css_class("trim-timeline")
        drag = Gtk.GestureDrag()
        drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.add_controller(drag)
        self._render()

    def set_range(self, duration: float, start: float = 0.0, end: float | None = None):
        self.duration = max(.1, duration)
        self.start = max(0.0, min(start, self.duration))
        self.end = max(self.start + .1, min(self.duration, end if end is not None else self.duration))
        self._render()
        self.changed(self.start, self.end)

    def _position(self, seconds: float, width: int) -> float:
        return 18 + (width - 36) * seconds / self.duration

    def _seconds(self, x: float, width: int) -> float:
        return max(0.0, min(self.duration, (x - 18) / max(1, width - 36) * self.duration))

    def _render(self):
        width, height = 700, 58
        pixels = bytearray(bytes((42, 47, 52, 255)) * (width * height))
        left = round(self._position(self.start, width))
        right = round(self._position(self.end, width))
        def rect(x1, y1, x2, y2, color):
            x1, x2 = max(0, x1), min(width, x2)
            for y in range(max(0, y1), min(height, y2)):
                offset = (y * width + x1) * 4
                pixels[offset:offset + (x2 - x1) * 4] = bytes(color) * (x2 - x1)
        rect(18, 23, width - 18, 35, (83, 88, 94, 255))
        rect(left, 23, right, 35, (225, 164, 136, 255))
        for x in (left, right):
            rect(x - 5, 15, x + 5, 43, (255, 208, 184, 255))
            rect(x - 1, 20, x + 1, 38, (138, 87, 68, 255))
        self.set_paintable(Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.R8G8B8A8,
                                                 GLib.Bytes.new(bytes(pixels)), width * 4))

    def _drag_begin(self, _gesture, x, _y):
        width = self.get_allocated_width()
        left = self._position(self.start, width)
        right = self._position(self.end, width)
        self.dragged_handle = "start" if abs(x - left) <= abs(x - right) else "end"
        self.drag_origin = x
        self._move_handle(x)

    def _drag_update(self, _gesture, dx, _dy):
        self._move_handle(self.drag_origin + dx)

    def _drag_end(self, _gesture, _dx, _dy):
        if self.released:
            self.released(self.start if self.dragged_handle == "start" else self.end)

    def _move_handle(self, x):
        value = self._seconds(x, self.get_allocated_width())
        if self.dragged_handle == "start":
            self.start = min(value, self.end - .1)
        else:
            self.end = max(value, self.start + .1)
        self._render()
        self.changed(self.start, self.end)


class ClipdeckApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.clipdeck.Clipdeck", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.settings = Settings.load()
        self.hotkeys = load_hotkeys()
        self.pending_hotkeys = dict(self.hotkeys)
        self.pending_bind = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.media_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.preview_jobs = {}
        self.player = None
        self.trim_player = None
        self.preview_origin = "library"
        self.preview_fullscreen = False
        self.preview_duration = 0.0
        self.seek_source = 0
        self.seek_dragging = False
        self.seek_pending = False
        self.seek_waiting_frame = False
        self.seek_resume = False
        self.seek_target = 0.0
        self._recent_tick = 0
        self._trim_previewing = False
        self.trim_saving = False
        self.mic_test_future = None
        self.mic_stop = threading.Event()
        self.busy = False
        self.saving_clip = False
        self.replay = False
        self.record = False
        self.next_start_attempt = 0.0
        self.window = None
        self.tray_process = None
        self._held_open = False
        self._quitting = False
        self.responsive_rows = []
        for action_name, handler in (("show", self.show_window),
                                     ("library", self.show_library),
                                     ("quit", self.confirm_quit)):
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", handler)
            self.add_action(action)
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self._on_shutdown)

    def _on_shutdown(self, *_):
        if self.player:
            self.player.stop()
        if self.trim_player:
            self.trim_player.stop()
        self.mic_stop.set()
        if self.tray_process and self.tray_process.poll() is None:
            self.tray_process.terminate()

    def _window_key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape and getattr(self, "trim_overlay", None) and self.trim_overlay.get_visible():
            self._close_trim_overlay()
            return True
        if keyval == Gdk.KEY_Escape and getattr(self, "quit_overlay", None) and self.quit_overlay.get_visible():
            if not self._quitting:
                self._dismiss_quit()
            return True
        if self.pending_bind:
            return self._on_bind_key(_controller, keyval, _keycode, _state)
        if (keyval == Gdk.KEY_Escape and self.preview_fullscreen):
            self.toggle_preview_fullscreen()
            return True
        if (keyval == Gdk.KEY_space and self.stack.get_visible_child_name() == "preview"
                and not self.preview_menu.get_active()):
            self.toggle_preview()
            return True
        return False

    def on_activate(self, *_):
        if self.window:
            self.window.unminimize()
            self.window.present()
            return
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Adw.ApplicationWindow(application=self, title="Clipdeck", default_width=1160, default_height=760)
        self.window.set_size_request(480, 480)
        self.window.connect("close-request", self._window_close_requested)
        keyboard = Gtk.EventControllerKey()
        keyboard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keyboard.connect("key-pressed", self._window_key_pressed)
        self.window.add_controller(keyboard)
        self._apply_appearance(self.settings.theme, self.settings.blur_enabled)
        outer = box()
        root = box(Gtk.Orientation.HORIZONTAL)
        root.add_css_class("shell")
        root.set_vexpand(True)
        outer.append(root)
        self.sidebar = self._sidebar()
        root.append(self.sidebar)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(180)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.stack.set_interpolate_size(False)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        root.append(self.stack)
        self.stack.add_named(self._dashboard(), "dashboard")
        self.stack.add_named(self._library(), "library")
        self.stack.add_named(self._preview_page(), "preview")
        self.stack.add_named(self._settings_page(), "settings")
        self.compact_nav = self._compact_navigation()
        self.compact_nav.set_visible(False)
        outer.append(self.compact_nav)
        overlay = Gtk.Overlay()
        overlay.set_child(outer)
        self._build_quit_overlay(overlay)
        self._build_trim_overlay(overlay)
        responsive = Adw.BreakpointBin()
        responsive.set_child(overlay)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 1060px"))
        narrow.add_setter(self.sidebar, "visible", False)
        narrow.add_setter(self.compact_nav, "visible", True)
        for row in self.responsive_rows:
            narrow.add_setter(row, "orientation", Gtk.Orientation.VERTICAL)
        narrow.add_setter(self.settings_save_bar, "orientation", Gtk.Orientation.VERTICAL)
        narrow.add_setter(self.settings_content, "margin-bottom", 210)
        narrow.add_setter(self.dashboard_content, "margin-start", 18)
        narrow.add_setter(self.dashboard_content, "margin-end", 18)
        responsive.add_breakpoint(narrow)
        self.window.set_content(responsive)
        self.navigate("dashboard")
        self.window.present()
        if not self._held_open:
            self.hold()
            self._held_open = True
        self._start_tray()
        self._load_devices()
        self.ensure_capture()
        GLib.timeout_add_seconds(4, self._periodic_refresh)

    def _sidebar(self):
        sidebar = box(spacing=12)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(260, -1)
        sidebar.set_hexpand(False)
        body = box(spacing=12)
        body.set_vexpand(True)
        body.set_hexpand(False)
        body.set_margin_top(35)
        body.set_margin_bottom(28)
        body.set_margin_start(16)
        body.set_margin_end(16)
        sidebar.append(body)
        brandrow = box(Gtk.Orientation.HORIZONTAL, 11)
        mark = label("c", "brand-glyph", .5)
        brandrow.append(mark)
        brandrow.append(label("clipdeck.", "brand"))
        body.append(brandrow)
        gap = box()
        gap.set_size_request(-1, 35)
        body.append(gap)
        self.nav = {}
        for key, title, image in (("dashboard", "Home", "layout-dashboard"),
                                  ("library", "Library", "library"),
                                  ("settings", "Settings", "settings-2")):
            item = nav_button(image, title, lambda _, page=key: self.navigate(page))
            body.append(item)
            self.nav[key] = item
        spacer = box()
        spacer.set_vexpand(True)
        body.append(spacer)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(5)
        separator.set_margin_bottom(5)
        body.append(separator)
        footer = box(Gtk.Orientation.HORIZONTAL, 8)
        for name, title, callback in (("minus", "Minimize", self.minimize_window),
                                      ("power", "Quit", self.confirm_quit)):
            action = Gtk.Button()
            action.add_css_class("sidebar-action")
            action.set_hexpand(True)
            if name == "power":
                action.add_css_class("quit")
            inner = box(Gtk.Orientation.HORIZONTAL, 6)
            inner.set_halign(Gtk.Align.CENTER)
            inner.append(icon(name, 16))
            inner.append(label(title))
            action.set_child(inner)
            action.connect("clicked", callback)
            footer.append(action)
        body.append(footer)
        return sidebar

    def _compact_navigation(self):
        bar = box(spacing=5)
        bar.add_css_class("sidebar")
        bar.set_margin_top(3)
        links = box(Gtk.Orientation.HORIZONTAL, 5)
        for key, title in (("dashboard", "Home"), ("library", "Library"), ("settings", "Settings")):
            action = button(title, "sidebar-action", lambda _, page=key: self.navigate(page))
            action.set_hexpand(True)
            links.append(action)
        bar.append(links)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        tools = box(Gtk.Orientation.HORIZONTAL, 5)
        for action in (button("Minimize", "sidebar-action", self.minimize_window),
                       button("Quit", "sidebar-action", self.confirm_quit)):
            action.set_hexpand(True)
            tools.append(action)
        bar.append(tools)
        return bar

    def _build_quit_overlay(self, overlay):
        scrim = Gtk.Overlay()
        scrim.add_css_class("quit-scrim")
        scrim.set_halign(Gtk.Align.FILL)
        scrim.set_valign(Gtk.Align.FILL)
        scrim.set_child(box())
        card = box(spacing=16)
        card.add_css_class("quit-card")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(330, -1)
        card.append(label("Quit Clipdeck?", "section-title"))
        self.quit_message = label("Background capture will stop. Any full recording will be saved.", "subtle")
        card.append(self.quit_message)
        actions = box(Gtk.Orientation.HORIZONTAL, 10)
        self.quit_cancel_button = button("Cancel", "secondary-button", self._dismiss_quit)
        self.quit_cancel_button.set_hexpand(True)
        self.quit_confirm_button = button("Quit", "danger-button", self._quit_clipdeck)
        self.quit_confirm_button.set_hexpand(True)
        self.quit_force_button = button("Exit anyway", "danger-button", self._finish_quit)
        self.quit_force_button.set_visible(False)
        actions.append(self.quit_cancel_button)
        actions.append(self.quit_confirm_button)
        card.append(actions)
        card.append(self.quit_force_button)
        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        revealer.set_transition_duration(200)
        revealer.set_halign(Gtk.Align.CENTER)
        revealer.set_valign(Gtk.Align.CENTER)
        revealer.set_child(card)
        revealer.set_reveal_child(False)
        scrim.add_overlay(revealer)
        overlay.add_overlay(scrim)
        scrim.set_visible(False)
        self.quit_overlay = scrim
        self.quit_revealer = revealer

    def _build_trim_overlay(self, overlay):
        scrim = Gtk.Overlay()
        scrim.add_css_class("trim-scrim")
        scrim.set_halign(Gtk.Align.FILL)
        scrim.set_valign(Gtk.Align.FILL)
        viewport = Gtk.ScrolledWindow()
        viewport.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        centered = box()
        centered.set_margin_start(16)
        centered.set_margin_end(16)
        centered.set_margin_top(14)
        centered.set_margin_bottom(14)
        before = box()
        before.set_vexpand(True)
        centered.append(before)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(720)
        card = box(spacing=11)
        card.add_css_class("trim-dialog")
        clamp.set_child(card)
        centered.append(clamp)
        after = box()
        after.set_vexpand(True)
        centered.append(after)
        viewport.set_child(centered)
        scrim.set_child(viewport)

        heading = box(Gtk.Orientation.HORIZONTAL, 8)
        self.trim_title = label("Trim clip", "section-title")
        self.trim_title.set_hexpand(True)
        self.trim_title.set_wrap(False)
        self.trim_title.set_ellipsize(Pango.EllipsizeMode.END)
        heading.append(self.trim_title)
        heading.append(button("×", "clip-tool", self._close_trim_overlay))
        card.append(heading)
        frame = Gtk.AspectFrame.new(.5, .5, 16 / 9, False)
        frame.add_css_class("trim-video")
        frame.set_size_request(1, 210)
        self.trim_picture = Gtk.Picture()
        self.trim_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.trim_picture.set_can_shrink(True)
        frame.set_child(self.trim_picture)
        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_: self._toggle_trim_playback())
        frame.add_controller(click)
        card.append(frame)
        playback = box(Gtk.Orientation.HORIZONTAL, 8)
        self.trim_play_button = button("Play", "clip-tool", self._toggle_trim_playback)
        playback.append(self.trim_play_button)
        self.trim_seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, .1)
        self.trim_seek.set_draw_value(False)
        self.trim_seek.set_hexpand(True)
        self.trim_seek_handler = self.trim_seek.connect("value-changed", self._trim_seek_changed)
        playback.append(self.trim_seek)
        self.trim_time = label("0:00 / 0:00", "trim-marker")
        playback.append(self.trim_time)
        card.append(playback)
        card.append(label("Drag the peach handles, or move the playhead and use Set in / Set out.", "subtle"))
        self.trim_timeline = TrimTimeline(self._trim_range_changed, self._trim_handle_released)
        card.append(self.trim_timeline)
        markers = box(Gtk.Orientation.HORIZONTAL, 8)
        self.trim_start_label = label("In 0:00.0", "trim-marker")
        self.trim_start_label.set_hexpand(True)
        self.trim_length_label = label("Selected 0:00.0", "trim-marker")
        self.trim_length_label.set_hexpand(True)
        self.trim_length_label.set_halign(Gtk.Align.CENTER)
        self.trim_end_label = label("Out 0:00.0", "trim-marker")
        markers.append(self.trim_start_label)
        markers.append(self.trim_length_label)
        markers.append(self.trim_end_label)
        card.append(markers)
        marker_actions = box(Gtk.Orientation.HORIZONTAL, 8)
        marker_actions.append(button("Set in at playhead", "clip-tool", self._set_trim_in))
        marker_actions.append(button("Set out at playhead", "clip-tool", self._set_trim_out))
        card.append(marker_actions)
        self.trim_notice = label("", "toast-label")
        card.append(self.trim_notice)
        footer = box(Gtk.Orientation.HORIZONTAL, 8)
        footer.append(button("Preview", "clip-tool", self._preview_trim_selection))
        spacer = box()
        spacer.set_hexpand(True)
        footer.append(spacer)
        footer.append(button("Cancel", "clip-tool", self._close_trim_overlay))
        self.trim_save_button = button("Save trim", "primary-button", self._save_trimmed_clip)
        footer.append(self.trim_save_button)
        card.append(footer)
        overlay.add_overlay(scrim)
        scrim.set_visible(False)
        self.trim_overlay = scrim
        self.trim_player = None
        self.trim_seek_source = 0

    def _window_close_requested(self, *_):
        self.window.set_visible(False)
        return True

    def minimize_window(self, *_):
        if self.window:
            self.window.set_visible(False)

    def show_window(self, *_):
        self.activate()

    def show_library(self, *_):
        self.activate()
        self.navigate("library")

    def confirm_quit(self, *_):
        self.show_window()
        if self.trim_saving:
            self.trim_notice.set_text("Wait for the trimmed clip to finish saving.")
            return
        if self.trim_overlay.get_visible():
            self._close_trim_overlay(resume=False)
        self.quit_message.set_text("Background capture will stop. Any full recording will be saved.")
        self.quit_confirm_button.set_sensitive(True)
        self.quit_cancel_button.set_sensitive(True)
        self.quit_force_button.set_visible(False)
        self.quit_overlay.set_visible(True)
        def reveal():
            self.quit_overlay.add_css_class("visible")
            self.quit_revealer.set_reveal_child(True)
            return False
        GLib.idle_add(reveal)

    def _dismiss_quit(self, *_):
        if self._quitting:
            return
        self.quit_revealer.set_reveal_child(False)
        self.quit_overlay.remove_css_class("visible")
        def hide():
            if not self.quit_revealer.get_reveal_child():
                self.quit_overlay.set_visible(False)
            return False
        GLib.timeout_add(210, hide)

    def _quit_clipdeck(self, *_):
        if self._quitting:
            return
        self._quitting = True
        self.quit_confirm_button.set_sensitive(False)
        self.quit_cancel_button.set_sensitive(False)
        self.quit_message.set_text("Stopping capture…")
        future = self.executor.submit(lambda: Recorder(self.settings).stop())
        def done(completed):
            def finish():
                try:
                    completed.result()
                except (RecorderError, OSError) as exc:
                    self._quitting = False
                    GLib.timeout_add_seconds(4, self._periodic_refresh)
                    self.quit_confirm_button.set_sensitive(True)
                    self.quit_cancel_button.set_sensitive(True)
                    self.quit_force_button.set_visible(True)
                    self.quit_message.set_text("Could not stop capture: " + str(exc) + ". Exiting anyway may leave capture running.")
                    return False
                self._finish_quit()
                return False
            GLib.idle_add(finish)
        future.add_done_callback(done)

    def _finish_quit(self, *_):
        if self._held_open:
            self.release()
            self._held_open = False
        if self.window:
            self.window.destroy()
            self.window = None
        self.quit()

    def _start_tray(self):
        if self.tray_process and self.tray_process.poll() is None:
            return
        try:
            self.tray_process = subprocess.Popen(
                [sys.executable, "-m", "clipdeck.tray", str(os.getpid()),
                 self.get_application_id()],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
        except OSError:
            self.tray_process = None

    def _page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_width(False)
        scroll.set_propagate_natural_height(False)
        content = box(spacing=22)
        content.set_margin_top(38)
        content.set_margin_bottom(46)
        content.set_margin_start(42)
        content.set_margin_end(42)
        scroll.set_child(content)
        return scroll, content

    def _dashboard(self):
        scroll, content = self._page()
        self.dashboard_content = content
        content.append(label("Home", "headline"))

        recent_heading = box(Gtk.Orientation.HORIZONTAL, 12)
        self.recent_title = label("Recent clips", "section-title")
        self.recent_title.set_hexpand(True)
        recent_heading.append(self.recent_title)
        self.recent_page_label = label("", "subtle")
        self.recent_page_label.set_wrap(False)
        recent_heading.append(self.recent_page_label)
        recent_heading.append(button("See all  →", "secondary-button",
                                     lambda *_: self.navigate("library")))
        content.append(recent_heading)
        self.recent_scroll = Gtk.ScrolledWindow()
        self.recent_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.recent_scroll.set_propagate_natural_width(False)
        self.recent_scroll.set_min_content_width(1)
        self.recent_scroll.set_hexpand(True)
        self.recent_list = box(Gtk.Orientation.HORIZONTAL, 13)
        self.recent_scroll.set_child(self.recent_list)
        recent_carousel = Gtk.Overlay()
        recent_carousel.set_hexpand(True)
        recent_carousel.set_child(self.recent_scroll)
        self.recent_back = button("‹", "recent-arrow", lambda *_: self._move_recent(-1))
        self.recent_back.set_halign(Gtk.Align.START)
        self.recent_back.set_valign(Gtk.Align.CENTER)
        self.recent_back.set_margin_start(6)
        recent_carousel.add_overlay(self.recent_back)
        self.recent_next = button("›", "recent-arrow", lambda *_: self._move_recent(1))
        self.recent_next.set_halign(Gtk.Align.END)
        self.recent_next.set_valign(Gtk.Align.CENTER)
        self.recent_next.set_margin_end(6)
        recent_carousel.add_overlay(self.recent_next)
        content.append(recent_carousel)
        self.recent_scroll.get_hadjustment().connect("value-changed", self._update_recent_arrows)
        self.recent_scroll.get_hadjustment().connect("changed", self._update_recent_arrows)
        self.notice = label("", "toast-label")
        content.append(self.notice)
        return scroll

    def _library(self):
        scroll, content = self._page()
        content.append(label("Library", "headline"))
        self.library_search = Gtk.SearchEntry()
        self.library_search.add_css_class("field")
        self.library_search.set_placeholder_text("Search clips by name")
        self.library_search.connect("search-changed", lambda *_: self.populate_library())
        content.append(self.library_search)
        actions = box(Gtk.Orientation.HORIZONTAL, 10)
        actions.append(button("Refresh", "secondary-button", lambda *_: self.populate_library()))
        actions.append(button("Open folder", "secondary-button", lambda *_: self.open_path(self.settings.clips_dir)))
        content.append(actions)
        self.library_heading = label("Recent clips", "section-title")
        content.append(self.library_heading)
        self.library_list = Gtk.FlowBox()
        self.library_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.library_list.set_homogeneous(True)
        self.library_list.set_min_children_per_line(1)
        self.library_list.set_max_children_per_line(4)
        self.library_list.set_column_spacing(14)
        self.library_list.set_row_spacing(14)
        content.append(self.library_list)
        return scroll

    def _preview_page(self):
        scroll, content = self._page()
        self.preview_scroll = scroll
        self.preview_content = content
        back = button("←  Back to clips", "secondary-button",
                      lambda *_: self.navigate(self.preview_origin))
        back.set_halign(Gtk.Align.START)
        content.append(back)
        self.preview_back_button = back
        self.preview_title = label("", "headline")
        self.preview_title.set_wrap(False)
        self.preview_title.set_ellipsize(Pango.EllipsizeMode.END)
        content.append(self.preview_title)
        self.preview_picture = Gtk.Picture()
        self.preview_picture.set_can_shrink(True)
        self.preview_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview_picture.set_size_request(1, 220)
        self.preview_picture.set_hexpand(True)
        self.preview_picture.set_vexpand(True)
        self.preview_picture.add_css_class("preview-frame")
        frame = Gtk.Overlay()
        frame.set_vexpand(True)
        frame.set_child(self.preview_picture)
        click = Gtk.GestureClick()
        click.set_button(1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", lambda *_: self.toggle_preview())
        frame.add_controller(click)
        self.preview_placeholder = label("Preparing preview…", "subtle", .5)
        self.preview_placeholder.set_halign(Gtk.Align.CENTER)
        self.preview_placeholder.set_valign(Gtk.Align.CENTER)
        frame.add_overlay(self.preview_placeholder)
        content.append(frame)
        self.preview_frame = frame
        controls = box(Gtk.Orientation.HORIZONTAL, 12)
        self.preview_play_button = button("Pause", "secondary-button", self.toggle_preview)
        controls.append(self.preview_play_button)
        self.preview_seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, .1)
        self.preview_seek.set_draw_value(False)
        self.preview_seek.set_hexpand(True)
        self.preview_seek_handler = self.preview_seek.connect("value-changed", self._seek_changed)
        controls.append(self.preview_seek)
        self.preview_time = label("0:00 / 0:00", "subtle")
        self.preview_time.set_wrap(False)
        controls.append(self.preview_time)
        self.preview_fullscreen_button = Gtk.Button()
        self.preview_fullscreen_button.add_css_class("secondary-button")
        self.preview_fullscreen_button.set_child(icon("maximize", 18))
        self.preview_fullscreen_button.set_tooltip_text("Enter fullscreen")
        self.preview_fullscreen_button.connect("clicked", self.toggle_preview_fullscreen)
        controls.append(self.preview_fullscreen_button)
        content.append(controls)
        actions = box(spacing=9)
        tools = box(Gtk.Orientation.HORIZONTAL, 6)
        tools.set_halign(Gtk.Align.END)
        self.preview_meta = label("", "subtle")
        self.preview_meta.set_wrap(False)
        self.preview_meta.set_ellipsize(Pango.EllipsizeMode.END)
        self.preview_meta.set_valign(Gtk.Align.CENTER)
        self.preview_meta.set_hexpand(True)
        actions.append(self.preview_meta)
        menu = Gtk.MenuButton()
        menu.add_css_class("clip-tool")
        menu.set_child(icon("menu", 17))
        menu.set_size_request(38, 34)
        menu.set_tooltip_text("Clip options")
        popover = Gtk.Popover()
        popover_content = box(spacing=12)
        popover_content.set_margin_top(15)
        popover_content.set_margin_bottom(15)
        popover_content.set_margin_start(15)
        popover_content.set_margin_end(15)
        popover_content.append(label("Playback speed", "eyebrow"))
        speeds = Gtk.Grid()
        speeds.set_column_spacing(7)
        speeds.set_row_spacing(7)
        self.speed_buttons = {}
        for index, speed in enumerate((.45, .5, .75, 1.0, 1.25, 1.5, 2.0)):
            choice = button(f"{speed:g}×", "speed-choice",
                            lambda _, value=speed: self.set_preview_speed(value))
            choice.set_size_request(78, -1)
            speeds.attach(choice, index % 2, index // 2, 1, 1)
            self.speed_buttons[speed] = choice
        popover_content.append(speeds)
        popover_content.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        for title, callback in (("Open file", lambda *_: self.open_path(self.preview_path)),
                                ("Open folder", lambda *_: self.open_path(self.preview_path.parent)),
                                ("Delete clip", self.confirm_delete_clip)):
            action = button(title, "danger-button" if title == "Delete clip" else "clip-tool", callback)
            if title != "Delete clip":
                action.connect("clicked", lambda *_: popover.popdown())
            popover_content.append(action)
        popover.set_child(popover_content)
        menu.set_popover(popover)
        self.preview_menu = menu
        self.preview_menu_popover = popover
        trim_button = button("Trim", "clip-tool", self.prompt_trim_clip)
        trim_button.set_size_request(58, 34)
        tools.append(trim_button)
        tools.append(menu)
        actions.append(tools)
        content.append(actions)
        self.preview_actions = actions
        return scroll

    def _settings_page(self):
        page = box(spacing=0)
        header = box(spacing=17)
        header.set_margin_top(34)
        header.set_margin_start(42)
        header.set_margin_end(42)
        header.set_margin_bottom(18)
        header.append(label("Settings", "headline"))
        tabs = Gtk.FlowBox()
        tabs.set_selection_mode(Gtk.SelectionMode.NONE)
        tabs.set_min_children_per_line(1)
        tabs.set_max_children_per_line(6)
        tabs.set_column_spacing(3)
        tabs.set_row_spacing(3)
        tabs.add_css_class("settings-tabs")
        self.settings_tabs = {}
        for key, title in (("capture", "Capture"), ("audio", "Audio"),
                           ("storage", "Storage"), ("appearance", "Appearance"),
                           ("hotkeys", "Hotkeys"), ("about", "About")):
            tab = button(title, "settings-tab", lambda _, section=key: self._scroll_to_settings(section))
            tabs.insert(tab, -1)
            self.settings_tabs[key] = tab
        header.append(tabs)
        page.append(header)

        scroll_area = Gtk.Overlay()
        scroll_area.set_vexpand(True)
        page.append(scroll_area)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        content = box(spacing=20)
        content.set_margin_start(42)
        content.set_margin_end(42)
        content.set_margin_bottom(108)
        scroll.set_child(content)
        scroll_area.set_child(scroll)
        self.settings_scroll = scroll
        self.settings_content = content
        self.settings_sections = {}

        capture = box(spacing=16)
        capture.append(label("Capture", "settings-section-title"))
        self.source_options = [(self.settings.source, "Finding displays…")]
        self.source_dropdown = Gtk.DropDown.new_from_strings(["Finding displays…"])
        capture.append(self._settings_row("Display", "Choose which screen to capture", self.source_dropdown))
        self.duration_options = [15, 30, 60, 120, 300, 600, None]
        duration_control = box(Gtk.Orientation.HORIZONTAL, 8)
        self.duration_dropdown = Gtk.DropDown.new_from_strings(
            ["15 sec", "30 sec", "1 min", "2 min", "5 min", "10 min", "Custom"])
        self.duration_dropdown.set_selected(self.duration_options.index(self.settings.duration)
                                            if self.settings.duration in self.duration_options else len(self.duration_options) - 1)
        duration_control.append(self.duration_dropdown)
        self.duration_entry, self.duration_custom_box = self._unit_field(str(self.settings.duration), "sec", 5)
        self.duration_entry.set_tooltip_text("10–3600 seconds")
        self.duration_custom_box.set_visible(self.duration_dropdown.get_selected() == len(self.duration_options) - 1)
        duration_control.append(self.duration_custom_box)
        self.responsive_rows.append(duration_control)
        capture.append(self._settings_row("Clip length", "Length saved when you press the clip keybind", duration_control))
        fps_control = box(Gtk.Orientation.HORIZONTAL, 8)
        self.fps_options = [30, 60, 120, None]
        self.fps_dropdown = Gtk.DropDown.new_from_strings(["30 FPS", "60 FPS", "120 FPS", "Custom"])
        self.fps_dropdown.set_selected(self.fps_options.index(self.settings.fps)
                                       if self.settings.fps in self.fps_options else 3)
        fps_control.append(self.fps_dropdown)
        self.custom_fps_entry = self._field(str(self.settings.fps), "FPS")
        self.custom_fps_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.custom_fps_entry.set_width_chars(5)
        self.custom_fps_entry.set_max_width_chars(5)
        self.custom_fps_entry.set_visible(self.fps_dropdown.get_selected() == 3)
        fps_control.append(self.custom_fps_entry)
        self.responsive_rows.append(fps_control)
        capture.append(self._settings_row("Frame rate", "Frames captured per second", fps_control))
        self._add_settings_section(content, "capture", capture)

        audio = box(spacing=16)
        audio.append(label("Audio", "settings-section-title"))
        self.desktop_switch = Gtk.Switch(active=self.settings.desktop_audio)
        self.mic_switch = Gtk.Switch(active=self.settings.microphone)
        audio.append(self._settings_row("Desktop audio", "Game and system sounds", self.desktop_switch))
        self.output_options = [(self.settings.audio_output, "Finding audio devices…")]
        self.output_dropdown = Gtk.DropDown.new_from_strings(["Finding audio devices…"])
        audio.append(self._settings_row("Output device", "Audio played by your computer", self.output_dropdown))
        audio.append(self._settings_row("Microphone", "Mix your voice into the clip", self.mic_switch))
        self.noise_switch = Gtk.Switch(active=self.settings.noise_suppression)
        audio.append(self._settings_row("Noise suppression", "Reduce handling noise and clicks in your voice",
                                        self.noise_switch))
        self.input_options = [(self.settings.audio_input, "Finding microphones…")]
        self.input_dropdown = Gtk.DropDown.new_from_strings(["Finding microphones…"])
        audio.append(self._settings_row("Input device", "Select your microphone", self.input_dropdown))
        microphone_test_row = box(Gtk.Orientation.HORIZONTAL, 10)
        microphone_test_row.add_css_class("mic-test-controls")
        self.mic_test_button = button("Test microphone", "secondary-button",
                                      self.test_selected_microphone)
        microphone_test_row.append(self.mic_test_button)
        meter_shell = box(Gtk.Orientation.HORIZONTAL, 9)
        meter_shell.add_css_class("mic-meter-shell")
        meter_shell.append(label("Level", "mic-meter-label"))
        self.mic_meter = MicrophoneMeter()
        meter_shell.append(self.mic_meter)
        microphone_test_row.append(meter_shell)
        self.responsive_rows.append(microphone_test_row)
        audio.append(self._settings_row("Microphone test", "Check your voice before recording", microphone_test_row))
        self.mic_test_notice = label("", "toast-label")
        audio.append(self.mic_test_notice)
        self._add_settings_section(content, "audio", audio)

        storage = box(spacing=16)
        storage.append(label("Storage", "settings-section-title"))
        self.folder_entry = self._field(self.settings.clips_dir, "Clips folder")
        self.folder_entry.set_width_chars(14)
        self.folder_entry.set_hexpand(True)
        storage.append(self._settings_row("Save to folder", "Where clips and recordings are stored", self.folder_entry))
        self.max_clip_entry, max_size_control = self._unit_field(str(self.settings.max_clip_mb), "MB", 6)
        self.max_clip_entry.set_tooltip_text("1–2000 MB")
        storage.append(self._settings_row("Maximum clip size", "Compress oversized clips without shortening them", max_size_control))
        self._add_settings_section(content, "storage", storage)

        appearance = box(spacing=15)
        appearance.append(label("Appearance", "settings-section-title"))
        self.theme_options = [("default", "Default"), ("liquid_glass", "Liquid Glass")]
        self.theme_dropdown = Gtk.DropDown.new_from_strings([title for _, title in self.theme_options])
        self.theme_dropdown.set_selected(1 if self.settings.theme == "liquid_glass" else 0)
        self.theme_dropdown.connect("notify::selected", self.preview_appearance)
        appearance.append(self._settings_row("Theme", "Choose the look of Clipdeck", self.theme_dropdown))
        self.blur_switch = Gtk.Switch(active=self.settings.blur_enabled)
        self.blur_switch.connect("notify::active", self.preview_appearance)
        appearance.append(self._settings_row("Background blur", "Let the desktop show through the window", self.blur_switch))
        self.notification_switch = Gtk.Switch(active=self.settings.clip_notifications)
        self.notification_switch.set_valign(Gtk.Align.CENTER)
        self.notification_switch.set_halign(Gtk.Align.START)
        notification_controls = box(Gtk.Orientation.HORIZONTAL, 12)
        notification_controls.append(self.notification_switch)
        notification_controls.append(button("Show popup", "secondary-button", self.preview_clip_notification))
        self.responsive_rows.append(notification_controls)
        appearance.append(self._settings_row("Clip notification", "Show a popup after saving a clip",
                                             notification_controls))
        self.sound_options = [("chime", "Original chime"), ("pulse", "Soft pulse"), ("off", "Off")]
        sound_controls = box(Gtk.Orientation.HORIZONTAL, 10)
        self.sound_dropdown = Gtk.DropDown.new_from_strings([title for _, title in self.sound_options])
        self.sound_dropdown.set_selected(next(index for index, (value, _) in enumerate(self.sound_options)
                                              if value == self.settings.clip_sound))
        self.sound_dropdown.set_size_request(190, -1)
        sound_controls.append(self.sound_dropdown)
        self.sound_preview_button = button("Preview", "secondary-button", self.preview_clip_sound)
        self.sound_preview_button.set_sensitive(self.settings.clip_sound != "off")
        sound_controls.append(self.sound_preview_button)
        self.responsive_rows.append(sound_controls)
        self.sound_dropdown.connect("notify::selected", self._sound_selection_changed)
        appearance.append(self._settings_row("Clip sound", "Play a sound when a clip is saved",
                                             sound_controls))
        notification_preview = box(spacing=8)
        notification_preview.append(label("Notification preview", "eyebrow"))
        preview_card = box(Gtk.Orientation.HORIZONTAL, 12)
        preview_card.add_css_class("notification-preview")
        preview_card.set_halign(Gtk.Align.START)
        preview_icon = icon("check", 24)
        preview_icon.add_css_class("notification-preview-icon")
        preview_card.append(preview_icon)
        preview_text = box(spacing=2)
        preview_text.set_valign(Gtk.Align.CENTER)
        preview_text.append(label("Clip saved", "notification-preview-title"))
        preview_text.append(label("Ready in your Library", "notification-preview-detail"))
        preview_card.append(preview_text)
        notification_preview.append(preview_card)
        appearance.append(notification_preview)
        self._add_settings_section(content, "appearance", appearance)

        shortcuts = box(spacing=13)
        shortcuts.append(label("Hotkeys", "settings-section-title"))
        shortcuts.append(label("Choose a keybind, then press F1–F24 or a key combination.", "subtle"))
        self.bind_buttons = {}
        for title, action in (("Save a clip", "save"), ("Start / stop recording", "record")):
            line = box(Gtk.Orientation.HORIZONTAL, 10)
            name = label(title, "shortcut-name", .5)
            name.set_hexpand(True)
            name.set_wrap(False)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_valign(Gtk.Align.FILL)
            name.set_size_request(-1, 50)
            line.append(name)
            bind_button = button(self.hotkeys.get(action, "Set keybind"), "secondary-button",
                                 lambda _, key=action: self.begin_bind(key))
            bind_button.set_size_request(160, 50)
            bind_button.set_focusable(True)
            line.append(bind_button)
            self.bind_buttons[action] = bind_button
            clear = button("Clear", "secondary-button", lambda _, key=action: self.clear_bind(key))
            clear.set_size_request(80, 50)
            line.append(clear)
            self.responsive_rows.append(line)
            shortcuts.append(line)
        self.bind_notice = label("", "toast-label")
        shortcuts.append(self.bind_notice)
        self._add_settings_section(content, "hotkeys", shortcuts)

        about = box(spacing=14)
        about.append(label("About", "settings-section-title"))
        identity = box(Gtk.Orientation.HORIZONTAL, 13)
        identity.set_valign(Gtk.Align.CENTER)
        logo = Gtk.Image.new_from_file(str(ASSETS / "clipdeck.svg"))
        logo.set_pixel_size(42)
        identity.append(logo)
        product = box(spacing=2)
        product.append(label("Clipdeck", "about-name"))
        product.append(label(f"Version {__version__}", "subtle"))
        identity.append(product)
        about.append(identity)
        description = label(
            "Clipdeck saves recent gameplay and full recordings on Linux. "
            "It captures games with GPU Screen Recorder, without needing OBS Studio. "
            "Your clips stay on your device in the folder you choose.",
            "about-copy",
        )
        about.append(description)
        repository = Gtk.LinkButton.new_with_label(
            "https://github.com/Filip1x3/clipdeck", "View repository",
        )
        repository.add_css_class("secondary-button")
        about.append(self._settings_row(
            "Repository", "Source code and project updates", repository,
        ))
        self._add_settings_section(content, "about", about)

        save_bar = box(Gtk.Orientation.HORIZONTAL, 12)
        save_bar.add_css_class("settings-save-bar")
        self.settings_notice = label("Unsaved changes", "settings-save-title")
        self.settings_notice.set_hexpand(True)
        self.settings_notice.set_valign(Gtk.Align.CENTER)
        save_bar.append(self.settings_notice)
        save_bar.append(button("Discard", "settings-discard", self.discard_settings))
        save_bar.append(button("Save changes", "settings-commit", self.save_settings))
        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        revealer.set_transition_duration(280)
        revealer.set_halign(Gtk.Align.FILL)
        revealer.set_valign(Gtk.Align.END)
        revealer.set_margin_start(42)
        revealer.set_margin_end(42)
        revealer.set_margin_bottom(19)
        revealer.set_child(save_bar)
        revealer.set_reveal_child(False)
        scroll_area.add_overlay(revealer)
        self.settings_save_revealer = revealer
        self.settings_save_bar = save_bar

        self._restoring_settings = False
        self._saved_snapshot = self._settings_snapshot()
        for entry in (self.duration_entry, self.custom_fps_entry, self.folder_entry, self.max_clip_entry):
            entry.connect("changed", self._settings_changed)
        for dropdown in (self.source_dropdown, self.duration_dropdown, self.fps_dropdown, self.output_dropdown,
                         self.input_dropdown, self.theme_dropdown, self.sound_dropdown):
            dropdown.connect("notify::selected", self._settings_changed)
        for switch in (self.desktop_switch, self.mic_switch, self.noise_switch,
                       self.blur_switch, self.notification_switch):
            switch.connect("notify::active", self._settings_changed)
        self.fps_dropdown.connect("notify::selected", self._fps_selection_changed)
        self.duration_dropdown.connect("notify::selected", self._duration_selection_changed)
        scroll.get_vadjustment().connect("value-changed", self._settings_scrolled)
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        wheel.connect("scroll", self._settings_wheel)
        scroll.add_controller(wheel)
        self._settings_scroll_tick = 0
        self._settings_scroll_target = 0.0
        self._active_settings_tab = None
        self._mark_settings_tab("capture")
        return page

    def _settings_row(self, title: str, detail: str, control: Gtk.Widget) -> Gtk.Box:
        row = box(Gtk.Orientation.HORIZONTAL, 18)
        row.add_css_class("settings-row")
        description = box(spacing=3)
        description.set_hexpand(True)
        description.append(label(title, "settings-row-title"))
        description.append(label(detail, "settings-row-detail"))
        row.append(description)
        control.set_valign(Gtk.Align.CENTER)
        if isinstance(control, Gtk.Switch):
            control.set_halign(Gtk.Align.START)
        if isinstance(control, Gtk.DropDown):
            control.set_size_request(220, -1)
        row.append(control)
        self.responsive_rows.append(row)
        return row

    def _add_settings_section(self, content: Gtk.Box, key: str, section: Gtk.Box):
        wrapper = padded_card(section)
        content.append(wrapper)
        self.settings_sections[key] = wrapper

    def _mark_settings_tab(self, key: str):
        if self._active_settings_tab == key:
            return
        self._active_settings_tab = key
        for section, tab in self.settings_tabs.items():
            if section == key:
                tab.add_css_class("active")
            else:
                tab.remove_css_class("active")

    def _scroll_to_settings(self, key: str, attempt: int = 0):
        adjustment = self.settings_scroll.get_vadjustment()
        if (key != "capture" and attempt < 4
                and adjustment.get_upper() <= adjustment.get_page_size() + 1):
            GLib.timeout_add(55, lambda: (self._scroll_to_settings(key, attempt + 1), False)[1])
            self._mark_settings_tab(key)
            return
        destination = (adjustment.get_upper() - adjustment.get_page_size()
                       if key == "about" else self._settings_section_offset(key))
        self._animate_settings_scroll(destination, 0.38, key)
        self._mark_settings_tab(key)

    def _settings_scrolled(self, adjustment):
        position = adjustment.get_value() + 28
        active = "capture"
        for key in self.settings_sections:
            if self._settings_section_offset(key) <= position:
                active = key
        if (adjustment.get_upper() > adjustment.get_page_size() + 1
                and adjustment.get_value() >= adjustment.get_upper() - adjustment.get_page_size() - 2):
            active = "about"
        self._mark_settings_tab(active)

    def _settings_section_offset(self, key: str) -> float:
        offset = 0
        for section_key, section in self.settings_sections.items():
            if section_key == key:
                return float(offset)
            offset += section.get_allocated_height() + self.settings_content.get_spacing()
        return float(offset)

    def _settings_wheel(self, controller, _dx, dy):
        if controller.get_unit() != Gdk.ScrollUnit.WHEEL:
            return False  # Keep native touchpad scrolling.
        adjustment = self.settings_scroll.get_vadjustment()
        start = self._settings_scroll_target if self._settings_scroll_tick else adjustment.get_value()
        self._animate_settings_scroll(start + dy * 105, 0.25)
        return True

    def _animate_settings_scroll(self, destination: float, duration: float, section: str | None = None):
        adjustment = self.settings_scroll.get_vadjustment()
        limit = max(0.0, adjustment.get_upper() - adjustment.get_page_size())
        destination = max(0.0, min(destination, limit))
        self._settings_scroll_target = destination
        if self._settings_scroll_tick:
            self.settings_scroll.remove_tick_callback(self._settings_scroll_tick)
            self._settings_scroll_tick = 0
        start = adjustment.get_value()
        if abs(destination - start) < 1 or not Gtk.Settings.get_default().get_property("gtk-enable-animations"):
            adjustment.set_value(destination)
            if section:
                self._mark_settings_tab(section)
            return
        started = time.monotonic()
        def step(_widget, _clock):
            progress = min(1.0, (time.monotonic() - started) / duration)
            eased = 1 - (1 - progress) ** 3
            adjustment.set_value(start + (destination - start) * eased)
            if progress >= 1:
                self._settings_scroll_tick = 0
                if section:
                    self._mark_settings_tab(section)
                return False
            return True
        self._settings_scroll_tick = self.settings_scroll.add_tick_callback(step)

    def _fps_selection_changed(self, *_):
        self.custom_fps_entry.set_visible(self.fps_dropdown.get_selected() == 3)

    def _duration_selection_changed(self, *_):
        self.duration_custom_box.set_visible(self.duration_dropdown.get_selected() == len(self.duration_options) - 1)

    def _sound_selection_changed(self, *_):
        self.sound_preview_button.set_sensitive(
            self._selected_setting(self.sound_options, self.sound_dropdown) != "off")

    def preview_clip_sound(self, *_):
        preview_sound(self._selected_setting(self.sound_options, self.sound_dropdown))

    def preview_clip_notification(self, *_):
        preview_notification(self._selected_setting(self.theme_options, self.theme_dropdown),
                             self.blur_switch.get_active())

    def _selected_setting(self, options, dropdown):
        index = dropdown.get_selected()
        return options[index][0] if index < len(options) else options[0][0]

    def _settings_snapshot(self):
        fps_index = self.fps_dropdown.get_selected()
        fps = (self.custom_fps_entry.get_text().strip() if fps_index == 3
               else str(self.fps_options[fps_index]))
        duration_index = self.duration_dropdown.get_selected()
        duration = (self.duration_entry.get_text().strip() if self.duration_options[duration_index] is None
                    else str(self.duration_options[duration_index]))
        return (duration, fps, self.max_clip_entry.get_text().strip(),
                self._selected_setting(self.source_options, self.source_dropdown),
                self.folder_entry.get_text().strip(), self.desktop_switch.get_active(),
                self.mic_switch.get_active(), self.noise_switch.get_active(),
                self._selected_setting(self.output_options, self.output_dropdown),
                self._selected_setting(self.input_options, self.input_dropdown),
                self._selected_setting(self.theme_options, self.theme_dropdown),
                self.blur_switch.get_active(), self.notification_switch.get_active(),
                self._selected_setting(self.sound_options, self.sound_dropdown),
                self.pending_hotkeys.get("save"), self.pending_hotkeys.get("record"))

    def _settings_changed(self, *_):
        if self._restoring_settings:
            return
        dirty = self._settings_snapshot() != self._saved_snapshot
        self.settings_save_revealer.set_reveal_child(dirty)
        if dirty:
            self.settings_notice.set_text("Unsaved changes")

    def discard_settings(self, *_):
        self._restoring_settings = True
        self.pending_bind = None
        self.pending_hotkeys = dict(self.hotkeys)
        for action, bind_button in self.bind_buttons.items():
            bind_button.set_label(self.pending_hotkeys.get(action, "Set keybind"))
        self.bind_notice.set_text("")
        self.duration_entry.set_text(str(self.settings.duration))
        self.duration_dropdown.set_selected(self.duration_options.index(self.settings.duration)
                                            if self.settings.duration in self.duration_options else len(self.duration_options) - 1)
        self.max_clip_entry.set_text(str(self.settings.max_clip_mb))
        self.custom_fps_entry.set_text(str(self.settings.fps))
        self.fps_dropdown.set_selected(self.fps_options.index(self.settings.fps)
                                       if self.settings.fps in self.fps_options else 3)
        self.source_dropdown.set_selected(next((index for index, (value, _) in enumerate(self.source_options)
                                               if value == self.settings.source), 0))
        self.output_dropdown.set_selected(next((index for index, (value, _) in enumerate(self.output_options)
                                               if value == self.settings.audio_output), 0))
        self.input_dropdown.set_selected(next((index for index, (value, _) in enumerate(self.input_options)
                                              if value == self.settings.audio_input), 0))
        self.folder_entry.set_text(self.settings.clips_dir)
        self.desktop_switch.set_active(self.settings.desktop_audio)
        self.mic_switch.set_active(self.settings.microphone)
        self.noise_switch.set_active(self.settings.noise_suppression)
        self.theme_dropdown.set_selected(1 if self.settings.theme == "liquid_glass" else 0)
        self.blur_switch.set_active(self.settings.blur_enabled)
        self.notification_switch.set_active(self.settings.clip_notifications)
        self.sound_dropdown.set_selected(next(index for index, (value, _) in enumerate(self.sound_options)
                                              if value == self.settings.clip_sound))
        self._apply_appearance(self.settings.theme, self.settings.blur_enabled)
        self._restoring_settings = False
        self._saved_snapshot = self._settings_snapshot()
        self.settings_save_revealer.set_reveal_child(False)

    def _apply_appearance(self, theme: str, blur: bool):
        for style in ("liquid-glass", "blur-enabled", "no-blur"):
            self.window.remove_css_class(style)
        if theme == "liquid_glass":
            self.window.add_css_class("liquid-glass")
        self.window.add_css_class("blur-enabled" if blur else "no-blur")

    def preview_appearance(self, *_):
        self._apply_appearance(self.theme_options[self.theme_dropdown.get_selected()][0],
                               self.blur_switch.get_active())

    def test_selected_microphone(self, *_):
        if self.mic_test_future and not self.mic_test_future.done():
            self.mic_stop.set()
            self.mic_test_button.set_label("Finishing…")
            self.mic_test_button.set_sensitive(False)
            return
        device = self.input_options[self.input_dropdown.get_selected()][0]
        self.mic_stop = threading.Event()
        self.mic_meter.set_level(0)
        self.mic_test_button.set_label("Stop test")
        self.mic_test_button.set_sensitive(True)
        self.mic_test_notice.set_text("Speak into your microphone. Stop whenever you like.")
        def level(value):
            GLib.idle_add(self.mic_meter.set_level, value)
        def playback():
            def update():
                self.mic_test_button.set_label("Playing back…")
                self.mic_test_button.set_sensitive(False)
                self.mic_test_notice.set_text("Playing your recorded voice.")
                return False
            GLib.idle_add(update)
        future = self.executor.submit(
            test_microphone, device, 10, playback, level, self.mic_stop,
            self.noise_switch.get_active()
        )
        self.mic_test_future = future
        def done(completed):
            def update():
                self.mic_test_button.set_label("Test microphone")
                self.mic_test_button.set_sensitive(True)
                self.mic_meter.set_level(0)
                try:
                    signal = completed.result()
                    self.mic_test_notice.set_text(
                        "Microphone test complete." if signal
                        else "No microphone signal detected. Check the selected input."
                    )
                except (MicrophoneError, OSError) as exc:
                    self.mic_test_notice.set_text(str(exc))
                return False
            GLib.idle_add(update)
        future.add_done_callback(done)

    def begin_bind(self, action: str):
        if self.pending_bind and self.pending_bind != action:
            self.bind_buttons[self.pending_bind].set_label(self.pending_hotkeys.get(self.pending_bind, "Set keybind"))
        self.pending_bind = action
        self.bind_buttons[action].set_label("Press a key…")
        self.bind_buttons[action].grab_focus()
        self.bind_notice.set_text("Press F1–F24 or a key with Ctrl, Alt or Super. Escape cancels.")

    def _on_bind_key(self, _controller, keyval, _keycode, state):
        if not self.pending_bind:
            return False
        name = Gdk.keyval_name(keyval)
        if name == "Escape":
            action = self.pending_bind
            self.pending_bind = None
            self.bind_buttons[action].set_label(self.pending_hotkeys.get(action, "Set keybind"))
            self.bind_notice.set_text("")
            return True
        if not name or name.lower().endswith(("_l", "_r")):
            return True
        modifiers = []
        for text, flag in (("CTRL", Gdk.ModifierType.CONTROL_MASK),
                           ("ALT", Gdk.ModifierType.ALT_MASK),
                           ("SHIFT", Gdk.ModifierType.SHIFT_MASK),
                           ("SUPER", Gdk.ModifierType.SUPER_MASK)):
            if state & flag:
                modifiers.append(text)
        function_key = name.upper().startswith("F") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24
        if not function_key and not any(part in modifiers for part in ("CTRL", "ALT", "SUPER")):
            self.bind_notice.set_text("Use F1–F24 or hold Ctrl, Alt or Super.")
            return True
        combo = " + ".join(modifiers + [name.upper()])
        action = self.pending_bind
        self.pending_bind = None
        self._stage_bind(action, combo)
        return True

    def clear_bind(self, action: str):
        self.pending_bind = None
        self._stage_bind(action, None)

    def _stage_bind(self, action: str, combo: str | None):
        try:
            if combo:
                parse_combo(combo)
                if combo in (value for key, value in self.pending_hotkeys.items() if key != action):
                    raise HotkeyError("That shortcut is already used in Clipdeck.")
                self.pending_hotkeys[action] = combo
            else:
                self.pending_hotkeys.pop(action, None)
        except HotkeyError as exc:
            self.bind_notice.set_text(str(exc))
            self.bind_buttons[action].set_label(self.pending_hotkeys.get(action, "Set keybind"))
            return
        self.bind_buttons[action].set_label(self.pending_hotkeys.get(action, "Set keybind"))
        self.bind_notice.set_text("Shortcut pending. Save changes to apply it.")
        self._settings_changed()

    def _load_devices(self):
        def discover():
            try:
                monitors = list_monitors()
            except (RecorderError, OSError):
                monitors = []
            try:
                audio = list_audio_devices()
            except (RecorderError, OSError):
                audio = []
            return monitors, audio
        def done(future):
            def update():
                monitors, audio = future.result()
                sources = [("screen", "First display")]
                sources.extend((name, f"{name}  ·  {resolution}") for name, resolution in monitors)
                sources.append(("portal", "Choose with system dialog"))
                if self.settings.source not in [item[0] for item in sources]:
                    sources.append((self.settings.source, self.settings.source))
                self.source_options = self._dropdown_options(self.source_dropdown, sources, self.settings.source)

                outputs = [("default_output", "Default desktop audio")]
                outputs.extend((name, description) for name, description in audio
                               if name != "default_output" and (name.endswith(".monitor") or "Monitor of" in description))
                inputs = [("default_input", "Default microphone")]
                inputs.extend((name, description) for name, description in audio
                              if name not in ("default_input", "default_output") and not name.endswith(".monitor")
                              and name != FILTER_SOURCE and "Monitor of" not in description)
                for options, selected in ((outputs, self.settings.audio_output), (inputs, self.settings.audio_input)):
                    if selected not in [item[0] for item in options]:
                        options.append((selected, selected))
                self.output_options = self._dropdown_options(self.output_dropdown, outputs, self.settings.audio_output)
                self.input_options = self._dropdown_options(self.input_dropdown, inputs, self.settings.audio_input)
                return False
            GLib.idle_add(update)
        self.executor.submit(discover).add_done_callback(done)

    @staticmethod
    def _dropdown_options(dropdown: Gtk.DropDown, options: list[tuple[str, str]], selected: str):
        dropdown.set_model(Gtk.StringList.new([title for _, title in options]))
        dropdown.set_selected(next((index for index, (value, _) in enumerate(options) if value == selected), 0))
        return options

    def _field(self, value: str, placeholder: str) -> Gtk.Entry:
        entry = Gtk.Entry(text=value)
        entry.set_placeholder_text(placeholder)
        entry.add_css_class("field")
        return entry

    def _unit_field(self, value: str, unit: str, width_chars: int):
        entry = self._field(value, "")
        entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        entry.set_width_chars(width_chars)
        entry.set_max_width_chars(width_chars)
        entry.add_css_class("unit-field")
        shell = Gtk.Overlay()
        shell.set_child(entry)
        suffix = label(unit, "unit-suffix")
        suffix.set_halign(Gtk.Align.END)
        suffix.set_valign(Gtk.Align.CENTER)
        suffix.set_margin_end(14)
        suffix.set_can_target(False)
        shell.add_overlay(suffix)
        return entry, shell

    def navigate(self, page: str):
        if self.preview_fullscreen and page != "preview":
            self.toggle_preview_fullscreen()
        if self.stack.get_visible_child_name() == "preview" and page != "preview" and self.player:
            self.player.stop()
            self.player = None
        self.stack.set_visible_child_name(page)
        for key, item in self.nav.items():
            if key == page:
                item.add_css_class("active")
            else:
                item.remove_css_class("active")
        if page == "library":
            self.populate_library()
        elif page == "dashboard":
            self.populate_recent()

    def _run(self, task, on_success=None, on_error=None):
        if self.busy:
            return
        self.busy = True
        future = self.executor.submit(task)
        def done(completed):
            def show():
                self.busy = False
                try:
                    result = completed.result()
                    if on_success:
                        on_success(result)
                except (RecorderError, MicrophoneError, HotkeyError, ValueError, OSError) as exc:
                    (on_error or self.notice.set_text)(str(exc))
                return False
            GLib.idle_add(show)
        future.add_done_callback(done)

    def _periodic_refresh(self):
        if self._quitting:
            return False
        if self.window and not self.busy:
            self.refresh_status()
        return True

    def ensure_capture(self):
        if self._quitting:
            return
        self.next_start_attempt = time.monotonic() + 60
        self._run(lambda: Recorder(self.settings).start(), lambda _: self.refresh_status())

    def refresh_status(self):
        self._run(lambda: Recorder(self.settings).status(), self._update_status)

    def _update_status(self, status):
        self.replay = status["replay"]
        self.record = status["record"]
        if not self._quitting and not self.replay and time.monotonic() >= self.next_start_attempt:
            GLib.idle_add(self.ensure_capture)

    def save_replay(self, *_):
        if self.saving_clip:
            return
        self.saving_clip = True
        self.notice.set_text("Saving clip…")
        settings = self.settings
        def saved(path):
            clip_saved(settings)
            GLib.idle_add(self.notice.set_text, "Saved: " + Path(path).name + " · Optimizing size…")
        future = self.executor.submit(lambda: Recorder(settings).save_replay(on_saved=saved))
        def done(completed):
            def update():
                self.saving_clip = False
                try:
                    path = completed.result()
                    self.notice.set_text("Saved: " + Path(path).name)
                    self.populate_recent()
                    self.populate_library()
                except (RecorderError, OSError) as exc:
                    self.notice.set_text(str(exc))
                    self.populate_recent()
                    self.populate_library()
                return False
            GLib.idle_add(update)
        future.add_done_callback(done)

    def toggle_record(self, *_):
        self._run(lambda: Recorder(self.settings).toggle_record(),
                  lambda path: (self.notice.set_text("Saved: " + Path(path).name) if path else self.notice.set_text("Recording started."), self.refresh_status()))

    def save_settings(self, *_):
        if self.busy:
            self.settings_notice.set_text("Please wait before saving settings.")
            return
        try:
            fps_index = self.fps_dropdown.get_selected()
            fps_text = (self.custom_fps_entry.get_text().strip() if fps_index == 3
                        else str(self.fps_options[fps_index]))
            duration_index = self.duration_dropdown.get_selected()
            duration_text = (self.duration_entry.get_text().strip() if self.duration_options[duration_index] is None
                             else str(self.duration_options[duration_index]))
            max_clip_text = self.max_clip_entry.get_text().strip()
            if not duration_text.isdigit() or not fps_text.isdigit() or not max_clip_text.isdigit():
                raise ValueError("Clip length, frame rate and size must be whole numbers.")
            fps = int(fps_text)
            settings = Settings(duration=int(duration_text), fps=fps, max_clip_mb=int(max_clip_text),
                                source=self._selected_setting(self.source_options, self.source_dropdown),
                                clips_dir=self.folder_entry.get_text().strip(),
                                desktop_audio=self.desktop_switch.get_active(), microphone=self.mic_switch.get_active(),
                                noise_suppression=self.noise_switch.get_active(),
                                audio_output=self._selected_setting(self.output_options, self.output_dropdown),
                                audio_input=self._selected_setting(self.input_options, self.input_dropdown),
                                theme=self._selected_setting(self.theme_options, self.theme_dropdown),
                                blur_enabled=self.blur_switch.get_active(),
                                clip_notifications=self.notification_switch.get_active(),
                                clip_sound=self._selected_setting(self.sound_options, self.sound_dropdown))
            settings.validate()
        except (ValueError, OSError) as exc:
            self.settings_notice.set_text("Enter valid values: " + str(exc))
            return
        capture_fields = ("duration", "fps", "source", "clips_dir", "desktop_audio",
                          "microphone", "noise_suppression", "audio_output", "audio_input")
        capture_changed = any(getattr(settings, field) != getattr(self.settings, field)
                              for field in capture_fields)
        pending_hotkeys = dict(self.pending_hotkeys)
        hotkeys_changed = pending_hotkeys != self.hotkeys
        def apply():
            if not capture_changed:
                settings.save()
            else:
                previous = Recorder(self.settings)
                status = previous.status()
                if status["record"]:
                    raise RecorderError("Stop the full recording before changing capture settings.")
                settings.save()
                if status["replay"]:
                    previous.stop()
                Recorder(settings).start()
            if hotkeys_changed:
                save_hotkeys(pending_hotkeys)
            return None
        self.settings_notice.set_text("Applying changes…")
        self.settings_content.set_sensitive(False)
        self.settings_save_bar.set_sensitive(False)
        def success(_):
            self.settings_content.set_sensitive(True)
            self.settings_save_bar.set_sensitive(True)
            self.settings = settings
            self.hotkeys = pending_hotkeys
            self._apply_appearance(settings.theme, settings.blur_enabled)
            self._saved_snapshot = self._settings_snapshot()
            self.settings_save_revealer.set_reveal_child(False)
            self.populate_recent()
            self.populate_library()
            self.refresh_status()
        def failure(message):
            self.settings_content.set_sensitive(True)
            self.settings_save_bar.set_sensitive(True)
            self.settings_notice.set_text(message)
        self._run(apply, success, failure)

    def populate_library(self):
        child = self.library_list.get_first_child()
        while child:
            following = child.get_next_sibling()
            self.library_list.remove(child)
            child = following
        query = self.library_search.get_text().strip().casefold()
        self.library_heading.set_text("Search results" if query else "Recent clips")
        files = recent_clips(self.settings.clips_dir, None if query else 50)
        if query:
            files = [path for path in files if query in path.stem.casefold()]
        if not files:
            self.library_list.append(label("No matching clips." if query else "Your saved clips will appear here.", "subtle"))
            return
        for path in files:
            self.library_list.insert(self._clip_card(path), -1)

    def populate_recent(self):
        child = self.recent_list.get_first_child()
        while child:
            following = child.get_next_sibling()
            self.recent_list.remove(child)
            child = following
        files = recent_clips(self.settings.clips_dir, 50)
        self.recent_count = len(files)
        if not files:
            self.recent_list.append(label("Your latest clips will appear here.", "subtle"))
            self._update_recent_arrows()
            return
        for path in files:
            self.recent_list.append(self._clip_card(path, 196))
        self.recent_scroll.get_hadjustment().set_value(0)
        GLib.idle_add(self._update_recent_arrows)

    def _move_recent(self, direction: int):
        adjustment = self.recent_scroll.get_hadjustment()
        step = 209
        destination = max(0, min(adjustment.get_upper() - adjustment.get_page_size(),
                                 adjustment.get_value() + direction * step))
        start = adjustment.get_value()
        if self._recent_tick:
            self.recent_scroll.remove_tick_callback(self._recent_tick)
            self._recent_tick = 0
        started = time.monotonic()
        def animate(_widget, _clock):
            progress = min(1.0, (time.monotonic() - started) / .22)
            adjustment.set_value(start + (destination - start) * (1 - (1 - progress) ** 3))
            if progress >= 1:
                self._recent_tick = 0
            return progress < 1
        self._recent_tick = self.recent_scroll.add_tick_callback(animate)

    def _update_recent_arrows(self, *_):
        adjustment = self.recent_scroll.get_hadjustment()
        count = getattr(self, "recent_count", 0)
        can_scroll = adjustment.get_upper() > adjustment.get_page_size() + 1
        self.recent_back.set_visible(can_scroll)
        self.recent_next.set_visible(can_scroll)
        self.recent_back.set_sensitive(can_scroll and adjustment.get_value() > 1)
        self.recent_next.set_sensitive(
            can_scroll and adjustment.get_value() + adjustment.get_page_size() < adjustment.get_upper() - 1
        )
        self.recent_page_label.set_text(f"{min(count, int(adjustment.get_value() / 209) + 1)} / {count}" if count else "")
        return False

    def _clip_card(self, path: Path, width: int = 210) -> Gtk.Box:
        card = box()
        card.add_css_class("clip-tile")
        card.set_size_request(width, -1)
        main = Gtk.Button()
        main.add_css_class("clip-main")
        main.set_tooltip_text("Preview clip")
        main.connect("clicked", lambda *_: self.preview_clip(path))
        layout = box(spacing=0)
        thumbnail = Gtk.Overlay()
        thumbnail.add_css_class("clip-thumb")
        thumbnail.set_overflow(Gtk.Overflow.HIDDEN)
        thumbnail.set_size_request(width, round(width * 9 / 16))
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_size_request(width, round(width * 9 / 16))
        thumbnail.set_child(picture)
        duration = label("", "clip-duration")
        duration.set_halign(Gtk.Align.END)
        duration.set_valign(Gtk.Align.END)
        duration.set_margin_end(8)
        duration.set_margin_bottom(8)
        duration.set_visible(False)
        thumbnail.add_overlay(duration)
        layout.append(thumbnail)
        details = box(spacing=5)
        details.set_margin_top(12)
        details.set_margin_bottom(13)
        details.set_margin_start(12)
        details.set_margin_end(12)
        title = label(path.stem, "clip-title")
        title.set_wrap(False)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_max_width_chars(24)
        details.append(title)
        try:
            stat = path.stat()
            date = dt.datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y · %H:%M")
            info = f"{date}  ·  {stat.st_size / 1024 / 1024:.1f} MB"
        except OSError:
            info = ""
        metadata = label(info, "clip-meta")
        metadata.set_wrap(False)
        metadata.set_ellipsize(Pango.EllipsizeMode.END)
        details.append(metadata)
        layout.append(details)
        main.set_child(layout)
        card.append(main)
        actions = box(Gtk.Orientation.HORIZONTAL, 7)
        actions.set_margin_start(12)
        actions.set_margin_end(12)
        actions.set_margin_bottom(12)
        for icon_name, tooltip, callback in (
            ("pencil", "Rename clip", lambda *_: self.prompt_rename_clip(path)),
            ("copy", "Copy file path", lambda *_: self.copy_clip_path(path)),
            ("external-link", "Open file", lambda *_: self.open_path(path)),
            ("folder-open", "Open folder", lambda *_: self.open_path(path.parent)),
            ("trash", "Delete clip", lambda *_: self.confirm_delete_path(path)),
        ):
            action = Gtk.Button()
            action.add_css_class("clip-action")
            if icon_name == "trash":
                action.add_css_class("danger")
            action.set_child(icon(icon_name, 14))
            action.set_tooltip_text(tooltip)
            action.connect("clicked", callback)
            actions.append(action)
        card.append(actions)
        self._load_clip_preview(path, picture, duration)
        return card

    def _load_clip_preview(self, path: Path, picture: Gtk.Picture, duration: Gtk.Label):
        try:
            stat = path.stat()
        except OSError:
            return
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        future = self.preview_jobs.get(key)
        if future is None:
            future = self.media_executor.submit(clip_preview, path)
            self.preview_jobs[key] = future
        def done(completed):
            def update():
                try:
                    thumbnail, length = completed.result()
                    if thumbnail:
                        picture.set_file(Gio.File.new_for_path(str(thumbnail)))
                    duration.set_text(length)
                    duration.set_visible(bool(length))
                except (OSError, ValueError):
                    duration.set_visible(False)
                return False
            GLib.idle_add(update)
        future.add_done_callback(done)

    def preview_clip(self, path: Path):
        if not path.is_file():
            self.notice.set_text("This clip is no longer available.")
            self.populate_recent()
            self.populate_library()
            return
        if self.player:
            self.player.stop()
        if self.seek_source:
            GLib.source_remove(self.seek_source)
            self.seek_source = 0
        self.seek_dragging = False
        self.seek_pending = False
        self.seek_waiting_frame = False
        self._trim_previewing = False
        if self.trim_overlay.get_visible():
            self._close_trim_overlay(resume=False)
        current = self.stack.get_visible_child_name()
        if current != "preview":
            self.preview_origin = current
        self.preview_path = path
        self.preview_duration = 0.0
        self.preview_title.set_text(path.stem)
        stat = path.stat()
        self.preview_meta.set_text(
            f"{dt.datetime.fromtimestamp(stat.st_mtime):%d %b %Y · %H:%M}  ·  "
            f"{stat.st_size / 1024 / 1024:.1f} MB"
        )
        self.preview_picture.set_paintable(None)
        self.preview_placeholder.set_text("Preparing preview…")
        self.preview_placeholder.set_visible(True)
        self.preview_play_button.set_label("Pause")
        self._update_preview_position(0)
        self.navigate("preview")
        self.player = ClipPlayer(path, self._preview_frame, self._preview_finished,
                                 self._preview_error)
        self.preview_speed = 1.0
        self._mark_preview_speed()
        self.player.play(0)
        def duration_ready(completed):
            def update():
                if self.preview_path == path:
                    self.preview_duration = completed.result()
                    self.preview_seek.handler_block(self.preview_seek_handler)
                    self.preview_seek.set_range(0, max(1, self.preview_duration))
                    self.preview_seek.handler_unblock(self.preview_seek_handler)
                    self._update_preview_position(self.player.position if self.player else 0)
                return False
            GLib.idle_add(update)
        self.media_executor.submit(video_duration, path).add_done_callback(duration_ready)

    @staticmethod
    def _time_text(seconds: float):
        value = max(0, int(seconds))
        return f"{value // 60}:{value % 60:02d}"

    def _update_preview_position(self, position: float):
        if self.seek_dragging or self.seek_pending:
            return
        self.preview_seek.handler_block(self.preview_seek_handler)
        self.preview_seek.set_value(min(position, max(1, self.preview_duration)))
        self.preview_seek.handler_unblock(self.preview_seek_handler)
        self.preview_time.set_text(
            f"{self._time_text(position)} / {self._time_text(self.preview_duration)}"
        )

    def _preview_frame(self, frame: bytes, position: float):
        if self.seek_pending:
            if not self.seek_waiting_frame or abs(position - self.seek_target) > .75:
                return
            self.seek_pending = False
            self.seek_waiting_frame = False
        texture = Gdk.MemoryTexture.new(WIDTH, HEIGHT, Gdk.MemoryFormat.R8G8B8,
                                        GLib.Bytes.new(frame), WIDTH * 3)
        self.preview_picture.set_paintable(texture)
        self.preview_placeholder.set_visible(False)
        self._update_preview_position(position)

    def _preview_finished(self):
        self.seek_pending = False
        self.seek_waiting_frame = False
        self.preview_play_button.set_label("Play")

    def _preview_error(self, message: str):
        self.seek_pending = False
        self.seek_waiting_frame = False
        self.preview_placeholder.set_text(message)
        self.preview_placeholder.set_visible(True)
        self.preview_play_button.set_label("Play")

    def _mark_preview_speed(self):
        for value, choice in self.speed_buttons.items():
            if value == self.preview_speed:
                choice.add_css_class("active")
            else:
                choice.remove_css_class("active")

    def set_preview_speed(self, speed: float):
        self.preview_speed = speed
        self._mark_preview_speed()
        self.preview_menu_popover.popdown()
        if self.player:
            self.player.set_speed(speed)

    def confirm_delete_clip(self, *_):
        self.preview_menu_popover.popdown()
        if not getattr(self, "preview_path", None):
            return
        return self.confirm_delete_path(self.preview_path)

    def prompt_trim_clip(self, *_):
        if not getattr(self, "preview_path", None) or self.preview_duration <= 0:
            return
        self._trim_was_playing = bool(self.player and self.player.playing)
        self._trim_restore_position = self.player.position if self.player else 0
        if self.player and self.player.playing:
            self.player.pause()
            self.preview_play_button.set_label("Play")
        self._trim_previewing = False
        self.trim_saving = False
        self.trim_title.set_text("Trim · " + self.preview_path.stem)
        self.trim_timeline.set_range(self.preview_duration)
        self.trim_notice.set_text("")
        self.trim_save_button.set_sensitive(True)
        self.trim_picture.set_paintable(None)
        self.trim_seek.handler_block(self.trim_seek_handler)
        self.trim_seek.set_range(0, max(1, self.preview_duration))
        self.trim_seek.set_value(0)
        self.trim_seek.handler_unblock(self.trim_seek_handler)
        self.trim_time.set_text(f"0:00 / {self._time_text(self.preview_duration)}")
        self.trim_play_button.set_label("Play")
        self.trim_overlay.set_visible(True)
        self.trim_player = ClipPlayer(self.preview_path, self._trim_frame, self._trim_finished, self._trim_error)
        self.trim_player.seek(0)

    def _trim_range_changed(self, start: float, end: float):
        self.trim_start_label.set_text(f"In {int(start // 60)}:{start % 60:04.1f}")
        length = end - start
        self.trim_length_label.set_text(f"Selected {int(length // 60)}:{length % 60:04.1f}")
        self.trim_end_label.set_text(f"Out {int(end // 60)}:{end % 60:04.1f}")

    def _trim_handle_released(self, position: float):
        self.trim_seek.set_value(position)

    def _trim_frame(self, frame: bytes, position: float):
        texture = Gdk.MemoryTexture.new(WIDTH, HEIGHT, Gdk.MemoryFormat.R8G8B8,
                                        GLib.Bytes.new(frame), WIDTH * 3)
        self.trim_picture.set_paintable(texture)
        self.trim_seek.handler_block(self.trim_seek_handler)
        self.trim_seek.set_value(min(position, max(1, self.preview_duration)))
        self.trim_seek.handler_unblock(self.trim_seek_handler)
        self.trim_time.set_text(f"{self._time_text(position)} / {self._time_text(self.preview_duration)}")
        if self._trim_previewing and position >= self.trim_timeline.end:
            self._trim_previewing = False
            if self.trim_player and self.trim_player.playing:
                self.trim_player.pause()
                self.trim_play_button.set_label("Play")

    def _trim_finished(self):
        self._trim_previewing = False
        self.trim_play_button.set_label("Play")

    def _trim_error(self, message: str):
        self.trim_notice.set_text(message)
        self.trim_play_button.set_label("Play")

    def _toggle_trim_playback(self, *_):
        if not self.trim_player:
            return
        if self.trim_player.playing:
            self.trim_player.pause()
            self.trim_play_button.set_label("Play")
        else:
            position = self.trim_player.position
            if position >= self.trim_timeline.end:
                position = self.trim_timeline.start
            self._trim_previewing = True
            self.trim_player.play(position)
            self.trim_play_button.set_label("Pause")

    def _trim_seek_changed(self, scale):
        if not self.trim_player:
            return
        self._trim_previewing = False
        if self.trim_player.playing:
            self.trim_player.pause()
            self.trim_play_button.set_label("Play")
        self.trim_time.set_text(f"{self._time_text(scale.get_value())} / {self._time_text(self.preview_duration)}")
        if self.trim_seek_source:
            GLib.source_remove(self.trim_seek_source)
        self.trim_seek_source = GLib.timeout_add(180, self._commit_trim_seek)

    def _commit_trim_seek(self):
        self.trim_seek_source = 0
        if self.trim_player:
            self.trim_player.seek(self.trim_seek.get_value())
        return False

    def _set_trim_in(self, *_):
        self.trim_timeline.set_range(self.preview_duration,
                                     min(self.trim_seek.get_value(), self.trim_timeline.end - .1),
                                     self.trim_timeline.end)

    def _set_trim_out(self, *_):
        self.trim_timeline.set_range(self.preview_duration, self.trim_timeline.start,
                                     max(self.trim_seek.get_value(), self.trim_timeline.start + .1))

    def _preview_trim_selection(self, *_):
        if not self.trim_player:
            return
        self._trim_previewing = True
        self.trim_player.play(self.trim_timeline.start)
        self.trim_play_button.set_label("Pause")

    def _save_trimmed_clip(self, *_):
        if self.trim_saving:
            return
        self.trim_saving = True
        self.trim_save_button.set_sensitive(False)
        if self.trim_player and self.trim_player.playing:
            self.trim_player.pause()
            self.trim_play_button.set_label("Play")
        path = self.preview_path
        start, end = self.trim_timeline.start, self.trim_timeline.end
        self.trim_notice.set_text("Saving trimmed clip…")
        future = self.executor.submit(lambda: trim_clip(path, start, end))
        def done(completed):
            def update():
                self.trim_saving = False
                self.trim_save_button.set_sensitive(True)
                try:
                    result = completed.result()
                except (ValueError, OSError) as exc:
                    self.trim_notice.set_text(str(exc))
                    return False
                self._close_trim_overlay(resume=False)
                self.populate_library()
                self.populate_recent()
                self.preview_clip(result)
                return False
            GLib.idle_add(update)
        future.add_done_callback(done)

    def _close_trim_overlay(self, *_, resume=True):
        if self.trim_saving:
            return
        self.trim_overlay.set_visible(False)
        self._trim_previewing = False
        if self.trim_seek_source:
            GLib.source_remove(self.trim_seek_source)
            self.trim_seek_source = 0
        if self.trim_player:
            self.trim_player.stop(wait=False)
            self.trim_player = None
        if resume and self._trim_was_playing and self.player:
            self.player.play(self._trim_restore_position)
            self.preview_play_button.set_label("Pause")

    def confirm_delete_path(self, path: Path):
        if self.player and self.player.playing:
            if self.stack.get_visible_child_name() == "preview" and path == self.preview_path:
                self.player.pause()
                self.preview_play_button.set_label("Play")
        dialog = Adw.AlertDialog.new("Delete this clip?",
                                     f"{path.name} will be permanently removed.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _dialog, response:
                       self._delete_clip(path) if response == "delete" else None)
        dialog.present(self.window)
        return dialog

    def _delete_clip(self, path: Path):
        try:
            path.unlink()
        except OSError as exc:
            Adw.AlertDialog.new("Could not delete clip", str(exc)).present(self.window)
            return
        if self.stack.get_visible_child_name() == "preview" and path == self.preview_path:
            self.navigate(self.preview_origin)
        self.populate_library()
        self.populate_recent()

    def copy_clip_path(self, path: Path):
        Gdk.Display.get_default().get_clipboard().set_text(str(path.resolve()))
        if self.stack.get_visible_child_name() == "dashboard":
            self.notice.set_text("Clip path copied.")

    def prompt_rename_clip(self, path: Path):
        if not path.is_file():
            self.populate_library()
            self.populate_recent()
            return
        dialog = Adw.AlertDialog.new("Rename clip", "The video file extension will stay the same.")
        entry = Gtk.Entry(text=path.stem)
        entry.set_activates_default(True)
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_margin_start(8)
        entry.set_margin_end(8)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _dialog, response:
                       self._rename_clip(path, entry.get_text()) if response == "rename" else None)
        dialog.present(self.window)
        entry.grab_focus()
        entry.select_region(0, -1)
        return dialog

    def _rename_clip(self, path: Path, name: str):
        try:
            renamed = rename_clip(path, name)
        except (ValueError, OSError) as exc:
            dialog = Adw.AlertDialog.new("Could not rename clip", str(exc))
            dialog.add_response("ok", "OK")
            dialog.present(self.window)
            return
        if getattr(self, "preview_path", None) == path:
            self.preview_path = renamed
            self.preview_title.set_text(renamed.stem)
        self.populate_library()
        self.populate_recent()

    def toggle_preview(self, *_):
        if not self.player:
            return
        if self.player.playing:
            self.preview_play_button.set_label("Play")
            self.player.pause()
        else:
            start = self.player.position
            if self.preview_duration and start >= self.preview_duration - .2:
                start = 0
            self.preview_play_button.set_label("Pause")
            self.player.play(start)

    def toggle_preview_fullscreen(self, *_):
        if not self.preview_fullscreen and self.stack.get_visible_child_name() != "preview":
            return
        self.preview_fullscreen = not self.preview_fullscreen
        fullscreen = self.preview_fullscreen
        self.sidebar.set_visible(not fullscreen)
        self.preview_back_button.set_visible(not fullscreen)
        self.preview_title.set_visible(not fullscreen)
        self.preview_actions.set_visible(not fullscreen)
        self.preview_content.set_margin_top(12 if fullscreen else 38)
        self.preview_content.set_margin_bottom(12 if fullscreen else 46)
        self.preview_content.set_margin_start(12 if fullscreen else 42)
        self.preview_content.set_margin_end(12 if fullscreen else 42)
        self.preview_content.set_vexpand(fullscreen)
        self.preview_fullscreen_button.set_child(icon("minimize", 18) if fullscreen else icon("maximize", 18))
        self.preview_fullscreen_button.set_tooltip_text("Exit fullscreen" if fullscreen else "Enter fullscreen")
        if fullscreen:
            self.window.add_css_class("preview-fullscreen")
            self.window.fullscreen()
        else:
            self.window.remove_css_class("preview-fullscreen")
            self.window.unfullscreen()

    def _begin_seek(self):
        if not self.player:
            return
        if self.seek_pending:
            self.seek_waiting_frame = False
            if self.player.playing:
                self.seek_resume = True
                self.player.pause()
                self.preview_play_button.set_label("Play")
            return
        self.seek_resume = self.player.playing
        self.seek_pending = True
        self.seek_waiting_frame = False
        if self.seek_resume:
            self.player.pause()
            self.preview_play_button.set_label("Play")

    def _commit_seek(self):
        self.seek_source = 0
        if not self.player:
            self.seek_pending = False
            return False
        position = self.preview_seek.get_value()
        self.seek_target = position
        self.seek_waiting_frame = True
        if self.seek_resume:
            self.player.play(position)
            self.preview_play_button.set_label("Pause")
        else:
            self.player.seek(position)
            self.preview_play_button.set_label("Play")
        return False

    def _seek_changed(self, scale):
        if not self.player:
            return
        self._begin_seek()
        self.seek_target = scale.get_value()
        self.preview_time.set_text(
            f"{self._time_text(self.seek_target)} / {self._time_text(self.preview_duration)}")
        if self.seek_source:
            GLib.source_remove(self.seek_source)
        self.seek_source = GLib.timeout_add(180, self._commit_seek)

    def open_path(self, path):
        try:
            Gio.AppInfo.launch_default_for_uri(Path(path).expanduser().resolve().as_uri(), None)
        except GLib.Error as exc:
            self.notice.set_text(str(exc))
