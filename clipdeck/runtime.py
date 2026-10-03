"""Private runtime directory shared by the recorder and audio filter."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def ensure_private_runtime_directory(directory: Path) -> None:
    """Reject a substituted /tmp directory before opening sockets or state files."""
    base = directory.parent
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    base_info = base.lstat()
    if not stat.S_ISDIR(base_info.st_mode):
        raise OSError("The Clipdeck runtime parent is not a directory.")
    # /tmp itself is protected by the sticky bit. Other parents must belong
    # to this user and must not allow another user to replace our child.
    if base != Path("/tmp") and (base_info.st_uid != os.getuid() or base_info.st_mode & 0o022):
        raise OSError("The Clipdeck runtime parent is not private.")

    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise OSError("The Clipdeck runtime folder is not private.")
    directory.chmod(0o700)
