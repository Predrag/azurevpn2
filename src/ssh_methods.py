import subprocess
import socket
import threading
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

    def __init__(self):
        # track background process or last found PIDs so stop_vpn can terminate
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._last_pids: List[int] = []

    def start_vpn(self, user_at_host: str, local_port: int = local_port, bind_address: str = local_address, key_file: Optional[str] = None, background: bool = False, extra_options: Optional[list] = None, nonblocking: bool = True):
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
            # Delegate actual start logic to internal implementation so GUI can call non-blocking
        if nonblocking:
            t = threading.Thread(target=self._start_vpn_impl, args=(user_at_host, local_port, bind_address, key_file, background, extra_options), daemon=True)
            t.start()
            self._thread = t
            return t
        else:
            return self._start_vpn_impl(user_at_host, local_port, bind_address, key_file, background, extra_options)

    def _is_port_in_use(self, host: str, port: int, timeout: float = 0.5) -> bool:
        # First try a local socket check (works when process is visible inside sandbox)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            pass

        # If running inside Flatpak, try checking the host network namespace via flatpak-spawn
        if shutil.which('flatpak-spawn'):
            try:
                out = subprocess.check_output(['flatpak-spawn', '--host', 'ss', '-ltn'], text=True, stderr=subprocess.DEVNULL)
                for line in out.splitlines():
                    if f':{port} ' in line or f':{port}\n' in line or f':{port}\t' in line:
                        return True
            except Exception:
                pass

        # fallback: no listener detected
        return False

    def _kill_process_on_port(self, port: int) -> List[int]:
        """Try to find and terminate processes listening on `port`.

        Uses `lsof` if available, otherwise falls back to parsing `ss` output.
        Returns list of killed PIDs (may be empty).
        """
        # Find PIDs listening on port (host via flatpak-spawn or local tools)
        pids: List[int] = self._get_pids_on_port(port)
        if pids:
            print(f"Found PIDs to kill on port {port}: {pids}")

        # Attempt to terminate found pids
        killed: List[int] = []
        for pid in set(pids):
            if shutil.which('flatpak-spawn'):
                # ask host to send TERM, then KILL if needed
                try:
                    r = subprocess.run(['flatpak-spawn', '--host', 'kill', '-TERM', str(pid)], check=False)
                    if r.returncode != 0:
                        print(f"Failed to send TERM to PID {pid} via flatpak-spawn (rc={r.returncode})")
                except Exception as e:
                    print(f"flatpak-spawn kill error for PID {pid}: {e}")
                    continue

                # wait for process to disappear on host
                for _ in range(10):
                    try:
                        out = subprocess.run(['flatpak-spawn', '--host', 'ps', '-p', str(pid)], capture_output=True, text=True)
                        # ps returns non-zero if process not found
                        if out.returncode != 0:
                            killed.append(pid)
                            break
                    except Exception:
                        killed.append(pid)
                        break
                    time.sleep(0.2)
                else:
                    # force kill via host
                    try:
                        r = subprocess.run(['flatpak-spawn', '--host', 'kill', '-KILL', str(pid)], check=False)
                        if r.returncode == 0:
                            killed.append(pid)
                        else:
                            print(f"Failed to kill PID {pid} via flatpak-spawn (rc={r.returncode})")
                    except Exception as e:
                        print(f"flatpak-spawn kill -KILL error for PID {pid}: {e}")
            else:
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

    def _get_pids_on_port(self, port: int) -> List[int]:
        """Return list of PIDs listening on `port` (does not kill).

        Tries host via flatpak-spawn first, then local lsof/ss.
        """
        pids: List[int] = []
        if shutil.which('flatpak-spawn'):
            try:
                out = subprocess.check_output(['flatpak-spawn', '--host', 'lsof', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'], text=True)
                for line in out.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        pids.append(int(line))
                    except ValueError:
                        continue
            except Exception:
                pass
            if not pids:
                try:
                    out = subprocess.check_output(['flatpak-spawn', '--host', 'ss', '-ltnp'], text=True, stderr=subprocess.DEVNULL)
                    for line in out.splitlines():
                        if f':{port} ' in line or f':{port}\n' in line or f':{port}\t' in line:
                            m = re.search(r'pid=(\d+)', line)
                            if m:
                                try:
                                    pids.append(int(m.group(1)))
                                except ValueError:
                                    pass
                except Exception:
                    pass

        if not pids:
            if shutil.which('lsof'):
                try:
                    out = subprocess.check_output(['lsof', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'], text=True)
                    for line in out.splitlines():
                        try:
                            pids.append(int(line.strip()))
                        except Exception:
                            pass
                except Exception:
                    pass
            elif shutil.which('ss'):
                try:
                    out = subprocess.check_output(['ss', '-ltnp'], text=True, stderr=subprocess.DEVNULL)
                    for line in out.splitlines():
                        if f':{port} ' in line or f':{port}\n' in line or f':{port}\t' in line:
                            m = re.search(r'pid=(\d+)', line)
                            if m:
                                try:
                                    pids.append(int(m.group(1)))
                                except ValueError:
                                    pass
                except Exception:
                    pass

        return pids

    def stop_vpn(self) -> None:
        """Terminate the Popen started by `start_vpn`.

        This attempts a graceful terminate(), then kill() if needed.
        """
        # If we started a background process and have its Popen, terminate it
        if getattr(self, '_proc', None):
            proc = self._proc
            try:
                proc.terminate()
                proc.wait(timeout=5.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                self._proc = None

        # Otherwise, kill any process listening on the configured local port
        if self._is_port_in_use(self.local_address, self.local_port):
            self._kill_process_on_port(self.local_port)

        # also try to kill any last-known pids
        if getattr(self, '_last_pids', None):
            for pid in list(self._last_pids):
                try:
                    if shutil.which('flatpak-spawn'):
                        subprocess.run(['flatpak-spawn', '--host', 'kill', '-TERM', str(pid)], check=False)
                    else:
                        os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            self._last_pids = []

    def _start_vpn_impl(self, user_at_host: str, local_port: int, bind_address: str, key_file: Optional[str], background: bool, extra_options: Optional[list]) -> Optional[subprocess.Popen]:
        # If running inside Flatpak, avoid using -f (background) because
        # backgrounding breaks process visibility from the sandbox.
        is_flatpak = bool(os.getenv('FLATPAK_SANDBOX') or os.getenv('FLATPAK_ID') or shutil.which('flatpak-spawn'))
        if is_flatpak:
            background = False
            print("Flatpak detected: forcing foreground ssh and using flatpak-spawn for host ops")

        # If something is already listening on the port, try to kill it first
        if self._is_port_in_use(bind_address, local_port):
            self._kill_process_on_port(local_port)

        cmd = ['ssh', '-D', f'{bind_address}:{local_port}', '-N']
        if background:
            cmd.append('-f')
        cmd += ['-o', 'ExitOnForwardFailure=yes']
        if key_file:
            # Expand ~ to user's home directory (shell doesn't do this in subprocess)
            expanded_key = os.path.expanduser(key_file)
            cmd += ['-i', expanded_key]
        if extra_options:
            cmd += extra_options
        cmd.append(user_at_host)

        # If background is False we run and wait (so we can detect bind errors).
        try:
            if not background:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    print(f"ssh started (foreground): {cmd}")
                    # record any pids listening on the port for later stop
                    try:
                        pids = self._get_pids_on_port(local_port)
                        self._last_pids = pids
                    except Exception:
                        pass
                    return None
                else:
                    stderr = (res.stderr or '').strip()
                    print(stderr)
                    if 'Address already in use' in stderr or 'cannot listen to port' in stderr:
                        # try to kill whatever is using the port on host and retry once
                        print("Port appears in use; attempting to kill conflicting process on port", local_port)
                        self._kill_process_on_port(local_port)
                        # wait briefly for port to free up
                        for i in range(10):
                            if not self._is_port_in_use(bind_address, local_port):
                                break
                            time.sleep(0.2)
                        else:
                            print("Port still in use after kill attempts")

                        # retry once without background
                        retry = subprocess.run(cmd, capture_output=True, text=True)
                        if retry.returncode == 0:
                            print("ssh started after killing conflicting process")
                            try:
                                pids = self._get_pids_on_port(local_port)
                                self._last_pids = pids
                            except Exception:
                                pass
                            return None
                        else:
                            print(f"ssh failed after retry: {retry.stderr}")
                            return None
                    else:
                        print(f"ssh failed: {stderr}")
                        return None
            else:
                p = subprocess.Popen(cmd)
                # track background process so stop_vpn can terminate it
                self._proc = p
                return p
        except FileNotFoundError:
            print("ssh binary not found on PATH")
            return None
        except Exception as exc:
            print(f"Failed to start ssh process: {exc}")
            return None