"""Clip discovery and preview metadata."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


EXTENSIONS = {".mkv", ".mp4", ".mov", ".webm"}


def _temporary_video(folder: Path, stem: str, suffix: str) -> Path:
    """Reserve a private output name before handing it to FFmpeg."""
    short_id = hashlib.sha256(os.fsencode(stem)).hexdigest()[:12]
    descriptor, name = tempfile.mkstemp(prefix=f".clipdeck-{short_id}.", suffix=suffix, dir=folder)
    os.close(descriptor)
    return Path(name)


def _rename_noreplace(source: Path, target: Path) -> None:
    """Atomically publish a file on Linux without replacing an existing name."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint)
        renameat2.restype = ctypes.c_int
        at_fdcwd = -100
        rename_noreplace = 1
        if renameat2(at_fdcwd, os.fsencode(source), at_fdcwd,
                     os.fsencode(target), rename_noreplace) == 0:
            return
        error = ctypes.get_errno()
        if error not in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise OSError(error, os.strerror(error), str(target))
    # Older systems can still publish safely on filesystems supporting links.
    os.link(source, target, follow_symlinks=False)
    source.unlink()


def compress_to_limit(path: Path, limit_mb: int) -> Path:
    """Keep the full clip and replace it only after a smaller encode succeeds."""
    limit_bytes = limit_mb * 1024 * 1024
    if path.stat().st_size <= limit_bytes:
        return path
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=15, check=False)
    try:
        duration = float(probe.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("Clip saved, but its duration could not be read for compression.") from exc
    if duration <= 0:
        raise RuntimeError("Clip saved, but its duration could not be read for compression.")
    # Leave room for audio, container overhead and bitrate variation.
    target_bytes = int(limit_bytes * .82)
    for attempt in range(3):
        bitrate = max(100_000, int(target_bytes * 8 / duration - 96_000))
        temp = _temporary_video(path.parent, f"{path.stem}.compress-{attempt}", path.suffix)
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                 "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                 "-b:v", str(bitrate), "-maxrate", str(bitrate), "-bufsize", str(bitrate * 2),
                 "-c:a", "aac", "-b:a", "96k", str(temp)],
                capture_output=True, text=True, timeout=max(120, int(duration * 5)), check=False)
            if result.returncode != 0 or not temp.is_file() or not temp.stat().st_size:
                raise RuntimeError("Clip saved, but compression failed: " + result.stderr[-300:])
            size = temp.stat().st_size
            if size <= limit_bytes:
                temp.replace(path)
                return path
            target_bytes = int(target_bytes * limit_bytes / size * .84)
        finally:
            temp.unlink(missing_ok=True)
    raise RuntimeError("Clip saved, but it could not fit the selected size limit.")


def trim_clip(path: Path, start: float, end: float) -> Path:
    """Create a precise trimmed copy, keeping the source clip intact."""
    if start < 0 or end <= start:
        raise ValueError("Choose an end time after the start time.")
    temporary = _temporary_video(path.parent, f"{path.stem}.trim", ".mkv")
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start),
             "-i", str(path), "-t", str(end - start), "-map", "0:v:0", "-map", "0:a?",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "160k", str(temporary)],
            capture_output=True, text=True, timeout=max(120, int((end - start) * 5)), check=False)
        if result.returncode != 0 or not temporary.is_file() or not temporary.stat().st_size:
            raise OSError("Could not trim clip: " + result.stderr[-300:])
        # A clip may be created while FFmpeg is running. Publish without
        # replacing it, including when a concurrent file is a symlink.
        for index in range(1, 10_001):
            suffix = "" if index == 1 else f" {index}"
            target = path.with_name(f"{path.stem} trimmed{suffix}.mkv")
            try:
                _rename_noreplace(temporary, target)
            except FileExistsError:
                continue
            return target
        raise OSError("Could not choose a unique trimmed clip name.")
    except subprocess.TimeoutExpired as exc:
        raise OSError("Trimming took too long.") from exc
    finally:
        temporary.unlink(missing_ok=True)


def rename_clip(path: Path, name: str) -> Path:
    """Rename a clip while keeping its video extension and avoiding collisions."""
    name = name.strip()
    if not name or name in {".", ".."} or any(ord(char) < 32 or char in "/\\" for char in name):
        raise ValueError("Enter a valid clip name without slashes or control characters.")
    target = path.with_name(name + path.suffix)
    if target == path:
        return path
    try:
        _rename_noreplace(path, target)
    except FileExistsError as exc:
        raise FileExistsError(f"A clip named {target.name} already exists.") from exc
    return target


def recent_clips(directory: str, limit: int | None = 50) -> list[Path]:
    folder = Path(directory).expanduser()
    try:
        clips = (path for path in folder.iterdir()
                 if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in EXTENSIONS)
        return sorted(clips, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
    except OSError:
        return []


def clip_preview(path: Path) -> tuple[Path | None, str]:
    """Generate a cached thumbnail and read the duration without blocking GTK."""
    duration = ""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=12, check=False,
        )
        if result.returncode == 0:
            seconds = int(float(result.stdout.strip()))
            duration = f"{seconds // 60}:{seconds % 60:02d}"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    try:
        stat = path.stat()
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "clipdeck" / "thumbnails"
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        cache.chmod(0o700)
        identity = f"thumb-v3-630x354-png:{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        thumbnail = cache / (hashlib.sha256(identity.encode()).hexdigest() + ".png")
        if not thumbnail.exists():
            temp = _temporary_video(cache, thumbnail.stem, ".png")
            try:
                result = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "0.5",
                     "-i", str(path), "-frames:v", "1", "-vf",
                     "scale=630:354:flags=lanczos:force_original_aspect_ratio=increase,crop=630:354",
                     "-c:v", "png", "-compression_level", "6",
                     "-y", str(temp)],
                    capture_output=True, text=True, timeout=25, check=False,
                )
                if result.returncode == 0 and temp.is_file() and temp.stat().st_size:
                    _rename_noreplace(temp, thumbnail)
            except FileExistsError:
                pass  # Another preview worker finished first.
            finally:
                temp.unlink(missing_ok=True)
        return (thumbnail if thumbnail.is_file() else None), duration
    except (OSError, subprocess.TimeoutExpired):
        return None, duration
