"""Launch the Terrain Heightmap Generator in its own environment.

    python start.py          (server.bat does the same on Windows)

What it does:
  1. Creates ``terrain-venv`` on first run and installs ``requirements.txt`` into
     it — the environment with all requirements.
  2. Starts ``server.py`` with that venv's interpreter: the switch to the
     environment.
  3. Port choice: ``HMG_PORT`` if you set one explicitly, otherwise the
     default 8765 when it is free, otherwise a random empty port so an
     already-running session is never disturbed.
  4. Prints the URL once the server answers /api/health.

``python server.py`` on its own still defaults to 8765 (the test suite
depends on that).
"""

import hashlib
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / "terrain-venv"
VENV_PY = VENV / ("Scripts" if os.name == "nt" else "bin") / (
    "python.exe" if os.name == "nt" else "python"
)
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".requirements.sha256"
DEFAULT_PORT = 8765


def ensure_environment():
    """Create the terrain-venv environment once, install requirements when they change.

    ``--system-site-packages`` keeps packages already installed on the
    machine visible, so an offline first run still succeeds; pip still
    installs anything that is missing straight into the venv.
    """
    if not VENV_PY.exists():
        print(f"[env] creating {VENV.name} ...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(VENV)],
            check=True,
        )
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    stamp = STAMP.read_text().strip() if STAMP.exists() else ""
    if stamp != digest:
        print("[env] installing requirements ...", flush=True)
        subprocess.run(
            [str(VENV_PY), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
            check=True,
        )
        STAMP.write_text(digest)
    print("[env] ready (requirements satisfied)", flush=True)


def _port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def choose_port():
    """HMG_PORT if explicitly set, else the default if empty, else random."""
    explicit = os.environ.get("HMG_PORT")
    if explicit:
        return int(explicit), "from HMG_PORT"
    if _port_is_free(DEFAULT_PORT):
        return DEFAULT_PORT, "default"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1], "default busy, picked a free port"


def wait_for_health(url, proc, attempts=150):
    for _ in range(attempts):
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.2)
    return False


def main():
    ensure_environment()
    port, why = choose_port()
    print(f"[server] starting on port {port} ({why})", flush=True)
    env = dict(os.environ, HMG_PORT=str(port))
    proc = subprocess.Popen(
        [str(VENV_PY), str(ROOT / "server.py")], cwd=str(ROOT), env=env
    )
    url = f"http://127.0.0.1:{port}"
    if not wait_for_health(url, proc):
        code = proc.poll()
        if code is None:
            proc.terminate()
        print("[server] failed to become healthy", flush=True)
        sys.exit(code if code is not None else 1)
    print(f"\nTerrain Heightmap Generator — {url}\n", flush=True)
    try:
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()
