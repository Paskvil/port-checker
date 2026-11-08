#!/usr/bin/env bash
# stops the app, removes its stored settings, the GSettings schema and the autostart entry
set -euo pipefail
schemas="${XDG_DATA_HOME:-$HOME/.local/share}/glib-2.0/schemas"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/local.portchecker.desktop"

pkill -f 'python[0-9.]* .*port_checker\.py' && echo "stopped running instance" || true

# stored values live in dconf independently of the schema, wipe them too
dconf reset -f /local/portchecker/

rm -f "$autostart"
if [ -f "$schemas/local.portchecker.gschema.xml" ]; then
    rm "$schemas/local.portchecker.gschema.xml"
    glib-compile-schemas "$schemas"
fi

echo "uninstalled - settings, schema and autostart entry removed"
