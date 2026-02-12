# tray_icon.py — StatusNotifierItem (system tray) for AzureVPN
#
# Implements the org.kde.StatusNotifierItem DBus interface so the app
# shows a persistent icon in the system tray / top-bar indicator area.
#
# On GNOME you need the "AppIndicator and KStatusNotifierItem Support"
# extension (installed by default on Ubuntu, available on extensions.gnome.org).
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from gi.repository import Gio, GLib

logger = logging.getLogger("azurevpn")

# ── DBus XML for org.kde.StatusNotifierItem ──────────────────────────
_SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>

    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>

    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewStatus">
      <arg name="status" type="s"/>
    </signal>
    <signal name="NewToolTip"/>
  </interface>
</node>
"""

# ── DBus XML for com.canonical.dbusmenu ──────────────────────────────
_DBUSMENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <method name="GetLayout">
      <arg name="parentId" type="i" direction="in"/>
      <arg name="recursionDepth" type="i" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="revision" type="u" direction="out"/>
      <arg name="layout" type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="Event">
      <arg name="id" type="i" direction="in"/>
      <arg name="eventId" type="s" direction="in"/>
      <arg name="data" type="v" direction="in"/>
      <arg name="timestamp" type="u" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg name="id" type="i" direction="in"/>
      <arg name="needUpdate" type="b" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg name="ids" type="ai" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="properties" type="a(ia{sv})" direction="out"/>
    </method>

    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>

    <signal name="LayoutUpdated">
      <arg name="revision" type="u"/>
      <arg name="parent" type="i"/>
    </signal>
    <signal name="ItemsPropertiesUpdated">
      <arg name="updatedProps" type="a(ia{sv})"/>
      <arg name="removedProps" type="a(ias)"/>
    </signal>
  </interface>
</node>
"""

_MENU_PATH = "/org/gnome/azurevpn/Menu"
_SNI_PATH = "/StatusNotifierItem"


class TrayIcon:
    """Register a StatusNotifierItem on the session bus."""

    def __init__(self, app):
        self._app = app
        self._bus = None
        self._sni_reg_id = 0
        self._menu_reg_id = 0
        self._bus_name_id = 0
        self._menu_revision = 1
        self._tooltip_text = "Azure VPN"

        # Menu items: list of (id, label, action_name_or_None)
        self._menu_items = [
            (1, "Zobraziť okno", "show"),
            (2, "Zapnuť Proxy", "toggle-proxy"),
            (3, "", None),  # separator
            (4, "Ukončiť", "quit"),
        ]

    # ── public API ───────────────────────────────────────────────────

    def register(self):
        """Acquire a bus name and export the SNI + Menu objects."""
        self._bus_name = "org.gnome.azurevpn.StatusNotifierItem"
        self._bus_name_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            self._bus_name,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            self._on_name_acquired,
            self._on_name_lost,
        )

    def unregister(self):
        if self._bus and self._sni_reg_id:
            self._bus.unregister_object(self._sni_reg_id)
        if self._bus and self._menu_reg_id:
            self._bus.unregister_object(self._menu_reg_id)
        if self._bus_name_id:
            Gio.bus_unown_name(self._bus_name_id)

    def update_proxy_label(self, proxy_active: bool):
        """Update the proxy menu item label and emit LayoutUpdated."""
        self._menu_items[1] = (
            2,
            "Vypnuť Proxy" if proxy_active else "Zapnuť Proxy",
            "toggle-proxy",
        )
        self._menu_revision += 1
        if self._bus and self._menu_reg_id:
            self._bus.emit_signal(
                None,
                _MENU_PATH,
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                GLib.Variant("(ui)", (self._menu_revision, 0)),
            )

    def update_tooltip(self, text: str):
        self._tooltip_text = text

    # ── bus callbacks ────────────────────────────────────────────────

    def _on_bus_acquired(self, connection, name):
        self._bus = connection

        # Export StatusNotifierItem
        node_info = Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
        self._sni_reg_id = connection.register_object(
            _SNI_PATH,
            node_info.interfaces[0],
            self._sni_method_call,
            self._sni_get_property,
            None,
        )

        # Export DBusMenu
        menu_info = Gio.DBusNodeInfo.new_for_xml(_DBUSMENU_XML)
        self._menu_reg_id = connection.register_object(
            _MENU_PATH,
            menu_info.interfaces[0],
            self._menu_method_call,
            self._menu_get_property,
            None,
        )

    def _on_name_acquired(self, connection, name):
        logger.info(f"Tray icon bus name acquired: {name}")
        # Register with the StatusNotifierWatcher
        try:
            connection.call(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (name,)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                self._on_registered,
            )
        except Exception:
            logger.warning(
                "StatusNotifierWatcher not available — tray icon won't appear"
            )

    def _on_registered(self, connection, result):
        try:
            connection.call_finish(result)
            logger.info("Tray icon registered with StatusNotifierWatcher")
        except Exception as e:
            logger.warning(f"Failed to register tray icon: {e}")

    def _on_name_lost(self, connection, name):
        logger.warning(f"Tray icon bus name lost: {name}")

    # ── StatusNotifierItem method calls ──────────────────────────────

    def _sni_method_call(
        self, connection, sender, path, iface, method, params, invocation
    ):
        if method == "Activate":
            GLib.idle_add(self._activate_window)
            invocation.return_value(None)
        elif method == "SecondaryActivate":
            GLib.idle_add(self._activate_window)
            invocation.return_value(None)
        elif method == "ContextMenu":
            # context menu is handled via dbusmenu
            invocation.return_value(None)
        elif method == "Scroll":
            invocation.return_value(None)
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", "")

    def _sni_get_property(self, connection, sender, path, iface, prop):
        if prop == "Category":
            return GLib.Variant("s", "ApplicationStatus")
        elif prop == "Id":
            return GLib.Variant("s", "azurevpn")
        elif prop == "Title":
            return GLib.Variant("s", "Azure VPN")
        elif prop == "Status":
            return GLib.Variant("s", "Active")
        elif prop == "IconName":
            return GLib.Variant("s", "org.gnome.azurevpn")
        elif prop == "IconThemePath":
            return GLib.Variant("s", "")
        elif prop == "ToolTip":
            # (icon_name, icon_data[], title, description)
            return GLib.Variant(
                "(sa(iiay)ss)", ("", [], "Azure VPN", self._tooltip_text)
            )
        elif prop == "ItemIsMenu":
            return GLib.Variant("b", True)
        elif prop == "Menu":
            return GLib.Variant("o", _MENU_PATH)
        return None

    # ── DBusMenu method calls ────────────────────────────────────────

    def _menu_method_call(
        self, connection, sender, path, iface, method, params, invocation
    ):
        if method == "GetLayout":
            parent_id, depth, prop_names = params.unpack()
            layout = self._build_layout(parent_id)
            invocation.return_value(
                GLib.Variant("(u(ia{sv}av))", (self._menu_revision, layout))
            )
        elif method == "GetGroupProperties":
            ids, prop_names = params.unpack()
            result = []
            for item_id, label, action in self._menu_items:
                if item_id in ids or not ids:
                    props = self._item_properties(item_id, label, action)
                    result.append((item_id, props))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (result,)))
        elif method == "Event":
            item_id, event_id, data, timestamp = params.unpack()
            if event_id == "clicked":
                GLib.idle_add(self._handle_menu_click, item_id)
            invocation.return_value(None)
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", "")

    def _menu_get_property(self, connection, sender, path, iface, prop):
        if prop == "Version":
            return GLib.Variant("u", 3)
        elif prop == "Status":
            return GLib.Variant("s", "normal")
        return None

    def _item_properties(self, item_id, label, action):
        props = {}
        if not label:
            # separator
            props["type"] = GLib.Variant("s", "separator")
        else:
            props["label"] = GLib.Variant("s", label)
            props["enabled"] = GLib.Variant("b", True)
            props["visible"] = GLib.Variant("b", True)
        return props

    def _build_layout(self, parent_id):
        """Return (id, properties, [children]) for the root or a child."""
        if parent_id == 0:
            children = []
            for item_id, label, action in self._menu_items:
                props = self._item_properties(item_id, label, action)
                child = GLib.Variant(
                    "v", GLib.Variant("(ia{sv}av)", (item_id, props, []))
                )
                children.append(child)
            return (0, {}, children)
        else:
            for item_id, label, action in self._menu_items:
                if item_id == parent_id:
                    props = self._item_properties(item_id, label, action)
                    return (item_id, props, [])
            return (parent_id, {}, [])

    # ── actions ──────────────────────────────────────────────────────

    def _activate_window(self):
        """Show / raise the application window."""
        win = self._app.get_active_window()
        if win:
            win.present()
        else:
            self._app.activate()
        return False

    def _handle_menu_click(self, item_id):
        action_map = {item[0]: item[2] for item in self._menu_items}
        action = action_map.get(item_id)
        if action == "show":
            self._activate_window()
        elif action == "toggle-proxy":
            win = self._app.get_active_window()
            if win and hasattr(win, "proxy_button_handler"):
                win.proxy_button_handler(win.proxy_button)
        elif action == "quit":
            self._app.quit()
        return False
