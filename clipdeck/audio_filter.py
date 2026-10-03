"""Clipdeck-only PipeWire microphone processing through the PulseAudio API."""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import time
from pathlib import Path

from .runtime import ensure_private_runtime_directory


FILTER_SOURCE = "clipdeck_noise_suppressed"
FILTER_SINK = "clipdeck_noise_suppressed_sink"
_MODULE = "module-echo-cancel"
_AEC_ARGS = ("webrtc.noise_suppression=true "
             "webrtc.high_pass_filter=true "
             "webrtc.transient_suppression=true "
             "webrtc.gain_control=false")


class AudioFilterError(Exception):
    pass


def _pactl(*args: str) -> str:
    if not shutil.which("pactl"):
        raise AudioFilterError("Microphone filtering needs pactl (libpulse).")
    try:
        result = subprocess.run(["pactl", *args], capture_output=True, text=True,
                                check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioFilterError(f"Could not reach PipeWire: {exc}") from exc
    if result.returncode:
        raise AudioFilterError(result.stderr.strip() or "PipeWire microphone filtering failed.")
    return result.stdout.strip()


def _module_ids() -> list[tuple[int, str]]:
    modules = []
    for line in _pactl("list", "short", "modules").splitlines():
        parts = line.split("\t")
        if (len(parts) >= 3 and parts[1] == _MODULE
                and f"source_name={FILTER_SOURCE}" in parts[2].split()):
            modules.append((int(parts[0]), parts[2]))
    return modules


def _source_exists() -> bool:
    return any(parts[1] == FILTER_SOURCE
               for line in _pactl("list", "short", "sources").splitlines()
               if len(parts := line.split("\t")) > 1)


def _lock_path() -> Path:
    root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/clipdeck-{os.getuid()}")) / "clipdeck"
    try:
        ensure_private_runtime_directory(root)
    except OSError as exc:
        raise AudioFilterError(str(exc)) from exc
    return root / "microphone-filter.lock"


def ensure_filtered_source(device: str) -> str:
    """Expose a private filtered source; leave the system default microphone alone."""
    source = _pactl("get-default-source") if device == "default_input" else device
    if not source or source == FILTER_SOURCE or source.endswith(".monitor"):
        raise AudioFilterError("Select a physical microphone for noise suppression.")
    with _lock_path().open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        modules = _module_ids()
        expected = f"source_master={source}"
        if len(modules) == 1 and expected in modules[0][1].split() and _source_exists():
            return FILTER_SOURCE
        for module_id, _ in modules:
            _pactl("unload-module", str(module_id))
        _pactl("load-module", _MODULE,
               f"source_name={FILTER_SOURCE}", f"source_master={source}",
               f"sink_name={FILTER_SINK}", "aec_method=webrtc", f"aec_args={_AEC_ARGS}")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if _source_exists():
                return FILTER_SOURCE
            time.sleep(0.1)
        raise AudioFilterError("PipeWire did not create the filtered microphone.")


def remove_filtered_source() -> None:
    """Remove only Clipdeck's virtual microphone when capture stops."""
    if not shutil.which("pactl"):
        return
    with _lock_path().open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for module_id, _ in _module_ids():
            _pactl("unload-module", str(module_id))
