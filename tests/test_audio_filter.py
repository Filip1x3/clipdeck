import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipdeck.audio_filter import FILTER_SOURCE, AudioFilterError, ensure_filtered_source


class AudioFilterTests(unittest.TestCase):
    def test_creates_filter_for_selected_microphone(self):
        calls = []
        def pactl(*args):
            calls.append(args)
            if args == ("list", "short", "modules"):
                return ""
            if args == ("list", "short", "sources"):
                return f"4\t{FILTER_SOURCE}\tPipeWire\n"
            return "123"
        with tempfile.TemporaryDirectory() as directory, \
             patch("clipdeck.audio_filter._lock_path", return_value=Path(directory) / "lock"), \
             patch("clipdeck.audio_filter._pactl", side_effect=pactl):
            self.assertEqual(ensure_filtered_source("alsa_input.usb-mic"), FILTER_SOURCE)
        load = next(args for args in calls if args[0] == "load-module")
        self.assertIn("source_master=alsa_input.usb-mic", load)
        self.assertTrue(any("webrtc.transient_suppression=true" in arg for arg in load))

    def test_reuses_filter_for_same_microphone(self):
        calls = []
        def pactl(*args):
            calls.append(args)
            if args == ("list", "short", "modules"):
                return (f"123\tmodule-echo-cancel\tsource_name={FILTER_SOURCE} "
                        "source_master=alsa_input.usb-mic\n")
            if args == ("list", "short", "sources"):
                return f"4\t{FILTER_SOURCE}\tPipeWire\n"
            return ""
        with tempfile.TemporaryDirectory() as directory, \
             patch("clipdeck.audio_filter._lock_path", return_value=Path(directory) / "lock"), \
             patch("clipdeck.audio_filter._pactl", side_effect=pactl):
            self.assertEqual(ensure_filtered_source("alsa_input.usb-mic"), FILTER_SOURCE)
        self.assertFalse(any(args[0] in ("load-module", "unload-module") for args in calls))

    def test_rejects_virtual_source_as_input(self):
        with patch("clipdeck.audio_filter._pactl"):
            with self.assertRaises(AudioFilterError):
                ensure_filtered_source(FILTER_SOURCE)


if __name__ == "__main__":
    unittest.main()
