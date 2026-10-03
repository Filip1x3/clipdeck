"""Register global shortcuts with the current desktop's shortcut manager."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path


ACTIONS = {"save": "--save-replay", "record": "--toggle-recording"}
MODMASKS = {"SHIFT": 1, "CTRL": 4, "ALT": 8, "SUPER": 64}
DESKTOP_SCHEMAS = {
    "gnome": ("org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings",
              "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding",
              "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/", False),
    "cinnamon": ("org.cinnamon.desktop.keybindings", "custom-list",
                 "org.cinnamon.desktop.keybindings.custom-keybinding",
                 "/org/cinnamon/desktop/keybindings/custom-keybindings/", True),
}
ACTION_NAMES = {"save": "Clipdeck: Save a clip", "record": "Clipdeck: Start / stop recording"}


class HotkeyError(Exception):
    pass


def _paths() -> tuple[Path, Path, Path]:
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config / "clipdeck/hotkeys.json", config / "caelestia/hypr-user.lua", config / "caelestia/clipdeck-binds.lua"


def load_hotkeys() -> dict[str, str]:
    try:
        data = json.loads(_paths()[0].read_text(encoding="utf-8"))
        return {key: str(data[key]) for key in ACTIONS if data.get(key)}
    except (OSError, ValueError, TypeError):
        return {}


def parse_combo(combo: str) -> tuple[int, str]:
    parts = [part.strip().upper() for part in combo.split("+")]
    function_key = bool(re.fullmatch(r"F(?:[1-9]|1\d|2[0-4])", parts[-1]))
    if (not parts[-1] or (len(parts) < 2 and not function_key)
            or len(set(parts[:-1])) != len(parts[:-1])):
        raise HotkeyError("Use F1–F24 or a modifier with a key, such as Ctrl + Alt + F9.")
    if any(part not in MODMASKS for part in parts[:-1]) or not re.fullmatch(r"[A-Z0-9_]+", parts[-1]):
        raise HotkeyError("This key combination is not supported.")
    return sum(MODMASKS[part] for part in parts[:-1]), parts[-1]


def _check_conflict(combo: str, previous: str | None) -> None:
    if combo == previous or not shutil.which("hyprctl") or not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return
    mask, key = parse_combo(combo)
    try:
        result = subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True, timeout=5)
        binds = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return
    for bind in binds:
        if bind.get("submap") == "" and bind.get("modmask") == mask and str(bind.get("key", "")).upper() == key:
            raise HotkeyError("That shortcut is already used by Hyprland. Choose another one.")


def _desktop() -> str | None:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return None
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "cinnamon" in current:
        return "cinnamon"
    if "gnome" in current:
        return "gnome"
    return None


def _gio():
    try:
        from gi.repository import Gio
    except ImportError as exc:
        raise HotkeyError("GSettings is unavailable. Install PyGObject to set global shortcuts.") from exc
    return Gio


def _accelerator(combo: str) -> str:
    _, key = parse_combo(combo)
    parts = {part.strip().upper() for part in combo.split("+")[:-1]}
    modifiers = "".join(f"<{tag}>" for part, tag in
                        (("CTRL", "Control"), ("ALT", "Alt"),
                         ("SHIFT", "Shift"), ("SUPER", "Super")) if part in parts)
    return modifiers + (key.lower() if len(key) == 1 else key)


def _accelerator_identity(accelerator: str) -> tuple[frozenset[str], str]:
    names = {name.lower() for name in re.findall(r"<([^>]+)>", accelerator)}
    names = {"control" if name in ("primary", "ctrl") else name for name in names}
    key = re.sub(r"<[^>]+>", "", accelerator).upper()
    return frozenset(names), key


def _shortcut_command(action: str) -> str:
    root = Path(__file__).resolve().parent.parent
    return shlex.quote(str(root / "run.sh")) + " " + ACTIONS[action]


def _owned_action(name: str, command: str) -> str | None:
    for action, title in ACTION_NAMES.items():
        if name == title and command.endswith(" " + ACTIONS[action]) and "run.sh" in command:
            return action
    return None


def _save_desktop_hotkeys(bindings: dict[str, str], desktop: str) -> None:
    Gio = _gio()
    parent_schema, list_key, child_schema, base_path, array_binding = DESKTOP_SCHEMAS[desktop]
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or any(source.lookup(schema, True) is None
                             for schema in (parent_schema, child_schema)):
        raise HotkeyError(f"{desktop.title()} shortcut settings are unavailable in this session.")

    parent = Gio.Settings.new(parent_schema)
    original = list(parent.get_strv(list_key))
    children = {}
    owned = {}
    for entry in original:
        if desktop == "gnome":
            if not entry.startswith(base_path) or not entry.endswith("/"):
                continue
            path = entry
        else:
            if entry == "__dummy__":
                continue
            path = base_path + entry + "/"
        child = Gio.Settings.new_with_path(child_schema, path)
        children[entry] = child
        action = _owned_action(child.get_string("name"), child.get_string("command"))
        if action:
            owned[action] = entry

    desired = {_accelerator(combo): action for action, combo in bindings.items()}
    conflicts = {_accelerator_identity(combo) for combo in desired}
    for entry, child in children.items():
        if entry in owned.values():
            continue
        existing = child.get_strv("binding") if array_binding else [child.get_string("binding")]
        if any(_accelerator_identity(value) in conflicts for value in existing if value):
            raise HotkeyError("That shortcut is already used by another custom shortcut.")

    # Allocate only unused slots; leave unrelated desktop shortcuts untouched.
    updated = list(original)
    for action in ACTIONS:
        if action in bindings and action not in owned:
            number = 0
            while True:
                name = f"custom{number}"
                entry = base_path + name + "/" if desktop == "gnome" else name
                if entry not in updated:
                    break
                number += 1
            owned[action] = entry
            updated.append(entry)
            children[entry] = Gio.Settings.new_with_path(child_schema, base_path + name + "/")

    for action, entry in owned.items():
        child = children[entry]
        if action in bindings:
            if not child.set_string("name", ACTION_NAMES[action]):
                raise HotkeyError("Could not write shortcut name to desktop settings.")
            if not child.set_string("command", _shortcut_command(action)):
                raise HotkeyError("Could not write shortcut command to desktop settings.")
            accel = _accelerator(bindings[action])
            saved = child.set_strv("binding", [accel]) if array_binding else child.set_string("binding", accel)
            if not saved:
                raise HotkeyError("Could not write shortcut to desktop settings.")
        else:
            updated.remove(entry)

    # Cinnamon only observes custom-list updates; remove/re-add owned entries to
    # force it to reload edited bindings. GNOME also accepts this refresh.
    if updated == original and bindings:
        temporarily_removed = [entry for entry in original if entry not in owned.values()]
        if not parent.set_strv(list_key, temporarily_removed):
            raise HotkeyError("Could not refresh desktop shortcuts.")
    if updated != original or bindings:
        if not parent.set_strv(list_key, updated):
            raise HotkeyError("Could not register desktop shortcuts.")
    for action, entry in owned.items():
        if action not in bindings:
            for key in ("binding", "command", "name"):
                children[entry].reset(key)


def save_hotkey(action: str, combo: str | None) -> None:
    if action not in ACTIONS:
        raise HotkeyError("Unknown shortcut action.")
    current = load_hotkeys()
    if combo:
        current[action] = combo
    else:
        current.pop(action, None)
    save_hotkeys(current)


def save_hotkeys(bindings: dict[str, str]) -> None:
    """Apply all shortcuts together so Settings can save or discard them."""
    current = load_hotkeys()
    if any(action not in ACTIONS for action in bindings):
        raise HotkeyError("Unknown shortcut action.")
    for action, combo in bindings.items():
        parse_combo(combo)
    if len({_accelerator_identity(_accelerator(combo)) for combo in bindings.values()}) != len(bindings):
        raise HotkeyError("The same shortcut cannot be used twice in Clipdeck.")

    desktop = _desktop()
    if desktop:
        _save_desktop_hotkeys(bindings, desktop)
    else:
        _, user_file, _ = _paths()
        if not user_file.exists():
            raise HotkeyError("Global shortcuts are supported on Hyprland/Caelestia, GNOME, and Cinnamon.")
        for action, combo in bindings.items():
            # A binding that already belongs to Clipdeck will be replaced on reload.
            previous = combo if combo in current.values() else current.get(action)
            _check_conflict(combo, previous)
        _save_hyprland_hotkeys(bindings)

    settings_file = _paths()[0]
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(settings_file)


def _save_hyprland_hotkeys(bindings: dict[str, str]) -> None:
    """Write bindings to the existing Caelestia Hyprland override."""

    _, user_file, binds_file = _paths()
    lines = ["-- Generated by Clipdeck. Change shortcuts in the app."]
    for key, argument in ACTIONS.items():
        if key in bindings:
            command = _shortcut_command(key)
            lines.append(f"hl.bind({json.dumps(bindings[key])}, hl.dsp.exec_cmd({json.dumps(command)}))")
    binds_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    marker = "-- Clipdeck shortcuts"
    user_content = user_file.read_text(encoding="utf-8")
    if marker not in user_content:
        backup = user_file.with_suffix(".lua.clipdeck-backup")
        if not backup.exists():
            shutil.copy2(user_file, backup)
        user_file.write_text(user_content.rstrip() + f"\n{marker}\ndofile({json.dumps(str(binds_file))})\n", encoding="utf-8")

    try:
        result = subprocess.run(["hyprctl", "reload"], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HotkeyError(f"Shortcut saved, but Hyprland could not reload: {exc}") from exc
    if result.returncode != 0:
        raise HotkeyError("Shortcut saved, but Hyprland could not reload: " + result.stderr.strip())
