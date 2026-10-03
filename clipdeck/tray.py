"""GTK 3 status notifier companion for the GTK 4 Clipdeck window."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
except (ImportError, ValueError):
    # Some distributions still provide the original AppIndicator typelib.
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator  # noqa: E402


ICON = Path(__file__).resolve().parent.parent / "assets" / "clipdeck.svg"


def main() -> int:
    parent = int(sys.argv[1]) if len(sys.argv) > 1 else os.getppid()
    app_id = sys.argv[2] if len(sys.argv) > 2 else "io.github.clipdeck.Clipdeck"
    if not Gtk.init_check()[0]:
        return 1
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    actions = Gio.DBusActionGroup.get(bus, app_id, "/" + app_id.replace(".", "/"))
    indicator = AppIndicator.Indicator.new(
        "clipdeck-tray", str(ICON), AppIndicator.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_icon_full(str(ICON), "Clipdeck")
    menu = Gtk.Menu()
    for title, action in (("Open Clipdeck", "show"), ("Library", "library"),
                          ("Quit", "quit")):
        item = Gtk.MenuItem(label=title)
        item.connect("activate", lambda _item, name=action: actions.activate_action(name, None))
        menu.append(item)
    menu.show_all()
    indicator.set_menu(menu)
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    def check_parent():
        if os.getppid() != parent:
            Gtk.main_quit()
            return False
        return True

    GLib.timeout_add_seconds(2, check_parent)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
