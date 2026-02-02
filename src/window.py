import subprocess
import sys
import logging
from gi.repository import Adw, Gtk, GLib
from .proxy_state import ProxyState
from .ssh_methods import SshMethods

@Gtk.Template(resource_path='/org/gnome/azurevpn/window.ui')
class AzurevpnWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'AzurevpnWindow'

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

    def _setup_ui_logging(self):
        buf = self.log_view.get_buffer()
        logger = logging.getLogger('azurevpn')
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
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(handler)
        # expose logger to instance methods
        self.logger = logger

        # redirect stdout/stderr to logger
        class StreamToLogger:
            def __init__(self, log_func):
                self.log_func = log_func

            def write(self, message):
                message = message.rstrip('\n')
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

    def connect_to_ssh(self, button):
        ssh = SshMethods()
        client = ssh.start_vpn('vpnuser@192.168.122.148', local_port=1080, bind_address='127.0.0.1', key_file='~/.ssh/githubSsh', background=True, extra_options=None)
        print(client)
        return client
    
    def disconnect_ssh(self, button):
        ssh = SshMethods()
        client = ssh.stop_vpn()
        print(client)
        return client