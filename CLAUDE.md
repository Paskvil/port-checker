# port-checker

- Python + PyGObject, GTK3 + `AyatanaAppIndicator3` - GTK4 can't be used, indicator libs are GTK3-only; `Gtk.StatusIcon` isn't shown by GNOME anymore
- target: Ubuntu 24.04, GNOME 46 with the `ubuntu-appindicators` extension
- settings in GSettings schema `local.portchecker` (`schemas/`); without an installed schema `port_checker.py` compiles and uses the repo copy (dev mode)
- `settings_dialog.py` writes all keys on Save; `PortChecker.on_settings_changed` coalesces the resulting `changed` signals into one re-check via `GLib.idle_add`
- `check_deps()` runs before any `gi.repository` import and maps missing GI namespaces to apt packages (`REQUIRED_GI`) - add new GI deps there
- `uninstall.sh` must `dconf reset` before removing the schema - stored values outlive the schema
- checks run in worker threads, results go back to the UI via `GLib.idle_add` - never do blocking socket calls on the main loop
