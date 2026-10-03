"""Installer checks without invoking a package manager or changing user files."""

import json
import shlex
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import install


class InstallerTests(TestCase):
    def test_desktop_launcher_uses_current_checkout_even_with_spaces(self):
        with patch.object(install, "ROOT", Path("/tmp/My Clipdeck")):
            entry = install.render_desktop(Path("clipdeck.desktop"))
        self.assertIn('Exec="/tmp/My Clipdeck/run.sh"', entry)
        self.assertIn("Icon=/tmp/My Clipdeck/assets/clipdeck.svg", entry)
        self.assertNotIn("/home/filip", entry)

    def test_desktop_launcher_rejects_newline_in_checkout_path(self):
        with patch.object(install, "ROOT", Path("/tmp/Clipdeck\nExec=evil")):
            with self.assertRaisesRegex(RuntimeError, "control characters"):
                install.render_desktop(Path("clipdeck.desktop"))

    def test_apt_does_not_run_unpinned_upstream_source(self):
        events = []
        with (patch.object(install.os, "geteuid", return_value=1000),
              patch.object(install, "distro_family", return_value="apt"),
              patch.object(install, "install_dependencies",
                           side_effect=lambda: events.append("deps")),
              patch.object(install, "missing_commands",
                           return_value=["gpu-screen-recorder", "gsr-cli"]),
              patch.object(install, "missing_gi_modules", return_value=[]),
              patch.object(install, "install_desktop") as desktop):
            self.assertEqual(install.main([]), 1)
        self.assertEqual(events, ["deps"])
        desktop.assert_not_called()

    def test_missing_dependencies_do_not_install_launcher(self):
        with (patch.object(install.os, "geteuid", return_value=1000),
              patch.object(install, "missing_commands", return_value=["gsr-cli"]),
              patch.object(install, "missing_gi_modules", return_value=[]),
              patch.object(install, "install_desktop") as desktop):
            self.assertEqual(install.main(["--no-deps"]), 1)
            desktop.assert_not_called()

    def test_hyprland_autostart_quotes_checkout_path_for_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            execs = config_home / "hypr/hyprland/execs.lua"
            execs.parent.mkdir(parents=True)
            execs.write_text('hl.on("hyprland.start", function()\nend)\n', encoding="utf-8")
            checkout = Path(directory) / "Clipdeck $(touch hacked) with spaces"
            with (patch.object(install, "CONFIG_HOME", config_home),
                  patch.object(install, "ROOT", checkout)):
                install.install_autostart()
            line = next(line for line in execs.read_text(encoding="utf-8").splitlines()
                        if "hl.exec_cmd(" in line)
            command = json.loads(line.split("hl.exec_cmd(", 1)[1].rsplit(")", 1)[0])
            self.assertEqual(shlex.split(command),
                             [str(checkout / "run.sh"), "--ensure-capture"])
            self.assertEqual(command,
                             shlex.quote(str(checkout / "run.sh")) + " --ensure-capture")
            self.assertTrue(execs.with_suffix(".lua.clipdeck-backup").exists())
