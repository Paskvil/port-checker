# port-checker
simple port checking tool for gnome desktop

Tray icon that checks TCP ports every N seconds: green = all up, red = at least one down, grey = not checked yet. Notifies when a target goes up or down.

## install (Ubuntu 24.04 / GNOME)

```sh
sudo apt install gir1.2-ayatanaappindicator3-0.1
./install.sh                      # installs the GSettings schema + autostart entry
python3 port_checker.py &
```

If a required library is missing, `port_checker.py` prints the `sudo apt install ...` command to run and exits (`--check-deps` does only that check).

`./uninstall.sh` stops the app and removes its stored settings, the schema and the autostart entry.

Needs the "Ubuntu AppIndicators" GNOME extension (enabled by default on Ubuntu).

## settings

Stored in GSettings under `local.portchecker`; edit via the tray menu's "Settings…" dialog or:

```sh
gsettings set local.portchecker targets "[('localhost', 80, 'web', true), ('db.example.com', 5432, '', true)]"
gsettings set local.portchecker interval 30     # seconds
gsettings set local.portchecker timeout 2.0     # seconds
gsettings set local.portchecker notify true
```

Each target is `(host, port, alias, active)`; an empty alias shows `host:port`. Changes apply immediately.

## license

BSD 2-Clause, see [LICENSE](LICENSE).
