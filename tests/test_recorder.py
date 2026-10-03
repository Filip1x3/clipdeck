import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from clipdeck.config import Settings
from clipdeck.recorder import Recorder, RecorderError, list_audio_devices, list_monitors


class RecorderTests(unittest.TestCase):
    def test_replay_command_uses_own_engine_and_settings(self):
        settings = Settings(duration=45, fps=120, source="DP-1", clips_dir="/tmp/clipdeck-clips",
                            desktop_audio=True, microphone=True)
        command = Recorder(settings)._start_command()
        self.assertEqual(command[0], "gpu-screen-recorder")
        self.assertEqual(command[command.index("-r") + 1], "45")
        self.assertEqual(command[command.index("-f") + 1], "120")
        self.assertEqual(command[command.index("-w") + 1], "DP-1")
        self.assertEqual(command[command.index("-ro") + 1], "/tmp/clipdeck-clips")
        self.assertEqual(command.count("-a"), 1)
        self.assertEqual(command[command.index("-a") + 1], "default_output|device:clipdeck_noise_suppressed")

    def test_status_reads_recording_flag_only_when_engine_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("clipdeck.recorder.runtime_dir", return_value=Path(directory)):
                recorder = Recorder(Settings())
                recorder._write_state(True)
                with patch.object(recorder, "_is_running", return_value=True):
                    self.assertEqual(recorder.status(), {"replay": True, "record": True})
                with patch.object(recorder, "_is_running", return_value=False):
                    self.assertEqual(recorder.status(), {"replay": False, "record": False})

    def test_save_replay_requires_buffer(self):
        recorder = Recorder(Settings())
        with patch.object(recorder, "_is_running", return_value=False):
            with self.assertRaisesRegex(RecorderError, "Capture"):
                recorder.save_replay()

    def test_save_confirmation_happens_before_compression(self):
        recorder = Recorder(Settings())
        events = []
        with patch.object(recorder, "_is_running", return_value=True), \
             patch.object(recorder, "_cli", return_value="/tmp/saved.mkv"), \
             patch("clipdeck.recorder.compress_to_limit", side_effect=lambda *_: events.append("compress") or Path("/tmp/saved.mkv")):
            recorder.save_replay(on_saved=lambda _path: events.append("saved"))
        self.assertEqual(events, ["saved", "compress"])

    def test_stop_waits_for_recorder_to_exit_before_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("clipdeck.recorder.runtime_dir", return_value=Path(directory)):
                recorder = Recorder(Settings())
                with patch.object(recorder, "_is_running", side_effect=[True, True, False, False]), \
                     patch.object(recorder, "_cli", return_value=""), \
                     patch("clipdeck.recorder.time.sleep") as sleep, \
                     patch("clipdeck.recorder.remove_filtered_source"):
                    recorder.stop()
                sleep.assert_called_once()

    def test_specific_audio_devices_are_mixed(self):
        settings = Settings(audio_output="alsa_output.test.monitor", audio_input="alsa_input.test", microphone=True)
        command = Recorder(settings)._start_command()
        self.assertEqual(command[command.index("-a") + 1],
                         "device:alsa_output.test.monitor|device:clipdeck_noise_suppressed")

    def test_microphone_filter_can_be_disabled(self):
        settings = Settings(audio_input="alsa_input.test", microphone=True, noise_suppression=False)
        command = Recorder(settings)._start_command()
        self.assertEqual(command[command.index("-a") + 1], "default_output|device:alsa_input.test")

    def test_display_and_audio_lists(self):
        with patch("clipdeck.recorder.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, "DP-2|2560x1440\n", ""),
            subprocess.CompletedProcess([], 0, "default_input|Default input\nalsa_input.test|USB Microphone\n", ""),
        ]):
            self.assertEqual(list_monitors(), [("DP-2", "2560x1440")])
            self.assertEqual(list_audio_devices()[1], ("alsa_input.test", "USB Microphone"))


if __name__ == "__main__":
    unittest.main()
