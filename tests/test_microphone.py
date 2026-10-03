import io
import unittest
from unittest.mock import patch

from clipdeck.microphone import MicrophoneError, sample_level, test_microphone as run_microphone_test


class FakeProcess:
    def __init__(self, data=b"", returncode=0):
        self.stdout = io.BytesIO(data)
        self.stderr = io.BytesIO()
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        pass


class MicrophoneTests(unittest.TestCase):
    def test_level_changes_with_pcm_signal(self):
        self.assertEqual(sample_level(b"\x00\x00" * 4800), 0)
        self.assertGreater(sample_level((2000).to_bytes(2, "little", signed=True) * 4800), .5)

    def test_live_levels_and_playback(self):
        raw = (1000).to_bytes(2, "little", signed=True) * 48000
        processes = [FakeProcess(raw, 1), FakeProcess()]
        levels = []
        with patch("clipdeck.microphone.shutil.which", return_value="/usr/bin/mock"), \
             patch("clipdeck.microphone.subprocess.Popen", side_effect=processes):
            self.assertTrue(run_microphone_test("default_input", seconds=1,
                                                on_level=levels.append))
        self.assertGreater(len(levels), 1)
        self.assertGreater(max(levels), .05)

    def test_pulseaudio_tools_work_when_pipewire_tools_are_unavailable(self):
        raw = (1000).to_bytes(2, "little", signed=True) * 48000
        processes = [FakeProcess(raw, 1), FakeProcess()]
        with patch("clipdeck.microphone.shutil.which",
                   side_effect=lambda name: None if name.startswith("pw-") else "/usr/bin/" + name), \
             patch("clipdeck.microphone.subprocess.Popen", side_effect=processes) as popen:
            self.assertTrue(run_microphone_test("alsa_input.test", seconds=1))
        self.assertEqual(popen.call_args_list[0].args[0],
                         ["parec", "--raw", "--rate=48000", "--channels=1",
                          "--format=s16le", "--device=alsa_input.test"])
        self.assertEqual(popen.call_args_list[1].args[0][0], "paplay")

    def test_pulseaudio_retries_when_pipewire_client_cannot_record(self):
        raw = (1000).to_bytes(2, "little", signed=True) * 48000
        processes = [FakeProcess(b"", 1), FakeProcess(raw, 1), FakeProcess()]
        with patch("clipdeck.microphone.shutil.which", return_value="/usr/bin/mock"), \
             patch("clipdeck.microphone.subprocess.Popen", side_effect=processes) as popen:
            self.assertTrue(run_microphone_test("default_input", seconds=1))
        self.assertEqual([call.args[0][0] for call in popen.call_args_list],
                         ["pw-record", "parec", "paplay"])

    def test_missing_desktop_audio_tools_has_actionable_error(self):
        with patch("clipdeck.microphone.shutil.which", return_value=None):
            with self.assertRaisesRegex(MicrophoneError, "PipeWire.*PulseAudio"):
                run_microphone_test("default_input")
