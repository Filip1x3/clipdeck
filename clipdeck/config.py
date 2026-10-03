from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "clipdeck"
CONFIG_FILE = CONFIG_DIR / "settings.json"


@dataclass
class Settings:
    duration: int = 30
    clips_dir: str = str(Path.home() / "Videos")
    source: str = "screen"
    fps: int = 60
    desktop_audio: bool = True
    microphone: bool = False
    noise_suppression: bool = True
    audio_output: str = "default_output"
    audio_input: str = "default_input"
    theme: str = "default"
    blur_enabled: bool = True
    clip_notifications: bool = True
    clip_sound: str = "chime"
    max_clip_mb: int = 150

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            values = {key: data[key] for key in cls.__dataclass_fields__ if key in data}
            settings = cls(**values)
            settings.validate()
            return settings
        except (OSError, ValueError, TypeError, KeyError):
            return cls()

    def validate(self) -> None:
        if not 10 <= int(self.duration) <= 3600:
            raise ValueError("Clip length must be between 10 and 3600 seconds.")
        if not 15 <= int(self.fps) <= 240:
            raise ValueError("Frame rate must be between 15 and 240 FPS.")
        if not self.source.strip() or self.source.startswith("-"):
            raise ValueError("Choose a valid display.")
        if not self.clips_dir.strip():
            raise ValueError("Choose a folder for your clips.")
        if self.desktop_audio and not self.audio_output.strip():
            raise ValueError("Choose a desktop audio device.")
        if self.microphone and not self.audio_input.strip():
            raise ValueError("Choose a microphone.")
        if self.theme not in ("default", "liquid_glass"):
            raise ValueError("Choose a valid theme.")
        if self.clip_sound not in ("chime", "pulse", "off"):
            raise ValueError("Choose a valid clip sound.")
        if not 1 <= int(self.max_clip_mb) <= 2000:
            raise ValueError("Maximum clip size must be between 1 and 2000 MB.")

    def save(self) -> None:
        self.validate()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(CONFIG_FILE, 0o600)
