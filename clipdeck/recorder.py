"""Own and control a GPU Screen Recorder replay process through its CLI/IPC."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import fcntl
from pathlib import Path

from .config import Settings
from .audio_filter import AudioFilterError, FILTER_SOURCE, ensure_filtered_source, remove_filtered_source
from .media import compress_to_limit
from .runtime import ensure_private_runtime_directory


class RecorderError(Exception):
    pass


def _device_argument(device: str) -> str:
    if device in ("default_output", "default_input"):
        return device
    return "device:" + device


def list_monitors() -> list[tuple[str, str]]:
    try:
        result = subprocess.run(["gpu-screen-recorder", "--list-monitors"],
                                capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecorderError(f"Could not list displays: {exc}") from exc
    if result.returncode != 0:
        raise RecorderError(result.stderr.strip() or "Could not list displays.")
    return [(name.strip(), resolution.strip()) for line in result.stdout.splitlines()
            if "|" in line for name, resolution in [line.split("|", 1)] if name.strip()]


def list_audio_devices() -> list[tuple[str, str]]:
    try:
        result = subprocess.run(["gpu-screen-recorder", "--list-audio-devices"],
                                capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecorderError(f"Could not list audio devices: {exc}") from exc
    if result.returncode != 0:
        raise RecorderError(result.stderr.strip() or "Could not list audio devices.")
    return [(name.strip(), description.strip()) for line in result.stdout.splitlines()
            if "|" in line for name, description in [line.split("|", 1)] if name.strip()]


def runtime_dir() -> Path:
    root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/clipdeck-{os.getuid()}"))
    return root / "clipdeck"


class Recorder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = runtime_dir()
        self.socket = self.runtime / "recorder.sock"
        self.state_file = self.runtime / "state.json"

    def _ensure_runtime(self) -> None:
        try:
            ensure_private_runtime_directory(self.runtime)
        except OSError as exc:
            raise RecorderError(str(exc)) from exc

    def _cli(self, *args: str, timeout: int = 30) -> str:
        if not shutil.which("gsr-cli"):
            raise RecorderError("gsr-cli is missing. Install gpu-screen-recorder.")
        try:
            result = subprocess.run(["gsr-cli", "-ipc", str(self.socket), *args],
                                    capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RecorderError(f"Could not control the recorder: {exc}") from exc
        if result.returncode != 0:
            raise RecorderError((result.stderr or result.stdout).strip() or "The recorder reported an error.")
        return result.stdout.strip()

    def _is_running(self) -> bool:
        if not shutil.which("gsr-cli"):
            return False
        try:
            return self._cli("status", timeout=3).strip() == "running"
        except RecorderError:
            return False

    def _read_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_state(self, recording: bool) -> None:
        self._ensure_runtime()
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"recording": recording}), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.state_file)

    def status(self) -> dict[str, bool]:
        running = self._is_running()
        return {"replay": running, "record": running and bool(self._read_state().get("recording"))}

    def _start_command(self) -> list[str]:
        self.settings.validate()
        directory = str(Path(self.settings.clips_dir).expanduser().resolve())
        command = ["gpu-screen-recorder", "-w", self.settings.source.strip(),
                   "-f", str(self.settings.fps), "-c", "mkv", "-r", str(self.settings.duration),
                   "-replay-storage", "ram", "-bm", "cbr", "-q", "12000",
                   "-o", directory, "-ro", directory, "-ipc", str(self.socket)]
        audio = []
        if self.settings.desktop_audio:
            audio.append(_device_argument(self.settings.audio_output))
        if self.settings.microphone:
            microphone = FILTER_SOURCE if self.settings.noise_suppression else self.settings.audio_input
            audio.append(_device_argument(microphone))
        if audio:
            command.extend(["-a", "|".join(audio)])
        return command

    def start(self) -> None:
        if not shutil.which("gpu-screen-recorder"):
            raise RecorderError("gpu-screen-recorder is missing. Install it to capture clips.")
        self._ensure_runtime()
        with (self.runtime / "start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self._is_running():
                return
            if self.settings.microphone and self.settings.noise_suppression:
                try:
                    ensure_filtered_source(self.settings.audio_input)
                except AudioFilterError as exc:
                    raise RecorderError(f"Microphone noise suppression could not start: {exc}") from exc
            Path(self.settings.clips_dir).expanduser().mkdir(parents=True, exist_ok=True)
            log_path = self.runtime / "recorder.log"
            with log_path.open("ab") as log:
                process = subprocess.Popen(self._start_command(), stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=log, start_new_session=True, close_fds=True)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if self._is_running():
                    self._write_state(False)
                    return
                if process.poll() is not None:
                    details = log_path.read_text(errors="replace")[-1800:].strip()
                    raise RecorderError("Capture could not start. " + details)
                time.sleep(0.2)
            process.terminate()
            raise RecorderError("Capture did not respond within 12 seconds. Check the log: " + str(log_path))

    def stop(self) -> None:
        if not self._is_running():
            try:
                remove_filtered_source()
            except AudioFilterError:
                pass
            return
        if self._read_state().get("recording"):
            self.stop_record()
        self._cli("stop", timeout=30)
        deadline = time.monotonic() + 8
        while self._is_running() and time.monotonic() < deadline:
            time.sleep(0.1)
        if self._is_running():
            raise RecorderError("Capture did not stop within eight seconds.")
        self._write_state(False)
        try:
            remove_filtered_source()
        except AudioFilterError:
            pass

    def save_replay(self, on_saved=None) -> str:
        if not self._is_running():
            raise RecorderError("Capture is starting. Try saving a clip in a few seconds.")
        path = self._cli("save-replay", str(self.settings.duration), timeout=90)
        if on_saved:
            on_saved(path)
        try:
            return str(compress_to_limit(Path(path), self.settings.max_clip_mb))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            raise RecorderError(str(exc)) from exc

    def start_record(self) -> None:
        if not self._is_running():
            self.start()
        self._cli("start-replay-recording", timeout=10)
        self._write_state(True)

    def stop_record(self) -> str:
        if not self._is_running() or not self._read_state().get("recording"):
            raise RecorderError("No recording is in progress.")
        path = self._cli("stop-replay-recording", timeout=90)
        self._write_state(False)
        return path

    def toggle_record(self) -> str | None:
        if self.status()["record"]:
            return self.stop_record()
        self.start_record()
        return None
