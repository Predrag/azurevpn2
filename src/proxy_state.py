import subprocess

class ProxyState:
    
    check_command = [
                "flatpak-spawn", 
                "--host", 
                "gsettings", 
                "get", 
                "org.gnome.system.proxy", 
                "mode"
            ]

    def __init__(self):
        self.current_state = subprocess.run(self.check_command, capture_output=True, text=True)

    def proxy_started(self):
        command_start = [
            "flatpak-spawn", 
            "--host", 
            "gsettings", 
            "set", 
            "org.gnome.system.proxy", 
            "mode", 
            "manual"
        ]
        subprocess.run(command_start, capture_output=True, text=True)
    
    def proxy_stopped(self):
        command_stop = [
                "flatpak-spawn", 
                "--host", 
                "gsettings", 
                "set", 
                "org.gnome.system.proxy", 
                "mode", 
                "none"
            ]
        subprocess.run(command_stop, capture_output=True, text=True)
