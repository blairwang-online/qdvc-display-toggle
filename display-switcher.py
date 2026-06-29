#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import subprocess
import re

# Minimum whitespace (px) on each side of the centered icon+label header.
# The header is centered, so this is roughly the gap left and right of it.
# Larger value = the icon+label unit is squeezed narrower (label wraps more).
HEADER_SIDE_PADDING_PX = 60

# Counterpart setting for the text label
HEADER_TEXT_LABEL_SIZE = 48

def get_outputs():
    """Return (connected, primary, modes).

    connected: list of connected output names (plugged in).
    primary:   name of the primary output (or first connected).
    modes:     dict mapping output name -> list of "WxH" mode strings,
               in xrandr's listed order (preferred/native first).
    """
    out = subprocess.check_output(['xrandr', '--query']).decode()
    connected = []
    primary = None
    modes = {}
    current = None
    for line in out.splitlines():
        m = re.match(r'^(\S+)\s+connected\s*(primary)?', line)
        if m:
            current = m.group(1)
            connected.append(current)
            modes[current] = []
            if m.group(2):
                primary = current
            continue
        # A disconnected output resets context so we don't attach modes to it.
        if re.match(r'^\S+\s+disconnected', line):
            current = None
            continue
        # Mode lines are indented and start with a resolution like 1920x1080.
        mm = re.match(r'^\s+(\d+x\d+)', line)
        if mm and current is not None:
            modes[current].append(mm.group(1))
    if primary is None and connected:
        primary = connected[0]
    return connected, primary, modes


def common_mode(connected, modes):
    """Find a resolution every connected output supports.

    Prefer the largest by pixel area. Returns a "WxH" string or None.
    """
    if not connected:
        return None
    sets = [set(modes.get(o, [])) for o in connected]
    shared = set.intersection(*sets) if sets else set()
    if not shared:
        return None

    def area(res):
        w, h = res.split('x')
        return int(w) * int(h)

    return max(shared, key=area)


def pick_internal(connected):
    """Heuristic: internal panel is usually eDP/LVDS/DSI."""
    for name in connected:
        if re.match(r'(eDP|LVDS|DSI)', name, re.I):
            return name
    return connected[0] if connected else None


def apply_mode(mode):
    connected, primary, modes = get_outputs()
    if len(connected) < 1:
        return
    internal = pick_internal(connected)
    externals = [o for o in connected if o != internal]

    cmd = ['xrandr']

    if mode == 'Mirror':
        # Mirror requires every output at the SAME resolution and origin.
        # --auto picks each panel's native mode independently, so if they
        # differ, xrandr can't overlay them. Pick a shared resolution.
        res = common_mode(connected, modes)
        for o in connected:
            cmd += ['--output', o]
            if res:
                cmd += ['--mode', res]
            else:
                cmd += ['--auto']
            cmd += ['--pos', '0x0']
            if o != connected[0]:
                cmd += ['--same-as', connected[0]]

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

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip() or 'xrandr failed with no message.'
        dialog = Gtk.MessageDialog(
            transient_for=None,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text='Could not apply "{}"'.format(mode),
        )
        dialog.format_secondary_text(
            '{}\n\nCommand:\n{}'.format(msg, ' '.join(cmd)))
        dialog.run()
        dialog.destroy()


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

        # Outer vertical container: header (icon + text) on top, buttons below.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)
        outer.set_margin_start(20)
        outer.set_margin_end(20)

        # Header: icon + instruction text, kept together and centered, with
        # fixed whitespace on each side. Centering the box (halign=CENTER)
        # stops it stretching to the full window width.
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_halign(Gtk.Align.CENTER)
        header.set_margin_start(HEADER_SIDE_PADDING_PX)
        header.set_margin_end(HEADER_SIDE_PADDING_PX)

        # MATE "Display Preferences" icon. Try the MATE-specific name first,
        # then the generic freedesktop name, so it works across icon themes.
        icon = Gtk.Image()
        theme = Gtk.IconTheme.get_default()
        for icon_name in ('mate-preferences-desktop-display',
                          'preferences-desktop-display',
                          'video-display'):
            if theme.has_icon(icon_name):
                icon.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
                icon.set_pixel_size(48)
                break
        icon.set_valign(Gtk.Align.CENTER)
        header.pack_start(icon, False, False, 0)

        # Instruction text. max_width_chars makes the label report a small
        # preferred width, so it wraps onto multiple lines instead of taking
        # its full natural single-line width.
        instructions = Gtk.Label()
        instructions.set_markup(
            'Use the <b>arrow keys</b> or number keys '
            '<b>1</b>\u2013<b>4</b> to choose, then press <b>Enter</b>'
            ' \u2014 or simply <b>click</b> an option.')
        instructions.set_line_wrap(True)
        instructions.set_max_width_chars(HEADER_TEXT_LABEL_SIZE)
        instructions.set_xalign(0.0)
        instructions.set_valign(Gtk.Align.CENTER)
        header.pack_start(instructions, False, False, 0)

        outer.pack_start(header, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

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

        outer.pack_start(box, True, True, 0)
        self.add(outer)

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
