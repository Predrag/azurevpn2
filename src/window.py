import subprocess
import sys
import logging
import os
from gi.repository import Adw, Gtk, GLib
from .proxy_state import ProxyState
from .ssh_methods import SshMethods


@Gtk.Template(resource_path="/org/gnome/azurevpn/window.ui")
class AzurevpnWindow(Adw.ApplicationWindow):
    __gtype_name__ = "AzurevpnWindow"

    # label = Gtk.Template.Child()
    zapni_vpn_button: Gtk.Button = Gtk.Template.Child()
    vypni_vpn_button: Gtk.Button = Gtk.Template.Child()
    proxy_button: Gtk.Button = Gtk.Template.Child()
    log_view: Gtk.TextView = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.zapni_vpn_button.connect("clicked", self.connect_to_ssh)
        self.vypni_vpn_button.connect("clicked", self.disconnect_ssh)
        self.proxy_button.connect("clicked", self.proxy_button_handler)
        # Setup logging to the text view
        self._setup_ui_logging()
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
                self.logger.info("Proxy started")
                # Zmen farbu tlaidla na modrú
                self.proxy_button.remove_css_class("destructive-action")
                self.proxy_button.add_css_class("suggested-action")
                self.proxy_button.set_label("Vypnuť Proxy")
            else:
                self.logger.info(f"Proxy state is {current} — stopping proxy")
                # Vypni proxy
                self.proxy_state.proxy_stopped()
                self.logger.info("Proxy stopped")
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

    def connect_to_ssh(self, button):
        ssh = SshMethods()
        client = ssh.start_vpn(
            "vpnuser@192.168.122.148",
            local_port=1080,
            bind_address="127.0.0.1",
            key_file="~/.ssh/githubSsh",
            background=True,
            extra_options=None,
        )
        print(client)
        return client

    def disconnect_ssh(self, button):
        ssh = SshMethods()
        client = ssh.stop_vpn()
        print(client)
        return client
