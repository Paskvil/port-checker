#!/usr/bin/env bash
# installs the GSettings schema for the current user and adds the app to autostart
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
schemas="${XDG_DATA_HOME:-$HOME/.local/share}/glib-2.0/schemas"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

python3 "$here/port_checker.py" --check-deps

mkdir -p "$schemas" "$autostart"
cp "$here/schemas/local.portchecker.gschema.xml" "$schemas/"
glib-compile-schemas "$schemas"

cat > "$autostart/local.portchecker.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Port checker
Comment=Tray icon showing whether watched TCP ports are reachable
Exec=python3 $here/port_checker.py
Icon=$here/icons/portchecker-ok.svg
X-GNOME-Autostart-enabled=true
NoDisplay=false
DESKTOP

echo "installed - start it now with: python3 $here/port_checker.py &"
