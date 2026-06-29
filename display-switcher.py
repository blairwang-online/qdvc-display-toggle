#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import subprocess
import re


def get_outputs():
    """Return (connected_outputs, primary). Connected = plugged in."""
    out = subprocess.check_output(['xrandr', '--query']).decode()
    connected = []
    primary = None
    for line in out.splitlines():
        m = re.match(r'^(\S+)\s+connected\s*(primary)?', line)
        if m:
            connected.append(m.group(1))
            if m.group(2):
                primary = m.group(1)
    if primary is None and connected:
        primary = connected[0]
    return connected, primary


def pick_internal(connected):
    """Heuristic: internal panel is usually eDP/LVDS/DSI."""
    for name in connected:
        if re.match(r'(eDP|LVDS|DSI)', name, re.I):
            return name
    return connected[0] if connected else None


def apply_mode(mode):
    connected, primary = get_outputs()
    if len(connected) < 1:
        return
    internal = pick_internal(connected)
    externals = [o for o in connected if o != internal]

    cmd = ['xrandr']

    if mode == 'Mirror':
        # Mirror everything onto the internal (or first) output position.
        base = internal or connected[0]
        for o in connected:
            cmd += ['--output', o, '--auto', '--same-as', base]

    elif mode == 'Join Displays':
        prev = None
        for o in connected:
            cmd += ['--output', o, '--auto']
            if prev:
                cmd += ['--right-of', prev]
            prev = o

    elif mode == 'External Only':
        if not externals:
            return
        for o in externals:
            cmd += ['--output', o, '--auto']
        cmd += ['--output', internal, '--off']
        # primary on first external
        cmd += ['--output', externals[0], '--primary']

    elif mode == 'Built-in Only':
        cmd += ['--output', internal, '--auto', '--primary']
        for o in externals:
            cmd += ['--output', o, '--off']

    subprocess.run(cmd)


class DisplayPopup(Gtk.Window):
    MODES = ['Mirror', 'Join Displays', 'External Only', 'Built-in Only']

    def __init__(self):
        # TOPLEVEL window so keyboard focus is grabbed reliably.
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title('Display Mode')
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_resizable(False)

        self.selected = 1  # default highlight "Join Displays"
        self.buttons = []

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        for i, mode in enumerate(self.MODES):
            btn = Gtk.Button()

            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            num = Gtk.Label()
            num.set_markup(
                '<span size="36000" weight="bold">{}</span>'.format(i + 1))
            name = Gtk.Label(label=mode)
            inner.pack_start(num, True, True, 0)
            inner.pack_start(name, False, False, 0)
            btn.add(inner)

            btn.set_size_request(140, 110)
            btn.connect('clicked', self.on_button_clicked, i)
            self.buttons.append(btn)
            box.pack_start(btn, True, True, 0)

        self.add(box)

        self.connect('key-press-event', self.on_key)
        self.connect('destroy', lambda *a: Gtk.main_quit())
        self.update_highlight()

    def update_highlight(self):
        for i, btn in enumerate(self.buttons):
            if i == self.selected:
                btn.grab_focus()

    def on_button_clicked(self, widget, index):
        mode = self.MODES[index]
        self.hide()
        apply_mode(mode)
        Gtk.main_quit()

    def activate_selected(self):
        mode = self.MODES[self.selected]
        self.hide()
        apply_mode(mode)
        Gtk.main_quit()

    def on_key(self, widget, event):
        key = event.keyval

        # Number keys 1-4 (top row and keypad) highlight, do not activate.
        number_keys = {
            Gdk.KEY_1: 0, Gdk.KEY_KP_1: 0,
            Gdk.KEY_2: 1, Gdk.KEY_KP_2: 1,
            Gdk.KEY_3: 2, Gdk.KEY_KP_3: 2,
            Gdk.KEY_4: 3, Gdk.KEY_KP_4: 3,
        }

        if key in number_keys:
            self.selected = number_keys[key]
            self.update_highlight()
            return True
        elif key in (Gdk.KEY_Right, Gdk.KEY_Tab):
            self.selected = (self.selected + 1) % len(self.MODES)
            self.update_highlight()
            return True
        elif key in (Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            self.selected = (self.selected - 1) % len(self.MODES)
            self.update_highlight()
            return True
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate_selected()
            return True
        elif key == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False


def main():
    win = DisplayPopup()
    win.show_all()
    win.present()
    Gtk.main()


if __name__ == '__main__':
    main()
