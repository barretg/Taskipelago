"""
Local host for the Taskipelago web client (UNIFY_PLAN section 2).

Serves the same static files as the hosted client from http://127.0.0.1, adds a
generated config.json (feature flags, launch info, per-run token) and a small
device-storage API, then opens a Chromium app-mode window (or the default
browser as a fallback) and lives as long as that window does.

Stdlib only.
"""
from __future__ import annotations

import http.client
import http.server
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import zipfile

PORT_FIRST = 38290
PORT_LAST = 38299
HEARTBEAT_TIMEOUT = 30.0
STARTUP_GRACE = 60.0
LOCK_POLL_SECONDS = 5.0
DETACH_WINDOW_SECONDS = 15.0
MAX_BODY_BYTES = 16 * 1024 * 1024
LEGACY_IMPORT_MARKER = "taskipelago_legacy_import_v1"

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MAC

# Hardcoded on purpose: mimetypes reads the Windows registry, which often maps
# .js to text/plain, and browsers then refuse to run ES modules.
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

NO_BROWSER_PROMPT = (
    "No Chromium-based browser (Chromium, Chrome, Edge, Brave) was found. The "
    "Taskipelago Client works best in one. Open it in your default browser instead?"
)


def _log(msg: str) -> None:
    print(f"[Taskipelago] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _user_dir() -> str:
    """Per-user state dir: Utils.user_path('taskipelago'), overridable for tests."""
    path = os.environ.get("TASKIPELAGO_STATE_DIR")
    if not path:
        try:
            import Utils
            path = Utils.user_path("taskipelago")
        except Exception:
            path = os.path.join(os.path.expanduser("~"), ".taskipelago")
    os.makedirs(path, exist_ok=True)
    return path


def _legacy_state_dirs() -> list:
    """Where the Tk client wrote its state: the process cwd, then Utils.user_path()."""
    dirs = [os.getcwd()]
    try:
        import Utils
        dirs.append(Utils.user_path())
    except Exception:
        pass
    return dirs


# ---------------------------------------------------------------------------
# Static files (unpacked world dir, or inside the .apworld zip)
# ---------------------------------------------------------------------------

class WebFiles:
    def __init__(self, module_file: str | None = None, package: str | None = None,
                 use_resources: bool = True) -> None:
        self._traversable = None
        self._dir = None
        self._zip = None
        self._zip_prefix = ""
        self._zip_lock = threading.Lock()

        here = os.path.dirname(os.path.abspath(module_file or __file__))
        package = __package__ if package is None else package
        local_dir = os.path.join(here, "web-client")
        if os.path.isdir(local_dir):
            self._dir = local_dir
            return

        if use_resources:
            try:
                from importlib.resources import files
                if package:
                    node = files(package) / "web-client"
                    if node.is_dir():
                        self._traversable = node
                        return
            except Exception:
                pass

        # zipimport without a resource reader: <archive>.apworld/<pkg>/webhost.py
        parts = here.replace("\\", "/").split("/")
        for i in range(len(parts), 0, -1):
            candidate = "/".join(parts[:i])
            if os.path.isfile(candidate) and zipfile.is_zipfile(candidate):
                self._zip = zipfile.ZipFile(candidate)
                inner = "/".join(parts[i:])
                self._zip_prefix = (inner + "/" if inner else "") + "web-client/"
                return

    def read(self, rel: str) -> bytes | None:
        """rel is a validated, forward-slash relative path."""
        if self._dir is not None:
            path = os.path.join(self._dir, *rel.split("/"))
            if not os.path.isfile(path):
                return None
            with open(path, "rb") as f:
                return f.read()
        if self._traversable is not None:
            node = self._traversable
            for seg in rel.split("/"):
                node = node / seg
            try:
                return node.read_bytes() if node.is_file() else None
            except OSError:
                return None
        if self._zip is not None:
            with self._zip_lock:
                try:
                    return self._zip.read(self._zip_prefix + rel)
                except KeyError:
                    return None
        return None


def safe_rel_path(raw_path: str) -> str | None:
    """Map a request path to a relative file path, or None if it must be rejected."""
    path = raw_path.split("?", 1)[0].split("#", 1)[0]
    if "\\" in path:
        return None
    path = urllib.parse.unquote(path)
    if "\\" in path or "\x00" in path or not path.startswith("/") or path.startswith("//"):
        return None
    rel = path[1:]
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    segs = rel.split("/")
    if any(s in ("", ".", "..") for s in segs) or ":" in segs[0]:
        return None
    return rel


# ---------------------------------------------------------------------------
# Device storage (UNIFY 3.2)
# ---------------------------------------------------------------------------

class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data = loaded
        except FileNotFoundError:
            pass
        except Exception as e:
            _log(f"could not read {path} ({e!r}); keeping a .bak copy and starting empty")
            try:
                shutil.copyfile(path, path + ".bak")
            except OSError:
                pass

    def snapshot_json(self) -> bytes:
        with self.lock:
            return json.dumps(self.data).encode("utf-8")

    def patch(self, set_values: dict, remove_keys: list) -> None:
        with self.lock:
            for k, v in set_values.items():
                self.data[k] = v
            for k in remove_keys:
                self.data.pop(k, None)
            self._write()

    def _write(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def migrate_legacy_state(storage: Storage, dirs: list) -> bool:
    """One-time import of Tk client state (UNIFY 3.3). Legacy files are never modified."""
    if storage.data.get(LEGACY_IMPORT_MARKER):
        return False

    def load(name: str) -> dict:
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        v = json.loads(f.read() or "{}")
                    if isinstance(v, dict):
                        return v
                except Exception:
                    continue
        return {}

    notify = load("taskipelago_notify_state.json")
    last = load("taskipelago_last_connection.json")
    updates: dict = {}

    for key, value in notify.items():
        if not isinstance(key, str):
            continue
        if key.startswith("v3::") and _is_int(value) and value >= 0:
            new_key = "taskipelago_notify_v3::" + key[len("v3::"):]
            current = storage.data.get(new_key)
            try:
                current_int = int(current) if current is not None else None
            except (TypeError, ValueError):
                current_int = None
            if current_int is None or value > current_int:
                updates[new_key] = value
        elif key.startswith("manual_v1::") and isinstance(value, dict):
            new_key = "taskipelago_manual_v1::" + key[len("manual_v1::"):]
            if new_key not in storage.data:
                updates[new_key] = {
                    n: c for n, c in value.items() if isinstance(n, str) and _is_int(c) and c > 0
                }

    if "taskipelago_last_conn" not in storage.data and (last.get("server") or last.get("slot")):
        updates["taskipelago_last_conn"] = {
            "server": str(last.get("server") or ""),
            "slot": str(last.get("slot") or ""),
        }

    updates[LEGACY_IMPORT_MARKER] = True
    storage.patch(updates, [])
    imported = len(updates) - 1
    if imported:
        _log(f"imported {imported} legacy client state entr{'y' if imported == 1 else 'ies'}")
    return True


# ---------------------------------------------------------------------------
# Launcher args (UNIFY 2.6)
# ---------------------------------------------------------------------------

def parse_launch_args(args) -> dict | None:
    server = slot = password = None

    def from_uri(uri: str) -> None:
        nonlocal server, slot, password
        u = urllib.parse.urlsplit(uri)
        userinfo, _, hostport = u.netloc.rpartition("@")
        if hostport:
            server = hostport
        if userinfo:
            user, sep, pw = userinfo.partition(":")
            if user:
                slot = urllib.parse.unquote(user)
            if sep and pw:
                password = urllib.parse.unquote(pw)

    items = [str(a) for a in (args or ())]
    i = 0
    while i < len(items):
        a = items[i]
        flag, eq, inline = a.partition("=")
        if a.startswith("archipelago://"):
            from_uri(a)
        elif flag in ("--connect", "--name", "--password"):
            if eq:
                value = inline
            elif i + 1 < len(items):
                i += 1
                value = items[i]
            else:
                value = ""
            if flag == "--connect":
                if value.startswith("archipelago://"):
                    from_uri(value)
                elif value:
                    server = value
            elif flag == "--name" and value:
                slot = value
            elif flag == "--password" and value:
                password = value
        i += 1

    if not server and not slot:
        return None
    return {
        "server": server or "",
        "slot": slot or "",
        "password": password or "",
        "autoconnect": bool(server and slot),
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class App:
    def __init__(self, files: WebFiles, storage: Storage, launch: dict | None) -> None:
        self.files = files
        self.storage = storage
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_hex(8)
        self.started = time.monotonic()
        self.last_heartbeat = self.started
        self._launch = launch
        self._launch_lock = threading.Lock()
        try:
            base = json.loads((files.read("config.json") or b"{}").decode("utf-8"))
            self._base_config = base if isinstance(base, dict) else {}
        except Exception:
            self._base_config = {}

    def config(self, consume_launch: bool) -> dict:
        with self._launch_lock:
            launch = self._launch
            if consume_launch:
                # Handed out once, so a reload never repeats an autoconnect.
                self._launch = None
        cfg = dict(self._base_config)
        cfg["mode"] = "local"
        cfg["features"] = {
            **(self._base_config.get("features") or {}),
            "insecureWs": True,
            "localStorageService": True,
        }
        cfg["launch"] = launch
        cfg["token"] = self.token
        cfg["instanceId"] = self.instance_id
        return cfg

    def set_launch(self, launch: dict | None) -> None:
        with self._launch_lock:
            self._launch = launch


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "TaskipelagoWebhost"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args) -> None:
        pass

    @property
    def app(self) -> App:
        return self.server.app

    def _send(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8",
              head: bool = False, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if status >= 400:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if body and not head:
            self.wfile.write(body)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _api_ok(self) -> bool:
        token = self.headers.get("X-Taskipelago-Token") or ""
        if not secrets.compare_digest(token, self.app.token):
            return False
        site = self.headers.get("Sec-Fetch-Site")
        return site is None or site == "same-origin"

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw.decode("utf-8") or "null")

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:
        # Never answer a preflight with allow headers: cross-site pages cannot
        # send the token header.
        self._send(405, b"Method Not Allowed")

    def _dispatch(self, method: str) -> None:
        if not self._host_ok():
            self._send(403, b"Forbidden")
            return
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/"):
            if not self._api_ok():
                self._send(403, b"Forbidden")
                return
            self._api(method, path)
            return
        if method not in ("GET", "HEAD"):
            self._send(405, b"Method Not Allowed")
            return
        head = method == "HEAD"
        if path == "/config.json":
            body = json.dumps(self.app.config(consume_launch=not head)).encode("utf-8")
            self._send(200, body, MIME_TYPES[".json"], head=head,
                       extra={"X-Taskipelago-Instance": self.app.instance_id})
            return
        rel = safe_rel_path(self.path)
        if rel is None:
            self._send(400, b"Bad Request")
            return
        ext = os.path.splitext(rel)[1].lower()
        content_type = MIME_TYPES.get(ext)
        data = self.app.files.read(rel) if content_type else None
        if data is None:
            self._send(404, b"Not Found")
            return
        self._send(200, data, content_type, head=head)

    def _api(self, method: str, path: str) -> None:
        try:
            if path == "/api/storage" and method == "GET":
                self._send(200, self.app.storage.snapshot_json(), MIME_TYPES[".json"])
            elif path == "/api/storage" and method == "PATCH":
                body = self._read_json()
                if not isinstance(body, dict):
                    raise ValueError("expected an object")
                set_values = body.get("set") or {}
                remove_keys = body.get("remove") or []
                if not isinstance(set_values, dict) or not isinstance(remove_keys, list) \
                        or not all(isinstance(k, str) for k in [*set_values.keys(), *remove_keys]):
                    raise ValueError("expected {set: {k: v}, remove: [k]}")
                self.app.storage.patch(set_values, remove_keys)
                self._send(204)
            elif path == "/api/heartbeat" and method == "POST":
                self._read_json()
                self.app.last_heartbeat = time.monotonic()
                self._send(204)
            elif path == "/api/launch" and method == "POST":
                body = self._read_json()
                self.app.set_launch(body if isinstance(body, dict) else None)
                self._send(204)
            else:
                self._send(404, b"Not Found")
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, str(e).encode("utf-8"))


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # SO_REUSEADDR on Windows lets another socket bind the same port.
    allow_reuse_address = not IS_WINDOWS


def bind_server(app: App, ports=range(PORT_FIRST, PORT_LAST + 1)) -> Server | None:
    for port in ports:
        try:
            server = Server(("127.0.0.1", port), Handler)
        except OSError:
            continue
        server.app = app
        return server
    return None


# ---------------------------------------------------------------------------
# Single instance (UNIFY 2.4)
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    if not _is_int(pid) or pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _read_lock(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _probe_instance(port, instance_id) -> bool:
    if not _is_int(port) or not isinstance(instance_id, str):
        return False
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("HEAD", "/config.json", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        found = resp.getheader("X-Taskipelago-Instance")
        conn.close()
        return resp.status == 200 and found == instance_id
    except OSError:
        return False


def _post_launch(lock: dict, launch: dict) -> None:
    port = lock.get("port")
    try:
        body = json.dumps(launch).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/api/launch", body=body, headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/json",
            "X-Taskipelago-Token": str(lock.get("token") or ""),
        })
        conn.getresponse().read()
        conn.close()
    except OSError as e:
        _log(f"could not pass launch arguments to the running client: {e!r}")


# ---------------------------------------------------------------------------
# Browser discovery and environment (UNIFY 2.3)
# ---------------------------------------------------------------------------

_APPIMAGE_DROP = ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH",
                  "APPDIR", "APPIMAGE", "ARGV0", "OWD")


def sanitized_env(environ=None) -> dict:
    """Child env without the AppImage/frozen-Python runtime leaking into a system browser."""
    env = dict(os.environ if environ is None else environ)
    appdir = env.get("APPDIR", "")
    for key in list(env):
        if key.endswith("_ORIG"):
            base = key[:-len("_ORIG")]
            if env[key]:
                env[base] = env[key]
            else:
                env.pop(base, None)
            env.pop(key, None)
    for key in _APPIMAGE_DROP:
        env.pop(key, None)
    if appdir:
        for key in ("PATH", "XDG_DATA_DIRS"):
            if key in env:
                kept = [p for p in env[key].split(os.pathsep) if p and not p.startswith(appdir)]
                env[key] = os.pathsep.join(kept)
    return env


class Browser:
    def __init__(self, command: list, profile: str, kind: str) -> None:
        self.command = command
        self.profile = profile
        self.kind = kind

    def lock_path(self) -> str:
        name = "lockfile" if IS_WINDOWS else "SingletonLock"
        return os.path.join(self.profile, name)

    def profile_locked(self) -> bool:
        return os.path.lexists(self.lock_path())


def _linux_data_home() -> str:
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def _find_windows_browser() -> str | None:
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for exe in ("msedge.exe", "chrome.exe", "brave.exe"):
                key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
                try:
                    with winreg.OpenKey(hive, key) as k:
                        value, _ = winreg.QueryValueEx(k, None)
                    value = str(value).strip().strip('"')
                    if os.path.isfile(value):
                        return value
                except OSError:
                    continue
    except ImportError:
        pass
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    lad = os.environ.get("LocalAppData", "")
    for path in (
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(lad, "Google", "Chrome", "Application", "chrome.exe") if lad else "",
        os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ):
        if path and os.path.isfile(path):
            return path
    return None


def find_browser(env: dict | None = None) -> Browser | None:
    override = os.environ.get("TASKIPELAGO_BROWSER", "").strip()
    if override.lower() == "none":
        return None
    env = sanitized_env() if env is None else env

    if IS_WINDOWS:
        exe = override if override and os.path.isfile(override) else _find_windows_browser()
        if not exe:
            return None
        return Browser([exe], os.path.join(_user_dir(), "chromium-profile"), "windows")

    if IS_MAC:
        mac_profile = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                                   "Taskipelago", "chromium-profile")
        candidates = [override] if override else [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for exe in candidates:
            if exe and os.path.isfile(exe):
                return Browser([exe], mac_profile, "mac")
        return None

    home = os.path.expanduser("~")
    native_profile = os.path.join(_linux_data_home(), "Taskipelago", "chromium-profile")
    if override:
        return Browser([override], native_profile, "native") if os.path.isfile(override) else None

    search_path = env.get("PATH", os.defpath)
    snap_exe = None
    for name in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome",
                 "microsoft-edge-stable", "brave-browser", "brave", "vivaldi-stable"):
        exe = shutil.which(name, path=search_path)
        if not exe:
            continue
        if os.path.realpath(exe).startswith("/snap/") or exe.startswith("/snap/"):
            snap_exe = snap_exe or exe
            continue
        return Browser([exe], native_profile, "native")

    if shutil.which("flatpak", path=search_path):
        for app_id in ("org.chromium.Chromium", "com.google.Chrome", "com.brave.Browser",
                       "com.microsoft.Edge"):
            try:
                result = subprocess.run(["flatpak", "info", app_id], env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0:
                profile = os.path.join(home, ".var", "app", app_id, "data", "taskipelago-profile")
                return Browser(["flatpak", "run", app_id], profile, "flatpak")

    snap_exe = snap_exe or ("/snap/bin/chromium" if os.path.exists("/snap/bin/chromium") else None)
    if snap_exe:
        # Snap confinement blocks hidden dirs in $HOME.
        profile = os.path.join(home, "snap", "chromium", "common", "taskipelago-profile")
        return Browser([snap_exe], profile, "snap")
    return None


def browser_args(url: str, profile: str) -> list:
    args = [
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        # DeathLink alert sound must play after launcher autoconnect, which has
        # no user gesture (v1.1 plan, UNIFY 2.3 amendment).
        "--autoplay-policy=no-user-gesture-required",
    ]
    if IS_LINUX:
        args += ["--class=Taskipelago", "--ozone-platform-hint=auto"]
    return args


def spawn_browser(browser: Browser, url: str) -> subprocess.Popen:
    os.makedirs(browser.profile, exist_ok=True)
    kwargs: dict = {"env": sanitized_env(), "stdin": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(browser.command + browser_args(url, browser.profile), **kwargs)


def open_default_browser(url: str) -> None:
    try:
        if IS_WINDOWS:
            os.startfile(url)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", url], env=sanitized_env())
        else:
            subprocess.Popen(["xdg-open", url], env=sanitized_env(),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        _log(f"could not open the default browser ({e!r}); open {url} manually")


def ask_use_default_browser() -> bool:
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        try:
            return bool(messagebox.askyesno("Taskipelago Client", NO_BROWSER_PROMPT, parent=root))
        finally:
            root.destroy()
    except Exception:
        _log("no Chromium-based browser found and tkinter is unavailable; using the default browser")
        return True


# ---------------------------------------------------------------------------
# Lifetime
# ---------------------------------------------------------------------------

def wait_for_heartbeats(app: App) -> None:
    while True:
        time.sleep(1.0)
        now = time.monotonic()
        if now - app.started < STARTUP_GRACE:
            continue
        if now - app.last_heartbeat > HEARTBEAT_TIMEOUT:
            return


def wait_for_app_window(app: App, browser: Browser, proc: subprocess.Popen) -> bool:
    """Block while the app window is open. Returns False if the browser never started."""
    spawned = time.monotonic()
    code = proc.wait()
    if time.monotonic() - spawned > DETACH_WINDOW_SECONDS:
        return True

    # Exited quickly: either it detached (flatpak/snap/Edge hand-off) or it failed.
    deadline = time.monotonic() + 10.0
    while not browser.profile_locked() and time.monotonic() < deadline:
        if time.monotonic() - app.last_heartbeat < 2 * LOCK_POLL_SECONDS and app.last_heartbeat > spawned:
            break
        time.sleep(0.5)

    if browser.profile_locked():
        while browser.profile_locked():
            time.sleep(LOCK_POLL_SECONDS)
        return True
    if app.last_heartbeat > spawned:
        wait_for_heartbeats(app)
        return True
    _log(f"browser exited with code {code} without opening a window")
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def launch(*args) -> None:
    launch_info = parse_launch_args(args)
    state_dir = _user_dir()
    lock_path = os.path.join(state_dir, "webhost.lock")

    existing = _read_lock(lock_path)
    if existing and _pid_alive(existing.get("pid")) and \
            _probe_instance(existing.get("port"), existing.get("instanceId")):
        url = f"http://127.0.0.1:{existing['port']}/"
        _log(f"client already running at {url}; opening another window")
        if launch_info:
            _post_launch(existing, launch_info)
        browser = find_browser()
        if browser:
            spawn_browser(browser, url)
        else:
            open_default_browser(url)
        return

    files = WebFiles()
    if files.read("index.html") is None:
        _log("web client files are missing from the apworld")
        return

    storage = Storage(os.path.join(state_dir, "client_state.json"))
    try:
        migrate_legacy_state(storage, _legacy_state_dirs())
    except Exception as e:
        _log(f"legacy state import failed: {e!r}")

    app = App(files, storage, launch_info)
    server = bind_server(app)
    if server is None:
        _log(f"no free port in {PORT_FIRST}-{PORT_LAST}")
        return
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "port": port, "instanceId": app.instance_id,
                       "token": app.token}, f)
    except OSError as e:
        _log(f"could not write {lock_path}: {e!r}")

    threading.Thread(target=server.serve_forever, name="TaskipelagoWebhost", daemon=True).start()
    _log(f"serving {url}")

    try:
        if os.environ.get("TASKIPELAGO_NO_OPEN"):
            wait_for_heartbeats(app)
            return
        browser = find_browser()
        if browser is not None:
            _log(f"opening app window with {browser.command[-1]} ({browser.kind})")
            try:
                proc = spawn_browser(browser, url)
            except OSError as e:
                _log(f"could not start {browser.command[0]}: {e!r}")
                proc = None
            if proc is not None and wait_for_app_window(app, browser, proc):
                return
        if not ask_use_default_browser():
            return
        _log(f"opening {url} in the default browser")
        open_default_browser(url)
        wait_for_heartbeats(app)
    finally:
        server.shutdown()
        server.server_close()
        current = _read_lock(lock_path)
        if current and current.get("instanceId") == app.instance_id:
            try:
                os.remove(lock_path)
            except OSError:
                pass
        _log("client closed")


if __name__ == "__main__":
    launch(*sys.argv[1:])
