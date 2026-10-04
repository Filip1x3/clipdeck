#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This copy was not installed from a Git clone. Download a fresh copy and run install.sh instead." >&2
  exit 1
fi

git pull --ff-only
bash ./install.sh --no-deps
echo "Clipdeck is updated. Quit the running app and open it again to load the new version."
