"""Windowless FFmpeg video decoder with MPV audio for GTK previews."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from gi.repository import GLib


WIDTH = 1280
HEIGHT = 720
FPS = 30
FRAME_BYTES = WIDTH * HEIGHT * 3
VIDEO_FILTER = (
    f"fps={FPS},scale={WIDTH}:{HEIGHT}:flags=lanczos:force_original_aspect_ratio=decrease,"
    f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
)


def video_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=12, check=False,
        )
        return max(0.0, float(result.stdout.strip())) if result.returncode == 0 else 0.0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


class ClipPlayer:
    def __init__(self, path: Path, on_frame, on_finished, on_error):
        self.path = path
        self.on_frame = on_frame
        self.on_finished = on_finished
        self.on_error = on_error
        self.position = 0.0
        self.speed = 1.0
        self.playing = False
        self.generation = 0
        self.video_process = None
        self.audio_process = None
        self._cleanup_thread = None

    @staticmethod
    def _reap(processes):
        for process in processes:
            if process:
                try:
                    process.wait(timeout=0.4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.4)

    def stop(self, wait: bool = True):
        self.generation += 1
        self.playing = False
        processes = (self.video_process, self.audio_process)
        self.video_process = None
        self.audio_process = None
        for process in processes:
            if process and process.poll() is None:
                process.terminate()
        previous_cleanup = self._cleanup_thread
        if wait:
            if previous_cleanup:
                previous_cleanup.join(timeout=2)
            self._reap(processes)
            self._cleanup_thread = None
        elif any(processes):
            def cleanup():
                if previous_cleanup:
                    previous_cleanup.join(timeout=2)
                self._reap(processes)
            self._cleanup_thread = threading.Thread(target=cleanup, daemon=True)
            self._cleanup_thread.start()

    def pause(self):
        self.stop(wait=False)

    def set_speed(self, speed: float):
        if speed <= 0:
            raise ValueError("Playback speed must be positive.")
        self.speed = speed
        if self.playing:
            self.play(self.position)

    def play(self, position: float | None = None):
        start = self.position if position is None else max(0.0, position)
        self.stop(wait=False)
        self.position = start
        self.playing = True
        token = self.generation
        threading.Thread(target=self._decode, args=(token, start), daemon=True).start()

    def seek(self, position: float):
        position = max(0.0, position)
        if self.playing:
            self.play(position)
            return
        self.generation += 1
        self.position = position
        token = self.generation
        threading.Thread(target=self._still_frame, args=(token, position), daemon=True).start()

    def _command(self, position: float, one_frame: bool = False):
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(position),
                   "-i", str(self.path), "-an", "-vf", VIDEO_FILTER]
        if one_frame:
            command.extend(["-frames:v", "1"])
        command.extend(["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
        return command

    def _still_frame(self, token: int, position: float):
        try:
            result = subprocess.run(self._command(position, True), capture_output=True,
                                    timeout=12, check=False)
            shown_at = position
            if (result.returncode != 0 or len(result.stdout) < FRAME_BYTES) and position >= .25 \
                    and token == self.generation:
                shown_at = position - .25
                result = subprocess.run(self._command(shown_at, True), capture_output=True,
                                        timeout=12, check=False)
            if result.returncode == 0 and len(result.stdout) >= FRAME_BYTES:
                GLib.idle_add(self._deliver_frame, token, result.stdout[:FRAME_BYTES], shown_at, None)
            else:
                GLib.idle_add(self._finish, token)
        except (OSError, subprocess.TimeoutExpired):
            GLib.idle_add(self._finish, token)

    def _decode(self, token: int, start: float):
        video = None
        audio = None
        frame_index = 0
        speed = self.speed
        try:
            if token != self.generation:
                return
            video = subprocess.Popen(self._command(start), stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
            if token != self.generation:
                return
            self.video_process = video
            started = None
            while token == self.generation:
                frame = video.stdout.read(FRAME_BYTES)
                if len(frame) != FRAME_BYTES:
                    break
                if started is None:
                    started = time.monotonic()
                    if token == self.generation:
                        try:
                            audio = subprocess.Popen(
                                ["mpv", "--no-config", "--no-terminal", "--no-video",
                                 "--start=" + str(start), "--speed=" + str(speed),
                                 "--", str(self.path)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            )
                            if token != self.generation:
                                break
                            self.audio_process = audio
                        except OSError:
                            audio = None
                delay = started + frame_index / (FPS * speed) - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                if token != self.generation:
                    break
                acknowledged = threading.Event()
                GLib.idle_add(self._deliver_frame, token, frame,
                              start + frame_index / FPS, acknowledged)
                while token == self.generation and not acknowledged.wait(0.1):
                    pass
                frame_index += 1
            if token == self.generation:
                if frame_index:
                    GLib.idle_add(self._finish, token)
                else:
                    GLib.idle_add(self._error, token, "Could not decode this clip.")
        except OSError as exc:
            GLib.idle_add(self._error, token, str(exc))
        finally:
            for process in (video, audio):
                if process and process.poll() is None:
                    process.terminate()
                if process:
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
            if video and video.stdout:
                video.stdout.close()

    def _deliver_frame(self, token, frame, position, acknowledged):
        try:
            if token == self.generation:
                self.position = position
                self.on_frame(frame, position)
        finally:
            if acknowledged:
                acknowledged.set()
        return False

    def _finish(self, token):
        if token == self.generation:
            self.playing = False
            self.on_finished()
        return False

    def _error(self, token, message):
        if token == self.generation:
            self.playing = False
            self.on_error(message)
        return False
