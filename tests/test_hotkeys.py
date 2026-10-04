import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipdeck import hotkeys


class FakeSettings:
    def __init__(self, values=None):
        self.values = values or {}
        self.history = []

    def get_strv(self, key):
        return list(self.values.get(key, []))

    def get_string(self, key):
        return self.values.get(key, "")

    def set_strv(self, key, value):
        self.values[key] = list(value)
        self.history.append((key, list(value)))
        return True

    def set_string(self, key, value):
        self.values[key] = value
        return True

    def reset(self, key):
        self.values.pop(key, None)


class FakeGio:
    def __init__(self):
        self.parent = FakeSettings()
        self.children = {}
        self.Settings = SimpleNamespace(new=lambda _schema: self.parent,
                                        new_with_path=self._child)
        self.SettingsSchemaSource = SimpleNamespace(get_default=lambda: self)

    def lookup(self, _schema, _recursive):
        return object()

    def _child(self, _schema, path):
        return self.children.setdefault(path, FakeSettings())


class HotkeyTests(unittest.TestCase):
    def test_modifier_order_and_case_do_not_allow_duplicate_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "GNOME",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys, "_gio") as gio:
                with self.assertRaisesRegex(hotkeys.HotkeyError, "same shortcut"):
                    hotkeys.save_hotkeys({"save": "CTRL + ALT + F8",
                                          "record": "alt + ctrl + f8"})
                gio.assert_not_called()

    def test_hyprland_session_takes_precedence_over_desktop_name(self):
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "GNOME",
                                    "HYPRLAND_INSTANCE_SIGNATURE": "test-instance"}):
            self.assertEqual(hotkeys._desktop(), "hyprland")

    def test_mixed_hyprland_and_gnome_desktop_uses_hyprland(self):
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "Hyprland:GNOME",
                                    "HYPRLAND_INSTANCE_SIGNATURE": ""}):
            self.assertEqual(hotkeys._desktop(), "hyprland")

    def test_gnome_shortcuts_preserve_unrelated_entries_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGio()
            base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
            other = base + "custom0/"
            fake.parent.values["custom-keybindings"] = [other]
            fake.children[other] = FakeSettings({"name": "Another app", "command": "other",
                                                  "binding": "<Control>F7"})
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys, "_gio", return_value=fake):
                hotkeys.save_hotkeys({"save": "CTRL + ALT + F9"})
                own = base + "custom1/"
                self.assertEqual(fake.parent.get_strv("custom-keybindings"), [other, own])
                self.assertEqual(fake.children[own].get_string("binding"), "<Control><Alt>F9")
                self.assertIn("--save-replay", fake.children[own].get_string("command"))
                hotkeys.save_hotkeys({"save": "F8"})
                self.assertEqual(fake.children[own].get_string("binding"), "F8")
                self.assertEqual(fake.parent.get_strv("custom-keybindings"), [other, own])
                hotkeys.save_hotkeys({})
                self.assertEqual(fake.parent.get_strv("custom-keybindings"), [other])
                self.assertEqual(fake.children[other].get_string("command"), "other")

    def test_cinnamon_shortcuts_use_array_bindings_and_preserve_dummy(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGio()
            fake.parent.values["custom-list"] = ["custom0", "__dummy__"]
            base = "/org/cinnamon/desktop/keybindings/custom-keybindings/"
            fake.children[base + "custom0/"] = FakeSettings({"name": "Another app",
                "command": "other", "binding": ["<Control>F7"]})
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "X-Cinnamon",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys, "_gio", return_value=fake):
                hotkeys.save_hotkeys({"record": "F8"})
                self.assertEqual(fake.parent.get_strv("custom-list"),
                                 ["custom0", "__dummy__", "custom1"])
                self.assertEqual(fake.children[base + "custom1/"].get_strv("binding"), ["F8"])
                hotkeys.save_hotkeys({"record": "CTRL + SHIFT + F9"})
                self.assertIn(("custom-list", ["custom0", "__dummy__"]), fake.parent.history)

    def test_gnome_rejects_conflict_with_existing_custom_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGio()
            base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
            other = base + "custom0/"
            fake.parent.values["custom-keybindings"] = [other]
            fake.children[other] = FakeSettings({"name": "Another app", "command": "other",
                                                  "binding": "<Alt><Control>F9"})
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "GNOME",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys, "_gio", return_value=fake):
                with self.assertRaises(hotkeys.HotkeyError):
                    hotkeys.save_hotkeys({"save": "CTRL + ALT + F9"})
                self.assertEqual(fake.parent.get_strv("custom-keybindings"), [other])

    def test_function_key_can_be_used_without_modifiers(self):
        self.assertEqual(hotkeys.parse_combo("F8"), (0, "F8"))
        with self.assertRaises(hotkeys.HotkeyError):
            hotkeys.parse_combo("K")

    def test_function_key_is_written_to_hyprland_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user = root / "caelestia" / "hypr-user.lua"
            user.parent.mkdir()
            user.write_text("", encoding="utf-8")
            (root / "hypr").mkdir()
            (root / "hypr" / "hyprland.lua").write_text('require("hypr-user")\n', encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "Hyprland",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}, clear=False), \
                 patch.object(hotkeys.subprocess, "run") as run, \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"):
                run.return_value.returncode = 0
                hotkeys.save_hotkeys({"save": "F8"})
                self.assertIn('hl.bind("F8"',
                              (root / "caelestia" / "clipdeck-binds.lua").read_text())

    def test_save_and_clear_shortcut_in_hyprland_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user = root / "caelestia" / "hypr-user.lua"
            user.parent.mkdir()
            user.write_text("-- existing user settings\n", encoding="utf-8")
            (root / "hypr").mkdir()
            (root / "hypr" / "hyprland.lua").write_text('require("hypr-user")\n', encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory, "XDG_CURRENT_DESKTOP": "Hyprland",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}, clear=False), \
                 patch.object(hotkeys.subprocess, "run") as run, \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"):
                run.return_value.returncode = 0
                run.return_value.stderr = ""
                hotkeys.save_hotkey("save", "CTRL + ALT + F9")
                self.assertEqual(hotkeys.load_hotkeys()["save"], "CTRL + ALT + F9")
                self.assertIn("CTRL + ALT + F9", (root / "caelestia" / "clipdeck-binds.lua").read_text())
                self.assertIn("-- Clipdeck shortcuts", user.read_text())
                self.assertEqual(user.read_text().count("-- Clipdeck shortcuts"), 1)
                self.assertTrue((root / "caelestia" / "hypr-user.lua.clipdeck-backup").exists())
                hotkeys.save_hotkey("save", None)
                self.assertEqual(json.loads((root / "clipdeck" / "hotkeys.json").read_text()), {})
                self.assertEqual(user.read_text().count("-- Clipdeck shortcuts"), 1)

    def test_rejects_duplicate_clipdeck_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user = root / "caelestia" / "hypr-user.lua"
            user.parent.mkdir()
            user.write_text("", encoding="utf-8")
            (root / "hypr").mkdir()
            (root / "hypr" / "hyprland.lua").write_text('require("hypr-user")\n', encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory, "XDG_CURRENT_DESKTOP": "Hyprland",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}, clear=False), \
                 patch.object(hotkeys.subprocess, "run") as run, \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"):
                run.return_value.returncode = 0
                hotkeys.save_hotkey("save", "CTRL + ALT + F9")
                with self.assertRaises(hotkeys.HotkeyError):
                    hotkeys.save_hotkey("record", "CTRL + ALT + F9")

    def test_save_hotkeys_applies_both_actions_in_one_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user = root / "caelestia" / "hypr-user.lua"
            user.parent.mkdir()
            user.write_text("", encoding="utf-8")
            (root / "hypr").mkdir()
            (root / "hypr" / "hyprland.lua").write_text('require("hypr-user")\n', encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "Hyprland",
                                        "HYPRLAND_INSTANCE_SIGNATURE": ""}, clear=False), \
                 patch.object(hotkeys.subprocess, "run") as run, \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"):
                run.return_value.returncode = 0
                hotkeys.save_hotkeys({"save": "CTRL + ALT + F9",
                                      "record": "CTRL + ALT + F10"})
                self.assertEqual(run.call_count, 1)
                self.assertEqual(hotkeys.load_hotkeys()["record"], "CTRL + ALT + F10")
                with self.assertRaises(hotkeys.HotkeyError):
                    hotkeys.save_hotkeys({"save": "CTRL + ALT + F9",
                                          "record": "CTRL + ALT + F9"})
                self.assertEqual(run.call_count, 1)

    def test_plain_hyprland_conf_registers_and_clears_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conf = root / "hypr" / "hyprland.conf"
            conf.parent.mkdir()
            conf.write_text("bind = SUPER, T, exec, terminal\n", encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "Hyprland", "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"), \
                 patch.object(hotkeys.subprocess, "run") as run:
                run.return_value.returncode = 0
                hotkeys.save_hotkeys({"save": "CTRL + ALT + F8"})
                binds = root / "hypr" / "clipdeck-binds.conf"
                self.assertIn("bind = CTRL_ALT, F8, exec,", binds.read_text())
                self.assertIn("source = " + str(binds), conf.read_text())
                self.assertEqual(conf.read_text().count("# Clipdeck shortcuts"), 1)
                hotkeys.save_hotkeys({"record": "F9"})
                self.assertNotIn("--save-replay", binds.read_text())
                self.assertIn("bind = , F9, exec,", binds.read_text())
                self.assertEqual(conf.read_text().count("# Clipdeck shortcuts"), 1)
                self.assertEqual(run.call_count, 2)

    def test_plain_hyprland_lua_registers_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lua = root / "hypr" / "hyprland.lua"
            lua.parent.mkdir()
            lua.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("terminal"))\n', encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "Hyprland", "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"), \
                 patch.object(hotkeys.subprocess, "run") as run:
                run.return_value.returncode = 0
                hotkeys.save_hotkeys({"save": "F8"})
                self.assertIn('hl.bind("F8"', (root / "hypr" / "clipdeck-binds.lua").read_text())
                self.assertIn('dofile(', lua.read_text())

    def test_failed_hyprland_reload_restores_config_and_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conf = root / "hypr" / "hyprland.conf"
            conf.parent.mkdir()
            conf.write_text("# existing settings\n", encoding="utf-8")
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory,
                                        "XDG_CURRENT_DESKTOP": "Hyprland", "HYPRLAND_INSTANCE_SIGNATURE": ""}), \
                 patch.object(hotkeys.shutil, "which", return_value="/usr/bin/hyprctl"), \
                 patch.object(hotkeys.subprocess, "run") as run:
                run.return_value.returncode = 1
                run.return_value.stderr = "invalid config"
                with self.assertRaisesRegex(hotkeys.HotkeyError, "invalid config"):
                    hotkeys.save_hotkeys({"save": "F8"})
                self.assertEqual(conf.read_text(), "# existing settings\n")
                self.assertFalse((root / "hypr" / "clipdeck-binds.conf").exists())
                self.assertFalse((root / "clipdeck" / "hotkeys.json").exists())
