import subprocess
import sys
import logging
import os
from gi.repository import Adw, Gtk, GLib, Gio
from .proxy_state import ProxyState
from .ssh_methods import SshMethods
from .connections_manager import ConnectionsManager


@Gtk.Template(resource_path="/org/gnome/azurevpn/window.ui")
class AzurevpnWindow(Adw.ApplicationWindow):
    __gtype_name__ = "AzurevpnWindow"

    # UI Components
    zapni_vpn_button: Gtk.Button = Gtk.Template.Child()
    vypni_vpn_button: Gtk.Button = Gtk.Template.Child()
    proxy_button: Gtk.Button = Gtk.Template.Child()
    log_view: Gtk.TextView = Gtk.Template.Child()

    # Connection form components
    connections_combo: Adw.ComboRow = Gtk.Template.Child()
    connection_name_entry: Adw.EntryRow = Gtk.Template.Child()
    user_entry: Adw.EntryRow = Gtk.Template.Child()
    host_entry: Adw.EntryRow = Gtk.Template.Child()
    port_entry: Adw.EntryRow = Gtk.Template.Child()
    key_file_entry: Adw.EntryRow = Gtk.Template.Child()
    local_port_entry: Adw.EntryRow = Gtk.Template.Child()
    save_connection_button: Gtk.Button = Gtk.Template.Child()
    delete_connection_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Setup logging first
        self._setup_ui_logging()

        # Initialize connections manager
        self.connections_manager = ConnectionsManager()

        # Connect button signals
        self.zapni_vpn_button.connect("clicked", self.connect_to_ssh)
        self.vypni_vpn_button.connect("clicked", self.disconnect_ssh)
        self.proxy_button.connect("clicked", self.proxy_button_handler)
        self.save_connection_button.connect("clicked", self.save_connection)
        self.delete_connection_button.connect("clicked", self.delete_connection)

        # Setup connections combo box
        self._setup_connections_combo()

        # Hide window instead of destroying it when user clicks X
        self.connect("close-request", self._on_close_request)

        # Create SSH instance that persists across start/stop calls
        self.ssh = SshMethods()

        # start monitor to detect external changes to proxy gsettings
        try:
            self._start_gsettings_monitor()
        except Exception:
            # not fatal; continue without monitor
            self.logger.exception("Nepodarilo sa spustiť GSettings monitor")
        # ensure UI matches current proxy state on startup
        try:
            self._update_proxy_ui_from_state()
        except Exception:
            self.logger.exception("Nepodarilo sa inicializovať stav proxy UI")

    def _setup_ui_logging(self):
        buf = self.log_view.get_buffer()
        logger = logging.getLogger("azurevpn")
        logger.setLevel(logging.DEBUG)

        class GtkHandler(logging.Handler):
            def __init__(self, buffer):
                super().__init__()
                self.buffer = buffer

            def emit(self, record):
                msg = self.format(record) + "\n"
                # append in main thread
                GLib.idle_add(self._append, msg)

            def _append(self, msg):
                end = self.buffer.get_end_iter()
                self.buffer.insert(end, msg)
                return False

        handler = GtkHandler(buf)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        )
        logger.addHandler(handler)
        # expose logger to instance methods
        self.logger = logger

        # redirect stdout/stderr to logger
        class StreamToLogger:
            def __init__(self, log_func):
                self.log_func = log_func

            def write(self, message):
                message = message.rstrip("\n")
                if message:
                    self.log_func(message)

            def flush(self):
                pass

        sys.stdout = StreamToLogger(lambda m: logger.info(m))
        sys.stderr = StreamToLogger(lambda m: logger.error(m))

    def proxy_button_handler(self, button):
        try:
            # Zisti stav gsettings proxy pred spustením príkazu
            self.proxy_state = ProxyState()
            current = self.proxy_state.current_state.stdout.strip()
            if current == "'none'":
                self.logger.info("Proxy state is 'none' — starting proxy")
                # Zapni proxy
                self.proxy_state.proxy_started()
                self.logger.info("Proxy GSettings set to 'manual'")
                # Zmen farbu tlaidla na modrú
                self.proxy_button.remove_css_class("destructive-action")
                self.proxy_button.add_css_class("suggested-action")
                self.proxy_button.set_label("Vypnuť Proxy")
            else:
                self.logger.info(f"Proxy state is {current} — stopping proxy")
                # Vypni proxy
                self.proxy_state.proxy_stopped()
                self.logger.info("Proxy GSettings set to 'none'")
                # Zmen farbu tlaidla na predvolenú (odstráni modrú farbu)
                self.proxy_button.remove_css_class("suggested-action")
                self.proxy_button.add_css_class("destructive-action")
                self.proxy_button.set_label("Zapnuť Proxy")
        except Exception as e:
            # log exception to UI log
            try:
                self.logger.exception(f"Kritická chyba pri prepínaní proxy: {e}")
            except Exception:
                print(f"Kritická chyba pri prepínaní proxy: {e}")

    def _update_proxy_ui_from_state(self):
        try:
            state = ProxyState()
            current = state.current_state.stdout.strip()
            if current == "'none'":
                # proxy is stopped
                self.proxy_button.remove_css_class("suggested-action")
                self.proxy_button.add_css_class("destructive-action")
                self.proxy_button.set_label("Zapnuť Proxy")
                proxy_active = False
            else:
                # proxy is running
                self.proxy_button.remove_css_class("destructive-action")
                self.proxy_button.add_css_class("suggested-action")
                self.proxy_button.set_label("Vypnuť Proxy")
                proxy_active = True
            # Update tray icon menu label
            try:
                tray = getattr(self.get_application(), "_tray", None)
                if tray:
                    tray.update_proxy_label(proxy_active)
            except Exception:
                pass
        except Exception:
            # best-effort, don't crash UI
            self.logger.exception("Chyba pri aktualizácii UI stavu proxy")

    def _start_gsettings_monitor(self):
        # use flatpak-spawn --host to monitor host gsettings changes
        args = [
            "flatpak-spawn",
            "--host",
            "gsettings",
            "monitor",
            "org.gnome.system.proxy",
            "mode",
        ]
        # start subprocess with line-buffered text output
        self._gsettings_proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        fd = self._gsettings_proc.stdout.fileno()
        try:
            os.set_blocking(fd, False)
        except Exception:
            pass
        self._gsettings_channel = GLib.IOChannel.unix_new(fd)
        GLib.io_add_watch(
            self._gsettings_channel,
            GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
            self._on_gsettings_output,
        )
        # ensure we stop the child when window is destroyed
        try:
            self.connect("destroy", lambda w: self._stop_gsettings_monitor())
        except Exception:
            pass

    def _on_gsettings_output(self, channel, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            return False
        try:
            status, line, length, _terminator = channel.read_line()
            if status != GLib.IOStatus.NORMAL or line is None:
                return True
            line = line.strip()
            if line:
                # schedule UI update in main loop
                GLib.idle_add(self._handle_gsettings_change, line)
        except Exception as e:
            try:
                self.logger.exception(f"Chyba pri čítaní GSettings monitora: {e}")
            except Exception:
                pass
        return True

    def _handle_gsettings_change(self, line):
        # simply re-read the current proxy state and update UI
        try:
            self.logger.info(f"GSettings change detected: {line}")
        except Exception:
            pass
        try:
            self._update_proxy_ui_from_state()
        except Exception:
            self.logger.exception("Chyba pri spracovaní zmeny GSettings")
        return False

    def _stop_gsettings_monitor(self):
        try:
            if getattr(self, "_gsettings_proc", None):
                try:
                    self._gsettings_proc.terminate()
                except Exception:
                    pass
                self._gsettings_proc = None
        except Exception:
            pass

    def _on_close_request(self, window):
        """Hide the window instead of closing the app."""
        self.set_visible(False)
        return True  # stop default close/destroy

    def start_proxy(self):
        """Start proxy if not already running."""
        try:
            state = ProxyState()
            current = state.current_state.stdout.strip()
            if current == "'none'":
                self.proxy_button_handler(self.proxy_button)
        except Exception as e:
            self.logger.exception(f"Chyba pri zapínaní proxy: {e}")

    def stop_proxy(self):
        """Stop proxy if running."""
        try:
            state = ProxyState()
            current = state.current_state.stdout.strip()
            if current != "'none'":
                self.proxy_button_handler(self.proxy_button)
        except Exception as e:
            self.logger.exception(f"Chyba pri vypínaní proxy: {e}")

    def _setup_connections_combo(self):
        """Setup the connections combo box with saved connections."""
        connections = self.connections_manager.load_connections()

        # Create string list model
        string_list = Gtk.StringList()
        string_list.append("-- Nové pripojenie --")

        for conn in connections:
            name = conn.get("name", "Bez názvu")
            string_list.append(name)

        self.connections_combo.set_model(string_list)

        # Connect to selection change BEFORE setting selected index
        self.connections_combo.connect("notify::selected", self._on_connection_selected)

        # Try to select last used connection
        last_used = self.connections_manager.get_last_used()
        selected_index = 0

        if last_used:
            for i in range(string_list.get_n_items()):
                if string_list.get_string(i) == last_used:
                    selected_index = i
                    break

        # Set selected index - this will trigger _on_connection_selected
        self.connections_combo.set_selected(selected_index)

    def _on_connection_selected(self, combo, _param):
        """Handle connection selection from combo box."""
        selected = combo.get_selected()
        if selected == 0:
            # "Nové pripojenie" - clear form
            self.connection_name_entry.set_text("")
            self.user_entry.set_text("")
            self.host_entry.set_text("")
            self.port_entry.set_text("22")
            self.key_file_entry.set_text("~/.ssh/id_rsa")
            self.local_port_entry.set_text("1080")
            return

        # Load selected connection
        connections = self.connections_manager.load_connections()
        if selected - 1 < len(connections):
            conn = connections[selected - 1]
            self.connection_name_entry.set_text(conn.get("name", ""))
            self.user_entry.set_text(conn.get("user", ""))
            self.host_entry.set_text(conn.get("host", ""))
            self.port_entry.set_text(str(conn.get("port", 22)))
            self.key_file_entry.set_text(conn.get("key_file", "~/.ssh/id_rsa"))
            self.local_port_entry.set_text(str(conn.get("local_port", 1080)))

    def save_connection(self, button):
        """Save current connection settings."""
        name = self.connection_name_entry.get_text().strip()
        user = self.user_entry.get_text().strip()
        host = self.host_entry.get_text().strip()

        if not name or not user or not host:
            self.logger.error("Názov, používateľ a adresa sú povinné")
            return

        try:
            port = int(self.port_entry.get_text().strip())
            local_port = int(self.local_port_entry.get_text().strip())
        except ValueError:
            self.logger.error("Port musí byť číslo")
            return

        key_file = self.key_file_entry.get_text().strip()

        # Check if updating existing connection
        connections = self.connections_manager.load_connections()
        existing = any(c.get("name") == name for c in connections)

        if existing:
            success = self.connections_manager.update_connection(
                name, name, user, host, port, key_file, local_port
            )
            msg = "Pripojenie aktualizované" if success else "Chyba pri aktualizácii"
        else:
            success = self.connections_manager.add_connection(
                name, user, host, port, key_file, local_port
            )
            msg = "Pripojenie uložené" if success else "Chyba pri ukladaní"

        if success:
            self.logger.info(msg)
            self._setup_connections_combo()
            # Select the saved connection
            model = self.connections_combo.get_model()
            for i in range(model.get_n_items()):
                if model.get_string(i) == name:
                    self.connections_combo.set_selected(i)
                    break
        else:
            self.logger.error(msg)

    def delete_connection(self, button):
        """Delete selected connection."""
        name = self.connection_name_entry.get_text().strip()
        if not name:
            self.logger.error("Vyberte pripojenie na zmazanie")
            return

        success = self.connections_manager.remove_connection(name)
        if success:
            self.logger.info(f"Pripojenie '{name}' zmazané")
            self._setup_connections_combo()
        else:
            self.logger.error(f"Chyba pri mazaní pripojenia '{name}'")

    def connect_to_ssh(self, button):
        """Connect to SSH using current form values."""
        user = self.user_entry.get_text().strip()
        host = self.host_entry.get_text().strip()

        if not user or not host:
            self.logger.error("Používateľ a adresa sú povinné")
            return

        try:
            port = int(self.port_entry.get_text().strip())
            local_port = int(self.local_port_entry.get_text().strip())
        except ValueError:
            self.logger.error("Port musí byť číslo")
            return

        key_file = self.key_file_entry.get_text().strip()
        ssh_target = f"{user}@{host}"

        self.logger.info(f"Pripájam sa na {ssh_target}...")

        ssh = SshMethods()
        client = ssh.start_vpn(
            ssh_target,
            local_port=local_port,
            bind_address="127.0.0.1",
            key_file=key_file,
            background=True,
            extra_options=None,
        )
        print(client)

        # Save last used connection if a named connection is selected
        connection_name = self.connection_name_entry.get_text().strip()
        if connection_name:
            self.connections_manager.set_last_used(connection_name)

        # Update tray overlay
        try:
            tray = getattr(self.get_application(), "_tray", None)
            if tray:
                tray.update_vpn_state(True)
        except Exception:
            pass
        return client

    def disconnect_ssh(self, button):
        ssh = SshMethods()
        client = ssh.stop_vpn()
        print(client)
        # Update tray overlay
        try:
            tray = getattr(self.get_application(), "_tray", None)
            if tray:
                tray.update_vpn_state(False)
        except Exception:
            pass
        return client
