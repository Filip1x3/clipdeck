"""Microphone loopback test with live PipeWire levels."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from .audio_filter import AudioFilterError, ensure_filtered_source


class MicrophoneError(Exception):
    pass


def _audio_commands(device: str, seconds: int) -> list[tuple[list[str], list[str]]]:
    """Return available raw PCM clients in preference order."""
    commands = []
    if shutil.which("pw-record") and shutil.which("pw-play"):
        record = ["pw-record", "--raw", "--rate", "48000", "--channels", "1",
                  "--format", "s16", "--sample-count", str(48000 * seconds)]
        if device != "default_input":
            record.extend(["--target", device])
        commands.append((record + ["-"], ["pw-play"]))
    if shutil.which("parec") and shutil.which("paplay"):
        record = ["parec", "--raw", "--rate=48000", "--channels=1", "--format=s16le"]
        if device != "default_input":
            record.append("--device=" + device)
        commands.append((record, ["paplay"]))
    if not commands:
        raise MicrophoneError("Microphone testing needs PipeWire (pw-record/pw-play) "
                              "or PulseAudio (parec/paplay) tools.")
    return commands


def sample_level(data: bytes) -> float:
    """Map 16-bit PCM RMS to a 0–1 meter level."""
    samples = array.array("h")
    samples.frombytes(data[:len(data) // 2 * 2])
    if not samples:
        return 0.0
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768
    decibels = 20 * math.log10(max(rms, 1e-6))
    return max(0.0, min(1.0, (decibels + 55) / 45))


def test_microphone(device: str, seconds: int = 5, on_playback=None,
                    on_level=None, stop_event: threading.Event | None = None,
                    noise_suppression: bool = False) -> bool:
    """Record the selected source, report live level, then play it back."""
    if noise_suppression:
        try:
            device = ensure_filtered_source(device)
        except AudioFilterError as exc:
            raise MicrophoneError(str(exc)) from exc
    commands = _audio_commands(device, seconds)
    stop_event = stop_event or threading.Event()
    with tempfile.TemporaryDirectory(prefix="clipdeck-mic-") as directory:
        path = Path(directory) / "microphone.wav"
        last_error = None
        for record_command, play_command in commands:
            try:
                recorder = subprocess.Popen(record_command, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
            except OSError as exc:
                last_error = exc
                continue
            chunks = []
            levels = []
            byte_count = 0
            started = time.monotonic()
            try:
                while byte_count < 48000 * seconds * 2 and time.monotonic() - started < seconds + 3:
                    if stop_event.is_set():
                        recorder.terminate()
                        break
                    chunk = recorder.stdout.read(9600)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    byte_count += len(chunk)
                    level = sample_level(chunk)
                    levels.append(level)
                    if on_level:
                        on_level(level)
            finally:
                if recorder.poll() is None:
                    recorder.terminate()
                try:
                    recorder.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder.wait(timeout=2)
                recorder.stdout.close()
                recorder.stderr.close()
            raw = b"".join(chunks)
            if len(raw) >= 48000 or stop_event.is_set():
                break
        else:
            detail = f": {last_error}" if last_error else "."
            raise MicrophoneError("The microphone recording was too short" + detail)
        if len(raw) < 48000:
            raise MicrophoneError("The microphone recording was too short.")
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(raw)
        signal = max(levels, default=0) > 0.05
        if on_playback:
            on_playback()
        try:
            player = subprocess.Popen([*play_command, str(path)], stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE)
        except OSError as exc:
            raise MicrophoneError(f"Could not play the microphone test: {exc}") from exc
        for level in levels:
            if on_level:
                on_level(level)
            if player.poll() is not None:
                break
            time.sleep(0.1)
        try:
            return_code = player.wait(timeout=3)
        except subprocess.TimeoutExpired:
            player.terminate()
            player.wait(timeout=2)
            raise MicrophoneError("Microphone playback did not finish.")
        if return_code != 0:
            raise MicrophoneError("Could not play the microphone test.")
        return signal
