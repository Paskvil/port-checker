#!/usr/bin/env python3
"""Tray app that periodically checks TCP ports and shows green/red status.

Settings live in GSettings (schema `local.portchecker`), editable via the
tray menu's settings dialog or the `gsettings` CLI.

`--check-deps` only verifies the required system libraries and exits.
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

# GI namespace -> (version, Ubuntu package providing it)
REQUIRED_GI = {
    "Gtk": ("3.0", "gir1.2-gtk-3.0"),
    "AyatanaAppIndicator3": ("0.1", "gir1.2-ayatanaappindicator3-0.1"),
    "Notify": ("0.7", "gir1.2-notify-0.7"),
}


def check_deps():
    """Exit with the apt command to run if any required system library is missing."""
    try:
        import gi
    except ImportError:
        missing = ["python3-gi"] + [pkg for _, pkg in REQUIRED_GI.values()]
    else:
        missing = []
        for name, (version, pkg) in REQUIRED_GI.items():
            try:
                gi.require_version(name, version)
            except ValueError:
                missing.append(pkg)
    if missing:
        sys.exit(
            "Port checker: missing system libraries, install them with:\n\n"
            f"    sudo apt install {' '.join(missing)}\n"
        )


check_deps()
if "--check-deps" in sys.argv[1:]:
    sys.exit(0)

from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import Gio, GLib, Gtk, Notify  # noqa: E402

from settings_dialog import SettingsDialog  # noqa: E402

APP_ID = "local.portchecker"
APP_NAME = "Port checker"
HERE = os.path.dirname(os.path.realpath(__file__))
ICON_DIR = os.path.join(HERE, "icons")
SCHEMA_DIR = os.path.join(HERE, "schemas")

ICON_OK = "portchecker-ok"
ICON_FAIL = "portchecker-fail"
ICON_UNKNOWN = "portchecker-unknown"


def load_settings():
    """Use the installed schema if there is one, else the one in the repo (dev mode)."""
    if Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True):
        return Gio.Settings.new(APP_ID)
    compiled = os.path.join(SCHEMA_DIR, "gschemas.compiled")
    xml = os.path.join(SCHEMA_DIR, f"{APP_ID}.gschema.xml")
    if not os.path.exists(compiled) or os.path.getmtime(compiled) < os.path.getmtime(xml):
        if not shutil.which("glib-compile-schemas"):
            sys.exit(
                "Port checker: schema not installed and glib-compile-schemas is missing;\n"
                "run ./install.sh, or: sudo apt install libglib2.0-bin"
            )
        subprocess.run(["glib-compile-schemas", SCHEMA_DIR], check=True)
    source = Gio.SettingsSchemaSource.new_from_directory(
        SCHEMA_DIR, Gio.SettingsSchemaSource.get_default(), False
    )
    return Gio.Settings.new_full(source.lookup(APP_ID, False), None, None)


def check_port(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class Target:
    def __init__(self, host, port, alias, active):
        self.host, self.port, self.alias, self.active = host, port, alias, active
        self.up = None  # None = not checked yet

    @property
    def key(self):
        return (self.host, self.port)

    @property
    def name(self):
        return self.alias or f"{self.host}:{self.port}"


class PortChecker:
    def __init__(self):
        Notify.init(APP_NAME)
        self.settings = load_settings()
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.check_lock = threading.Lock()
        self.timer_id = None
        self.recheck_pending = False
        self.dialog = None
        self.targets = []

        self.indicator = AppIndicator.Indicator.new(
            APP_ID, ICON_UNKNOWN, AppIndicator.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_icon_theme_path(ICON_DIR)
        self.indicator.set_title(APP_NAME)
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        self.settings.connect("changed", self.on_settings_changed)
        self.load_targets()
        self.rebuild_menu()
        self.check_now()

    # --- settings -----------------------------------------------------------

    def load_targets(self):
        """(Re)read targets, keeping the last known state of unchanged ones."""
        old = {t.key: t.up for t in self.targets}
        self.targets = []
        for host, port, alias, active in self.settings.get_value("targets").unpack():
            t = Target(host, port, alias, active)
            t.up = old.get(t.key)
            self.targets.append(t)

    def on_settings_changed(self, _settings, key):
        if key == "targets":
            self.load_targets()
            self.rebuild_menu()
            self.update_icon()
        if key in ("targets", "interval", "timeout") and not self.recheck_pending:
            # saving the dialog changes several keys at once -> coalesce into one re-check
            self.recheck_pending = True
            GLib.idle_add(self.on_recheck_idle)

    def on_recheck_idle(self):
        self.recheck_pending = False
        self.check_now()
        return GLib.SOURCE_REMOVE

    # --- checking -----------------------------------------------------------

    def schedule(self):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
        self.timer_id = GLib.timeout_add_seconds(self.settings.get_uint("interval"), self.on_timer)

    def on_timer(self):
        self.timer_id = None
        self.check_now()
        return GLib.SOURCE_REMOVE

    def check_now(self, *_args):
        self.schedule()
        active = [t for t in self.targets if t.active]
        timeout = self.settings.get_double("timeout")
        # runs in a worker thread so slow/dead hosts never block the UI
        threading.Thread(target=self.run_checks, args=(active, timeout), daemon=True).start()

    def run_checks(self, targets, timeout):
        if not self.check_lock.acquire(blocking=False):
            return  # previous round still running
        try:
            results = list(
                self.executor.map(lambda t: check_port(t.host, t.port, timeout), targets)
            )
        finally:
            self.check_lock.release()
        GLib.idle_add(self.apply_results, targets, results)

    def apply_results(self, targets, results):
        changed = []
        for t, up in zip(targets, results):
            if t not in self.targets:
                continue  # removed from settings meanwhile
            if t.up != up:
                # don't notify on the very first check of a target that's up
                if not (t.up is None and up):
                    changed.append(t)
                t.up = up
        self.rebuild_menu()
        self.update_icon()
        if changed and self.settings.get_boolean("notify"):
            self.notify(changed)
        return GLib.SOURCE_REMOVE

    # --- UI -----------------------------------------------------------------

    def update_icon(self):
        active = [t for t in self.targets if t.active]
        if any(t.up is False for t in active):
            icon = ICON_FAIL
        elif active and all(t.up for t in active):
            icon = ICON_OK
        else:
            icon = ICON_UNKNOWN
        up = sum(1 for t in active if t.up)
        down = sum(1 for t in active if t.up is False)
        self.indicator.set_icon_full(icon, f"{up} up, {down} down")

    def rebuild_menu(self):
        menu = Gtk.Menu()
        active = [t for t in self.targets if t.active]
        up = sum(1 for t in active if t.up)
        down = sum(1 for t in active if t.up is False)
        header = Gtk.MenuItem(label=f"{APP_NAME}: {up} up, {down} down")
        header.set_sensitive(False)
        menu.append(header)
        menu.append(Gtk.SeparatorMenuItem())

        for t in active:
            state = {True: "✅ up", False: "❌ DOWN", None: "… checking"}[t.up]
            item = Gtk.MenuItem(label=f"{state}: {t.name}")
            item.connect("activate", self.check_now)
            menu.append(item)
        if not active:
            item = Gtk.MenuItem(label="no active targets")
            item.set_sensitive(False)
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())
        for label, cb in (
            ("Check now", self.check_now),
            ("Settings…", self.open_settings),
            ("Quit", self.quit),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            menu.append(item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def notify(self, changed):
        lines = [f"{t.name} is {'online' if t.up else 'OFFLINE'}" for t in changed]
        icon = os.path.join(ICON_DIR, (ICON_OK if all(t.up for t in changed) else ICON_FAIL) + ".svg")
        Notify.Notification.new(APP_NAME, "\n".join(lines), icon).show()

    def open_settings(self, *_args):
        if self.dialog:
            self.dialog.present()
            return
        self.dialog = SettingsDialog(self.settings)
        self.dialog.connect("destroy", lambda _d: setattr(self, "dialog", None))

    def quit(self, *_args):
        self.executor.shutdown(wait=False, cancel_futures=True)
        Notify.uninit()
        Gtk.main_quit()


def main():
    GLib.set_application_name(APP_NAME)
    PortChecker()
    Gtk.main()


if __name__ == "__main__":
    main()
