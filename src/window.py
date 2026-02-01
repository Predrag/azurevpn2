import subprocess
from gi.repository import Adw, Gtk
from .proxy_state import ProxyState
from .ssh_methods import SshMethods

@Gtk.Template(resource_path='/org/gnome/gsettingstest/window.ui')
class GsettingstestWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'GsettingstestWindow'

    # label = Gtk.Template.Child()
    zapni_vpn_button: Gtk.Button = Gtk.Template.Child()
    vypni_vpn_button: Gtk.Button = Gtk.Template.Child()
    proxy_button: Gtk.Button = Gtk.Template.Child()
    stop_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.zapni_vpn_button.connect("clicked", self.connect_to_ssh)
        self.vypni_vpn_button.connect("clicked", self.disconnect_ssh)
        self.proxy_button.connect("clicked", self.proxy_button_handler)
        self.stop_button.connect("clicked", self.connect_to_ssh)

    def proxy_button_handler(self, button):
        try:
            # Zisti stav gsettings proxy pred spustením príkazu
            self.proxy_state = ProxyState()
            
            if self.proxy_state.current_state.stdout.strip() == "'none'":
                 
                # Zapni proxy
                self.proxy_state.proxy_started()
                # Zmen farbu tlaidla na modrú
                self.proxy_button.remove_css_class("destructive-action")
                self.proxy_button.add_css_class("suggested-action")
                self.proxy_button.set_label("Vypnuť Proxy")
            else:
                # Vypni proxy
                self.proxy_state.proxy_stopped()
                # Zmen farbu tlaidla na predvolenú (odstráni modrú farbu)
                self.proxy_button.remove_css_class("suggested-action")
                self.proxy_button.add_css_class("destructive-action")
                self.proxy_button.set_label("Zapnuť Proxy")
        except Exception as e:
            print(f"Kritická chyba: {e}")

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