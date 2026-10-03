import unittest
import threading
import io
import subprocess
from pathlib import Path
from unittest.mock import patch

from clipdeck.player import ClipPlayer, FRAME_BYTES


class FakeProcess:
    def __init__(self):
        self.running = True
        self.terminated = False
        self.waited = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        self.waited = True
        return 0


class PlayerTests(unittest.TestCase):
    def test_seeking_to_end_uses_last_available_frame(self):
        frames = []
        player = ClipPlayer(Path("/tmp/clip.mkv"), lambda _frame, position: frames.append(position),
                            lambda: None, lambda *_: None)
        responses = [subprocess.CompletedProcess([], 0, b"", b""),
                     subprocess.CompletedProcess([], 0, b"\0" * FRAME_BYTES, b"")]
        with patch("clipdeck.player.subprocess.run", side_effect=responses) as run, \
             patch("clipdeck.player.GLib.idle_add", side_effect=lambda fn, *args: fn(*args)):
            player._still_frame(player.generation, 3.0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(frames, [2.75])

    def test_seek_starts_new_decoder_while_old_cleanup_finishes(self):
        release = threading.Event()
        decoder_started = threading.Event()

        class EmptyVideo(FakeProcess):
            def __init__(self):
                super().__init__()
                self.stdout = io.BytesIO()

        player = ClipPlayer(Path("/tmp/clip.mkv"), lambda *_: None,
                            lambda: None, lambda *_: None)
        player._cleanup_thread = threading.Thread(target=lambda: release.wait(1), daemon=True)
        player._cleanup_thread.start()
        try:
            def start_video(*_args, **_kwargs):
                decoder_started.set()
                return EmptyVideo()
            with patch("clipdeck.player.subprocess.Popen", side_effect=start_video):
                player.play(5)
                self.assertTrue(decoder_started.wait(.3))
        finally:
            release.set()
            player.stop()

    def test_pause_does_not_wait_for_process_cleanup_on_ui_thread(self):
        waiting = threading.Event()
        release = threading.Event()

        class SlowProcess(FakeProcess):
            def wait(self, timeout=None):
                waiting.set()
                release.wait(1)
                self.waited = True
                return 0

        player = ClipPlayer(Path("/tmp/clip.mkv"), lambda *_: None,
                            lambda: None, lambda *_: None)
        process = SlowProcess()
        player.audio_process = process
        try:
            player.pause()
            self.assertTrue(waiting.wait(1))
            self.assertFalse(process.waited)
            self.assertFalse(player.playing)
        finally:
            release.set()
            player.stop()

    def test_stop_reaps_video_and_audio_before_next_playback(self):
        player = ClipPlayer(Path("/tmp/clip.mkv"), lambda *_: None,
                            lambda: None, lambda *_: None)
        video = FakeProcess()
        audio = FakeProcess()
        player.video_process = video
        player.audio_process = audio
        player.playing = True
        player.stop()
        self.assertTrue(video.terminated and audio.terminated)
        self.assertTrue(video.waited and audio.waited)
        self.assertIsNone(player.video_process)
        self.assertIsNone(player.audio_process)
        self.assertFalse(player.playing)


if __name__ == "__main__":
    unittest.main()
