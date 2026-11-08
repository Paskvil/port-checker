"""Settings dialog: edit targets, interval, timeout and notifications; saved to GSettings on "Save"."""
from gi.repository import GLib, Gtk

COL_ACTIVE, COL_HOST, COL_PORT, COL_ALIAS = range(4)


class SettingsDialog(Gtk.Dialog):
    def __init__(self, settings):
        super().__init__(title="Port checker settings")
        self.settings = settings
        self.set_default_size(560, 420)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.connect("response", self.on_response)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        # --- targets list ---
        self.store = Gtk.ListStore(bool, str, int, str)
        for host, port, alias, active in settings.get_value("targets").unpack():
            self.store.append([active, host, port, alias])

        self.view = Gtk.TreeView(model=self.store)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.on_toggled)
        self.view.append_column(Gtk.TreeViewColumn("Active", toggle, active=COL_ACTIVE))
        self.add_text_column("Host", COL_HOST, expand=True)
        port = self.add_text_column("Port", COL_PORT)
        port.set_min_width(70)
        self.add_text_column("Alias (optional)", COL_ALIAS, expand=True)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.add(self.view)
        box.pack_start(scroller, True, True, 0)

        buttons = Gtk.Box(spacing=6)
        add = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        add.set_tooltip_text("Add target")
        add.connect("clicked", self.on_add)
        self.remove = Gtk.Button.new_from_icon_name("list-remove-symbolic", Gtk.IconSize.BUTTON)
        self.remove.set_tooltip_text("Remove selected target")
        self.remove.connect("clicked", self.on_remove)
        self.view.get_selection().connect(
            "changed", lambda sel: self.remove.set_sensitive(sel.count_selected_rows() > 0)
        )
        self.remove.set_sensitive(False)
        buttons.pack_start(add, False, False, 0)
        buttons.pack_start(self.remove, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        # --- general options ---
        grid = Gtk.Grid(column_spacing=12, row_spacing=6, margin_top=6)
        self.interval = self.spin(5, 86400, 1, 0, settings.get_uint("interval"))
        self.timeout = self.spin(0.1, 60, 0.5, 1, settings.get_double("timeout"))
        self.notify = Gtk.Switch(active=settings.get_boolean("notify"), halign=Gtk.Align.START)
        for row, (label, widget) in enumerate((
            ("Check every (seconds)", self.interval),
            ("Connection timeout (seconds)", self.timeout),
            ("Notify on status change", self.notify),
        )):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        box.pack_start(grid, False, False, 0)

        self.error = Gtk.Label(xalign=0)
        self.error.get_style_context().add_class("error")
        box.pack_start(self.error, False, False, 0)

        self.show_all()
        self.error.hide()

    @staticmethod
    def spin(lo, hi, step, digits, value):
        s = Gtk.SpinButton.new_with_range(lo, hi, step)
        s.set_digits(digits)
        s.set_value(value)
        s.set_halign(Gtk.Align.START)
        return s

    def add_text_column(self, title, col, expand=False):
        cell = Gtk.CellRendererText(editable=True)
        cell.connect("edited", self.on_edited, col)
        column = Gtk.TreeViewColumn(title, cell, text=col)
        column.set_expand(expand)
        column.set_resizable(True)
        self.view.append_column(column)
        return column

    def on_toggled(self, _cell, path):
        self.store[path][COL_ACTIVE] = not self.store[path][COL_ACTIVE]

    def on_edited(self, _cell, path, text, col):
        text = text.strip()
        if col == COL_PORT:
            if not text.isdigit() or not 1 <= int(text) <= 65535:
                return  # keep the old value
            self.store[path][col] = int(text)
        else:
            self.store[path][col] = text

    def on_add(self, _button):
        it = self.store.append([True, "", 80, ""])
        path = self.store.get_path(it)
        # jump straight into editing the host
        self.view.set_cursor(path, self.view.get_column(COL_HOST), True)

    def on_remove(self, _button):
        model, it = self.view.get_selection().get_selected()
        if it:
            model.remove(it)

    def on_response(self, _dialog, response):
        if response == Gtk.ResponseType.OK:
            targets = [(r[COL_HOST], r[COL_PORT], r[COL_ALIAS], r[COL_ACTIVE]) for r in self.store]
            if any(not host for host, *_ in targets):
                self.error.set_text("Every target needs a host (or remove the empty row)")
                self.error.show()
                return
            self.settings.set_value("targets", GLib.Variant("a(sqsb)", targets))
            self.settings.set_uint("interval", self.interval.get_value_as_int())
            self.settings.set_double("timeout", self.timeout.get_value())
            self.settings.set_boolean("notify", self.notify.get_active())
        self.destroy()
