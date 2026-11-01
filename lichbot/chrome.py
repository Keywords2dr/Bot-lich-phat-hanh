import socket
import subprocess
import time

from .models import BotError


class ChromeLauncher:
    def __init__(self, settings):
        self._settings = settings
        self._proc = None

    def _port_open(self):
        with socket.socket() as sock:
            sock.settimeout(1)
            try:
                sock.connect(("127.0.0.1", self._settings.debug_port))
                return True
            except OSError:
                return False

    def __enter__(self):
        if self._port_open():
            return self
        s = self._settings
        try:
            self._proc = subprocess.Popen(
                [
                    s.chrome_path,
                    f"--remote-debugging-port={s.debug_port}",
                    f"--user-data-dir={s.profile_dir}",
                    "--remote-allow-origins=*",
                ]
            )
        except OSError:
            raise BotError("Khong tim thay Chrome tai: " + s.chrome_path)
        for _ in range(30):
            if self._port_open():
                return self
            time.sleep(1)
        self._proc.terminate()
        self._proc = None
        raise BotError(f"Khong mo duoc Chrome cua bot (cong {s.debug_port} khong mo)")

    def __exit__(self, exc_type, exc, tb):
        if self._proc:
            self._proc.terminate()
        return False
