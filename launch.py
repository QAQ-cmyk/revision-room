"""Open this installation of the local review desk, reusing its running instance."""
import ctypes
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
INSTALL = hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:16]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def matches(url):
    try:
        with OPENER.open(url + "/api/health", timeout=.6) as response:
            return json.load(response).get("installId") == INSTALL
    except (OSError, ValueError):
        return False


def open_desk():
    free = None
    for port in range(4185, 4195):
        url = f"http://127.0.0.1:{port}"
        with socket.socket() as sock:
            sock.settimeout(.15)
            if sock.connect_ex(("127.0.0.1", port)):
                if free is None:
                    free = port
            elif matches(url):
                return url
    if free is None:
        raise RuntimeError("本机端口 4185 至 4194 都已被占用。")
    url = f"http://127.0.0.1:{free}"
    with (ROOT / "server.log").open("ab") as log:
        proc = subprocess.Popen([sys.executable, str(ROOT / "server.py"), "--port", str(free)],
                                cwd=ROOT, stdout=log, stderr=log, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    for _ in range(120):
        if matches(url):
            return url
        if proc.poll() is not None:
            break
        time.sleep(.25)
    raise RuntimeError("请查看修订室目录中的 server.log。")


if __name__ == "__main__":
    try:
        address = open_desk()
        if "--no-open" in sys.argv:
            print(address)
        else:
            webbrowser.open(address)
    except (RuntimeError, OSError) as error:
        if sys.platform == "win32" and "--no-open" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, str(error), "修订室没有启动", 16)
        raise SystemExit(str(error))
