import json
import os
from pathlib import Path
import logging


class ConnectionsManager:
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "azurevpn"
        self.config_file = self.config_dir / "connections.json"
        self.logger = logging.getLogger("azurevpn")
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Nepodarilo sa vytvoriť config adresár: {e}")

    def load_connections(self):
        """Load connections from config file."""
        if not self.config_file.exists():
            return []

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("connections", [])
        except Exception as e:
            self.logger.error(f"Chyba pri načítaní pripojení: {e}")
            return []

    def save_connections(self, connections):
        """Save connections to config file."""
        try:
            # Load existing data to preserve last_used
            data = {"connections": connections}
            if self.config_file.exists():
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        if "last_used" in existing_data:
                            data["last_used"] = existing_data["last_used"]
                except Exception:
                    pass

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Chyba pri ukladaní pripojení: {e}")
            return False

    def add_connection(self, name, user, host, port=22, key_file="~/.ssh/id_rsa",
                      local_port=1080, bind_address="127.0.0.1"):
        """Add a new connection."""
        connections = self.load_connections()

        # Check if name already exists
        for conn in connections:
            if conn.get("name") == name:
                self.logger.warning(f"Pripojenie s názvom '{name}' už existuje")
                return False

        connection = {
            "name": name,
            "user": user,
            "host": host,
            "port": port,
            "key_file": key_file,
            "local_port": local_port,
            "bind_address": bind_address
        }

        connections.append(connection)
        return self.save_connections(connections)

    def remove_connection(self, name):
        """Remove a connection by name."""
        connections = self.load_connections()
        connections = [c for c in connections if c.get("name") != name]
        return self.save_connections(connections)

    def get_connection(self, name):
        """Get a connection by name."""
        connections = self.load_connections()
        for conn in connections:
            if conn.get("name") == name:
                return conn
        return None

    def update_connection(self, old_name, name, user, host, port=22,
                         key_file="~/.ssh/id_rsa", local_port=1080,
                         bind_address="127.0.0.1"):
        """Update an existing connection."""
        connections = self.load_connections()

        for i, conn in enumerate(connections):
            if conn.get("name") == old_name:
                connections[i] = {
                    "name": name,
                    "user": user,
                    "host": host,
                    "port": port,
                    "key_file": key_file,
                    "local_port": local_port,
                    "bind_address": bind_address
                }
                return self.save_connections(connections)

        return False

    def get_last_used(self):
        """Get the last used connection name."""
        if not self.config_file.exists():
            return None

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_used")
        except Exception as e:
            self.logger.error(f"Chyba pri načítaní posledného pripojenia: {e}")
            return None

    def set_last_used(self, name):
        """Set the last used connection name."""
        try:
            data = {"connections": self.load_connections(), "last_used": name}
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Chyba pri ukladaní posledného pripojenia: {e}")
            return False
