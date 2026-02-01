import subprocess
import socket
import time
import os
import signal
import shutil
import re
from typing import Optional, List


class SshMethods:
    """Minimal SSH helpers using the system `ssh` binary (no Paramiko).

    Use `start_system_ssh_socks` to create a local SOCKS5 proxy via
    `ssh -D`. Returns the `subprocess.Popen` object so the caller can
    manage/terminate the process.
    """
    local_address: str = '127.0.0.1'
    local_port: int = 1080


    def start_vpn(self, user_at_host: str, local_port: int = local_port, bind_address: str = local_address, key_file: Optional[str] = None, background: bool = True, extra_options: Optional[list] = None) -> Optional[subprocess.Popen]:
        """Start a system `ssh -D` SOCKS proxy to `user@host`.

        Args:
            user_at_host: string like 'user@example.com' or 'user@1.2.3.4'
            local_port: local port for SOCKS proxy (default 1080)
            bind_address: which address to bind locally (default 127.0.0.1)
            key_file: optional path to private key (passed with -i)
            background: whether to pass `-f` to ssh (background)
            extra_options: list of extra ssh args

        Returns:
            subprocess.Popen instance or None on failure.
        """
        # If something is already listening on the port, try to kill it first
        if self._is_port_in_use(bind_address, local_port):
            self._kill_process_on_port(local_port)

        cmd = ['ssh', '-D', f'{bind_address}:{local_port}', '-N']
        if background:
            cmd.append('-f')
        cmd += ['-o', 'ExitOnForwardFailure=yes']
        if key_file:
            cmd += ['-i', key_file]
        if extra_options:
            cmd += extra_options
        cmd.append(user_at_host)

        try:
            p = subprocess.Popen(cmd)
            return p
        except FileNotFoundError:
            print("ssh binary not found on PATH")
            return None
        except Exception as exc:
            print(f"Failed to start ssh process: {exc}")
            return None

    def _is_port_in_use(self, host: str, port: int, timeout: float = 0.5) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def _kill_process_on_port(self, port: int) -> List[int]:
        """Try to find and terminate processes listening on `port`.

        Uses `lsof` if available, otherwise falls back to parsing `ss` output.
        Returns list of killed PIDs (may be empty).
        """
        pids: List[int] = []
        # Prefer lsof if present
        if shutil.which('lsof'):
            try:
                out = subprocess.check_output(['lsof', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'], text=True)
                for line in out.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        pid = int(line)
                        pids.append(pid)
                    except ValueError:
                        continue
            except subprocess.CalledProcessError:
                pass
        elif shutil.which('ss'):
            try:
                out = subprocess.check_output(['ss', '-ltnp'], text=True, stderr=subprocess.DEVNULL)
                # lines contain something like: LISTEN 0      128        127.0.0.1:1080       *:*    users:("ssh",pid=1234,fd=3)
                for line in out.splitlines():
                    if f':{port} ' in line or f':{port}\n' in line or f':{port}\t' in line:
                        m = re.search(r'pid=(\d+)', line)
                        if m:
                            try:
                                pid = int(m.group(1))
                                pids.append(pid)
                            except ValueError:
                                pass
            except subprocess.CalledProcessError:
                pass

        # Attempt to terminate found pids
        killed: List[int] = []
        for pid in set(pids):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except PermissionError:
                print(f"No permission to kill PID {pid}")
                continue
            # wait briefly for process to exit
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                except OSError:
                    killed.append(pid)
                    break
                time.sleep(0.2)
            else:
                # force kill
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed.append(pid)
                except Exception:
                    print(f"Failed to kill PID {pid}")
        if killed:
            print(f"Killed processes on port {port}: {killed}")
        return killed

    def stop_vpn(self) -> None:
        """Terminate the Popen started by `start_vpn`.

        This attempts a graceful terminate(), then kill() if needed.
        """
        if self._is_port_in_use(self.local_address, self.local_port):
            self._kill_process_on_port(self.local_port)

a = SshMethods()
a.start_vpn('vpnuser@192.168.122.148', local_port=1080, bind_address='127.0.0.1', key_file='~/.ssh/githubSsh', background=True, extra_options=None)
# a.stop_vpn()