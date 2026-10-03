import sys
import unittest
from unittest.mock import ANY, patch

from clipdeck import __main__, confirmation, feedback
from clipdeck.config import Settings
from clipdeck.recorder import RecorderError


class FeedbackTests(unittest.TestCase):
    def test_saved_clip_uses_nonblocking_overlay_process(self):
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1", "GDK_BACKEND": "x11"}), \
             patch("clipdeck.feedback.subprocess.Popen") as popen:
            feedback.clip_saved(Settings())
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [sys.executable, "-m", "clipdeck.confirmation",
                                   "--sound", "chime", "--theme", "default"])
        self.assertEqual(kwargs["env"]["GDK_BACKEND"], "wayland")

    def test_notification_and_sound_can_be_disabled_independently(self):
        with patch("clipdeck.feedback.subprocess.Popen") as popen:
            feedback.clip_saved(Settings(clip_notifications=False, clip_sound="chime"))
            self.assertIn("--no-overlay", popen.call_args.args[0])
            popen.reset_mock()
            feedback.clip_saved(Settings(clip_notifications=True, clip_sound="off"))
            self.assertNotIn("--no-overlay", popen.call_args.args[0])
            popen.reset_mock()
            feedback.clip_saved(Settings(clip_notifications=False, clip_sound="off"))
            popen.assert_not_called()

    def test_sound_preview_does_not_show_saved_clip_popup(self):
        with patch("clipdeck.feedback.subprocess.Popen") as popen:
            feedback.preview_sound("pulse")
        self.assertEqual(popen.call_args.args[0][-2:], ["pulse", "--no-overlay"])

    def test_notification_preview_uses_pending_theme_without_sound(self):
        with patch("clipdeck.feedback.subprocess.Popen") as popen:
            feedback.preview_notification("liquid_glass", False)
        self.assertEqual(popen.call_args.args[0][-4:],
                         ["--preview", "--theme", "liquid_glass", "--no-blur"])

    def test_sound_uses_paplay_when_pipewire_client_is_missing(self):
        with patch("clipdeck.confirmation.shutil.which",
                   side_effect=lambda name: None if name == "pw-play" else "/usr/bin/" + name), \
             patch("clipdeck.confirmation.subprocess.Popen") as popen:
            confirmation._play_sound("chime")
        self.assertEqual(popen.call_args.args[0][0], "paplay")

    def test_sound_retries_paplay_if_pipewire_server_is_unavailable(self):
        with patch("clipdeck.confirmation.shutil.which", return_value="/usr/bin/mock"), \
             patch("clipdeck.confirmation.subprocess.Popen") as popen, \
             patch("clipdeck.confirmation.threading.Thread") as thread:
            popen.return_value.wait.return_value = 1
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs["target"]()
            confirmation._play_sound("chime")
        self.assertEqual([call.args[0][0] for call in popen.call_args_list],
                         ["pw-play", "paplay"])

    def test_keybind_confirms_only_successful_save(self):
        with patch.object(sys, "argv", ["clipdeck", "--save-replay"]), \
             patch("clipdeck.__main__.Recorder") as recorder, \
             patch("clipdeck.__main__.clip_saved") as confirmed, \
             patch("builtins.print"):
            recorder.return_value.save_replay.return_value = "/tmp/saved.mkv"
            self.assertEqual(__main__.main(), 0)
            confirmed.assert_called_once_with(ANY)
            confirmed.reset_mock()
            recorder.return_value.save_replay.side_effect = RecorderError("Capture failed")
            self.assertEqual(__main__.main(), 1)
            confirmed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
