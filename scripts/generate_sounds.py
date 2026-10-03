"""Recreate Clipdeck's original, short notification sounds using Python only.

Both WAV files are synthesized from sine waves; no sampled or third-party
audio is used. Run this script after changing the tone definitions below.
"""

from __future__ import annotations

import argparse
import io
import math
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "assets" / "sounds"
SAMPLE_RATE = 48_000


def tone(t: float, start: float, frequency: float, decay: float) -> float:
    elapsed = t - start
    if elapsed < 0:
        return 0.0
    envelope = min(1.0, elapsed / 0.007) * math.exp(-decay * elapsed)
    fundamental = math.sin(2 * math.pi * frequency * elapsed)
    overtone = 0.12 * math.sin(4 * math.pi * frequency * elapsed)
    return envelope * (fundamental + overtone)


def make_wav(kind: str) -> bytes:
    duration = 0.32 if kind == "clip-saved" else 0.27
    samples = []
    for index in range(round(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        if kind == "clip-saved":
            value = 0.26 * tone(t, 0.0, 880.0, 13.0)
            value += 0.25 * tone(t, 0.065, 1174.66, 13.0)
        elif kind == "clip-pulse":
            value = 0.28 * tone(t, 0.0, 740.0, 20.0)
            value += 0.13 * tone(t, 0.072, 880.0, 20.0)
        else:
            raise ValueError(f"Unknown sound: {kind}")
        samples.append(struct.pack("<h", round(max(-1.0, min(1.0, value)) * 32767)))

    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(b"".join(samples))
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Clipdeck notification sounds")
    parser.add_argument("--check", action="store_true", help="check that committed WAVs match")
    args = parser.parse_args()
    for kind in ("clip-saved", "clip-pulse"):
        path = SOUNDS / f"{kind}.wav"
        generated = make_wav(kind)
        if args.check:
            if not path.exists() or path.read_bytes() != generated:
                print(f"Out of date: {path}")
                return 1
        else:
            path.write_bytes(generated)
            print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
