# main.py
#
# Copyright 2026 predrag
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gio, Adw
from .window import AzurevpnWindow
from .proxy_state import ProxyState
from .tray_icon import TrayIcon


class AzurevpnApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(
            application_id="org.gnome.azurevpn",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            resource_base_path="/org/gnome/azurevpn",
        )
        # Zisti stav proxy pri spustení aplikácie
        self.proxy_state = ProxyState()
        # System tray icon
        self._tray = TrayIcon(self)
        self._tray.register()
        # Keep the app running even when all windows are hidden
        self.hold()
        # First activation should not show window
        self._first_activate = True

    def do_activate(self):
        """Called when the application is activated.

        We raise the application's main window, creating it if
        necessary.
        """

        # On first launch, just create the window hidden (for tray operation)
        if self._first_activate:
            self._first_activate = False
            win = AzurevpnWindow(application=self)
            self._init_proxy_button(win)
            # Don't present — stay in tray only
            return

        win = self.props.active_window
        if not win:
            win = AzurevpnWindow(application=self)
            self._init_proxy_button(win)
        win.present()

    def _init_proxy_button(self, win):
        """Set proxy button state based on current proxy mode."""
        try:
            btn = getattr(win, "proxy_button", None)
            if self.proxy_state.current_state.stdout.strip() == "'none'":
                btn.set_label("Zapnuť Proxy")
                btn.add_css_class("destructive-action")
            else:
                btn.set_label("Vypnuť Proxy")
                btn.add_css_class("suggested-action")
        except Exception:
            pass

    def create_action(self, name, callback, shortcuts=None):
        """Add an application action.

        Args:
            name: the name of the action
            callback: the function to be called when the action is
              activated
            shortcuts: an optional list of accelerators
        """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    app = AzurevpnApplication()
    return app.run(sys.argv)
