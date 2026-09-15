"""Webhost (UNIFY section 2): request guards, storage API, launch args, migration, zip serving."""
from __future__ import annotations

import http.client
import importlib
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile

from helpers import WEB_CLIENT, WORLD, load_world_module

webhost = load_world_module("webhost")


class PathTests(unittest.TestCase):
    def test_safe_rel_path(self):
        ok = {
            "/": "index.html",
            "/index.html": "index.html",
            "/js/app.js?v=3": "js/app.js",
            "/js/": "js/index.html",
            "/vendor/js-yaml.min.js#x": "vendor/js-yaml.min.js",
        }
        for raw, rel in ok.items():
            self.assertEqual(webhost.safe_rel_path(raw), rel, raw)
        for raw in ("/../secret", "/js/../../x", "//etc/passwd", "/a\\b", "/%2e%2e/x",
                    "/C:/Windows/win.ini", "/js//app.js", "relative", "/x%00y", "/a/./b"):
            self.assertIsNone(webhost.safe_rel_path(raw), raw)


class LaunchArgTests(unittest.TestCase):
    def test_uri(self):
        got = webhost.parse_launch_args(["archipelago://My%20Slot:pa%40ss@archipelago.gg:38281?game=Taskipelago"])
        self.assertEqual(got, {"server": "archipelago.gg:38281", "slot": "My Slot",
                               "password": "pa@ss", "autoconnect": True})

    def test_uri_without_password(self):
        got = webhost.parse_launch_args(["archipelago://Me@localhost:38281"])
        self.assertEqual(got["server"], "localhost:38281")
        self.assertEqual(got["slot"], "Me")
        self.assertEqual(got["password"], "")

    def test_flags(self):
        got = webhost.parse_launch_args(["--connect", "host:1", "--name=Bob", "--password", "pw"])
        self.assertEqual(got, {"server": "host:1", "slot": "Bob", "password": "pw", "autoconnect": True})

    def test_connect_uri_flag(self):
        got = webhost.parse_launch_args(["--connect", "archipelago://A:b@h:2"])
        self.assertEqual((got["server"], got["slot"], got["password"]), ("h:2", "A", "b"))

    def test_partial_and_empty(self):
        self.assertIsNone(webhost.parse_launch_args([]))
        self.assertIsNone(webhost.parse_launch_args(["Taskipelago Client"]))
        got = webhost.parse_launch_args(["--connect", "h:3"])
        self.assertFalse(got["autoconnect"])


class EnvTests(unittest.TestCase):
    def test_appimage_sanitizing(self):
        env = webhost.sanitized_env({
            "APPDIR": "/tmp/.mount_AP",
            "APPIMAGE": "/x/AP.AppImage",
            "LD_LIBRARY_PATH": "/tmp/.mount_AP/lib",
            "PYTHONHOME": "/tmp/.mount_AP/usr",
            "PATH": os.pathsep.join(["/tmp/.mount_AP/usr/bin", "/usr/bin"]),
            "XDG_DATA_DIRS": os.pathsep.join(["/tmp/.mount_AP/share", "/usr/share"]),
            "GDK_PIXBUF_MODULE_FILE_ORIG": "/usr/lib/gdk.cache",
            "GDK_PIXBUF_MODULE_FILE": "/tmp/.mount_AP/gdk.cache",
            "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-1",
        })
        for gone in ("APPDIR", "APPIMAGE", "LD_LIBRARY_PATH", "PYTHONHOME", "GDK_PIXBUF_MODULE_FILE_ORIG"):
            self.assertNotIn(gone, env)
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["XDG_DATA_DIRS"], "/usr/share")
        self.assertEqual(env["GDK_PIXBUF_MODULE_FILE"], "/usr/lib/gdk.cache")
        self.assertEqual(env["DISPLAY"], ":0")
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-1")

    def test_browser_override_none(self):
        old = os.environ.get("TASKIPELAGO_BROWSER")
        os.environ["TASKIPELAGO_BROWSER"] = "none"
        try:
            self.assertIsNone(webhost.find_browser())
        finally:
            if old is None:
                os.environ.pop("TASKIPELAGO_BROWSER")
            else:
                os.environ["TASKIPELAGO_BROWSER"] = old

    def test_browser_args(self):
        args = webhost.browser_args("http://127.0.0.1:38290/", "/p")
        self.assertIn("--app=http://127.0.0.1:38290/", args)
        self.assertIn("--user-data-dir=/p", args)
        self.assertIn("--autoplay-policy=no-user-gesture-required", args)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cwd = os.path.join(self.tmp, "cwd")
        self.user = os.path.join(self.tmp, "user")
        os.makedirs(self.cwd)
        os.makedirs(self.user)

    def _write(self, d, name, data):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_import_merges_and_marks(self):
        self._write(self.cwd, "taskipelago_notify_state.json", {
            "v3::host:1::me::seed": 7,
            "v3::host:1::me::other": 2,
            "manual_v1::host:1::me::seed": {"Gold": 2, "Bad": -1, "Zero": 0},
            "manual_v1::host:1::me::kept": {"Gold": 9},
        })
        self._write(self.user, "taskipelago_last_connection.json", {"server": "host:1", "slot": "me"})
        storage = webhost.Storage(os.path.join(self.tmp, "state.json"))
        storage.patch({
            "taskipelago_notify_v3::host:1::me::other": 5,
            "taskipelago_manual_v1::host:1::me::kept": {"Gold": 1},
        }, [])
        self.assertTrue(webhost.migrate_legacy_state(storage, [self.cwd, self.user]))
        d = storage.data
        self.assertEqual(d["taskipelago_notify_v3::host:1::me::seed"], 7)
        self.assertEqual(d["taskipelago_notify_v3::host:1::me::other"], 5)  # greater value kept
        self.assertEqual(d["taskipelago_manual_v1::host:1::me::seed"], {"Gold": 2})
        self.assertEqual(d["taskipelago_manual_v1::host:1::me::kept"], {"Gold": 1})  # only if absent
        self.assertEqual(d["taskipelago_last_conn"], {"server": "host:1", "slot": "me"})
        self.assertTrue(d[webhost.LEGACY_IMPORT_MARKER])
        # Persisted, and a second run is a no-op.
        reloaded = webhost.Storage(os.path.join(self.tmp, "state.json"))
        self.assertEqual(reloaded.data, d)
        self.assertFalse(webhost.migrate_legacy_state(reloaded, [self.cwd, self.user]))

    def test_corrupt_state_file_is_backed_up(self):
        path = os.path.join(self.tmp, "state.json")
        with open(path, "w") as f:
            f.write("{not json")
        storage = webhost.Storage(path)
        self.assertEqual(storage.data, {})
        self.assertTrue(os.path.exists(path + ".bak"))


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        storage = webhost.Storage(os.path.join(cls.tmp, "client_state.json"))
        launch = {"server": "h:1", "slot": "me", "password": "", "autoconnect": True}
        cls.app = webhost.App(webhost.WebFiles(), storage, launch)
        cls.server = webhost.bind_server(cls.app, ports=[0])
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp)

    def request(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def api(self, method, path, obj=None, extra=None):
        headers = {"X-Taskipelago-Token": self.app.token, "Content-Type": "application/json"}
        headers.update(extra or {})
        body = json.dumps(obj).encode() if obj is not None else None
        return self.request(method, path, body, headers)

    def test_static_and_mime(self):
        resp, data = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        self.assertIn(b"<html", data)
        resp, _ = self.request("GET", "/js/app.js?v=3")
        self.assertEqual(resp.getheader("Content-Type"), "text/javascript; charset=utf-8")
        resp, _ = self.request("HEAD", "/style.css")
        self.assertEqual(resp.status, 200)
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))

    def test_rejections(self):
        self.assertEqual(self.request("GET", "/", host="evil.example:80")[0].status, 403)
        self.assertEqual(self.request("GET", "/", host=f"localhost:{self.port}")[0].status, 200)
        self.assertEqual(self.request("GET", "/../webhost.py")[0].status, 400)
        self.assertEqual(self.request("GET", "/missing.js")[0].status, 404)
        self.assertEqual(self.request("GET", "/README")[0].status, 404)  # unknown extension
        resp, _ = self.request("OPTIONS", "/api/storage", headers={"Origin": "https://evil.example"})
        self.assertEqual(resp.status, 405)
        self.assertIsNone(resp.getheader("Access-Control-Allow-Headers"))
        self.assertEqual(self.request("POST", "/index.html", b"{}")[0].status, 405)

    def test_api_guards(self):
        self.assertEqual(self.request("GET", "/api/storage")[0].status, 403)
        self.assertEqual(self.request("GET", "/api/storage", headers={"X-Taskipelago-Token": "nope"})[0].status, 403)
        self.assertEqual(self.api("GET", "/api/storage", extra={"Sec-Fetch-Site": "cross-site"})[0].status, 403)
        self.assertEqual(self.api("GET", "/api/storage", extra={"Sec-Fetch-Site": "same-origin"})[0].status, 200)

    def test_config_launch_is_consumed_once(self):
        resp, _ = self.request("HEAD", "/config.json")
        self.assertEqual(resp.getheader("X-Taskipelago-Instance"), self.app.instance_id)
        self.assertTrue(webhost._probe_instance(self.port, self.app.instance_id))
        self.assertFalse(webhost._probe_instance(self.port, "other"))
        first = json.loads(self.request("GET", "/config.json")[1])
        self.assertEqual(first["mode"], "local")
        self.assertEqual(first["features"], {"insecureWs": True, "localStorageService": True})
        self.assertEqual(first["token"], self.app.token)
        self.assertEqual(first["launch"]["slot"], "me")
        second = json.loads(self.request("GET", "/config.json")[1])
        self.assertIsNone(second["launch"])
        self.assertEqual(self.api("POST", "/api/launch", {"server": "x:2", "slot": "b"})[0].status, 204)
        third = json.loads(self.request("GET", "/config.json")[1])
        self.assertEqual(third["launch"]["server"], "x:2")

    def test_storage_patch_and_heartbeat(self):
        resp, _ = self.api("PATCH", "/api/storage", {"set": {"a": 1, "b": {"c": [1, 2]}}, "remove": []})
        self.assertEqual(resp.status, 204)
        self.api("PATCH", "/api/storage", {"set": {"d": "x"}, "remove": ["a"]})
        got = json.loads(self.api("GET", "/api/storage")[1])
        self.assertEqual(got.get("b"), {"c": [1, 2]})
        self.assertEqual(got.get("d"), "x")
        self.assertNotIn("a", got)
        with open(self.app.storage.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["d"], "x")
        self.assertEqual(self.api("PATCH", "/api/storage", {"set": [1]})[0].status, 400)
        before = self.app.last_heartbeat
        self.assertEqual(self.api("POST", "/api/heartbeat", {})[0].status, 204)
        self.assertGreaterEqual(self.app.last_heartbeat, before)


class ZipServingTests(unittest.TestCase):
    """The apworld is a zip; files must be served through zipimport and the zipfile fallback."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.archive = os.path.join(cls.tmp, "taskipelago_zt.apworld")
        with zipfile.ZipFile(cls.archive, "w") as z:
            z.writestr("taskipelago_zt/__init__.py", "")
            z.write(os.path.join(WORLD, "webhost.py"), "taskipelago_zt/webhost.py")
            for root, _dirs, names in os.walk(WEB_CLIENT):
                for n in names:
                    full = os.path.join(root, n)
                    rel = os.path.relpath(full, WORLD).replace(os.sep, "/")
                    z.write(full, "taskipelago_zt/" + rel)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_zipimport_resources(self):
        sys.path.insert(0, self.archive)
        try:
            mod = importlib.import_module("taskipelago_zt.webhost")
            files = mod.WebFiles()
            self.assertIn(b"<html", files.read("index.html"))
            self.assertIsNotNone(files.read("js/app.js"))
            self.assertIsNone(files.read("nope.js"))
        finally:
            sys.path.remove(self.archive)
            for name in [m for m in sys.modules if m.startswith("taskipelago_zt")]:
                del sys.modules[name]

    def test_zipfile_fallback(self):
        fake_file = os.path.join(self.archive, "taskipelago_zt", "webhost.py")
        files = webhost.WebFiles(module_file=fake_file, package="", use_resources=False)
        self.assertIn(b"<html", files.read("index.html"))
        self.assertIsNotNone(files.read("vendor/js-yaml.min.js"))
        self.assertIsNone(files.read("missing.css"))


if __name__ == "__main__":
    unittest.main()
