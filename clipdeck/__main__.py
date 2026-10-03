from __future__ import annotations

import argparse
import sys

from .config import Settings
from .feedback import clip_saved
from .recorder import Recorder, RecorderError


def main() -> int:
    parser = argparse.ArgumentParser(description="Clipdeck — game clips and screen recording")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--save-replay", action="store_true", help="save the last seconds")
    group.add_argument("--toggle-recording", action="store_true", help="start or stop a full recording")
    group.add_argument("--start-buffer", "--ensure-capture", dest="start_capture", action="store_true", help="ensure background capture is running")
    group.add_argument("--stop-buffer", "--stop-capture", dest="stop_capture", action="store_true", help="stop background capture")
    group.add_argument("--status", action="store_true", help="show capture status")
    args = parser.parse_args()
    if not any((args.save_replay, args.toggle_recording, args.start_capture, args.stop_capture, args.status)):
        from .ui import ClipdeckApp
        return ClipdeckApp().run(sys.argv)

    settings = Settings.load()
    recorder = Recorder(settings)
    try:
        if args.save_replay:
            notified = False
            def notify_saved(_path):
                nonlocal notified
                if not notified:
                    notified = True
                    clip_saved(settings)
            path = recorder.save_replay(on_saved=notify_saved)
            notify_saved(path)
            print(path)
        elif args.toggle_recording:
            path = recorder.toggle_record()
            print(path or "Recording started.")
        elif args.start_capture:
            recorder.start()
            print("Background capture is ready.")
        elif args.stop_capture:
            recorder.stop()
            print("Background capture stopped.")
        else:
            print(recorder.status())
        return 0
    except RecorderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
