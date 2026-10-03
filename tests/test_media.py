import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipdeck.media import compress_to_limit, recent_clips, rename_clip, trim_clip


class MediaTests(unittest.TestCase):
    def test_rename_keeps_extension_and_refuses_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "first.mkv"
            original.write_bytes(b"video")
            collision = folder / "taken.mkv"
            collision.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                rename_clip(original, "taken")
            self.assertEqual(collision.read_bytes(), b"keep")
            renamed = rename_clip(original, "  game highlight  ")
            self.assertEqual(renamed.name, "game highlight.mkv")
            self.assertEqual(renamed.read_bytes(), b"video")
            self.assertFalse(original.exists())

    def test_rename_rejects_invalid_names(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "clip.mp4"
            original.write_bytes(b"video")
            for name in ("", "..", "nested/name", "line\nbreak"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    rename_clip(original, name)
            self.assertTrue(original.exists())

    def test_recent_clips_returns_latest_four_videos(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for index in range(6):
                path = folder / f"clip-{index}.mkv"
                path.write_bytes(b"video")
                os.utime(path, (index + 100, index + 100))
            (folder / "note.txt").write_text("not a clip")
            self.assertEqual(
                [path.name for path in recent_clips(directory, 4)],
                ["clip-5.mkv", "clip-4.mkv", "clip-3.mkv", "clip-2.mkv"],
            )

    def test_trim_uses_private_output_and_never_overwrites_existing_name(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "game.mkv"
            source.write_bytes(b"original")
            existing = folder / "game trimmed.mkv"
            existing.write_bytes(b"keep")
            modes = []

            def fake_ffmpeg(command, **_kwargs):
                temporary = Path(command[-1])
                modes.append(temporary.stat().st_mode & 0o777)
                temporary.write_bytes(b"trimmed")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("clipdeck.media.subprocess.run", side_effect=fake_ffmpeg):
                result = trim_clip(source, 1, 2)

            self.assertEqual(modes, [0o600])
            self.assertEqual(existing.read_bytes(), b"keep")
            self.assertEqual(result.name, "game trimmed 2.mkv")
            self.assertEqual(result.read_bytes(), b"trimmed")
            self.assertEqual(source.read_bytes(), b"original")

    def test_compression_does_not_write_to_predictable_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "game.mkv"
            source.write_bytes(b"x" * (1024 * 1024 + 1))
            victim = folder / "other-file"
            victim.write_bytes(b"keep")
            old_name = folder / f".game.compress-{os.getpid()}-0.mkv"
            old_name.symlink_to(victim)
            modes = []

            def fake_process(command, **_kwargs):
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(command, 0, "3", "")
                temporary = Path(command[-1])
                modes.append(temporary.stat().st_mode & 0o777)
                temporary.write_bytes(b"compressed")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("clipdeck.media.subprocess.run", side_effect=fake_process):
                result = compress_to_limit(source, 1)

            self.assertEqual(modes, [0o600])
            self.assertEqual(result.read_bytes(), b"compressed")
            self.assertEqual(victim.read_bytes(), b"keep")
            self.assertTrue(old_name.is_symlink())
