"""What an attacker would try first: the token following a redirect, an update over plain http, a secret shipped
inside a bundle, a path that breaks out of the launcher's quotes."""
import http.server, os, subprocess, sys, tempfile, threading, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pleiadi_cli_builder import ReadOnlyClient, bundle, install, self_update
from pleiadi_cli_builder.term import WIN


def serve(handler):
    s = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class Redirects(unittest.TestCase):
    def setUp(self):
        self.seen = seen = {}

        class Other(http.server.BaseHTTPRequestHandler):
            def do_GET(s):
                seen["auth"] = s.headers.get("Authorization")
                s.send_response(200), s.end_headers(), s.wfile.write(b"{}")

            def log_message(*a):
                pass
        self.other = serve(Other)
        other_port = self.other.server_port

        class Base(http.server.BaseHTTPRequestHandler):
            def do_GET(s):
                if s.path.startswith("/here"):
                    seen["here"] = s.headers.get("Authorization")
                    s.send_response(200), s.end_headers(), s.wfile.write(b'{"ok": 1}')
                    return
                target = "/here" if s.path.startswith("/same") else f"http://localhost:{other_port}/x"
                s.send_response(302), s.send_header("Location", target), s.end_headers()

            def log_message(*a):
                pass
        self.base = serve(Base)
        self.api = ReadOnlyClient(f"http://127.0.0.1:{self.base.server_port}", token="t0ken", retries=0)

    def tearDown(self):
        for s in (self.base, self.other):
            s.shutdown()
            s.server_close()

    def test_token_never_follows_a_redirect_to_another_server(self):
        with self.assertRaises(Exception) as e:
            self.api.get("/away")
        self.assertIn("redirect to another server refused", str(e.exception))
        self.assertNotIn("auth", self.seen)

    def test_same_server_redirect_still_works(self):
        self.assertEqual(self.api.get("/same"), {"ok": 1})
        self.assertEqual(self.seen["here"], "Bearer t0ken")

    def test_download_refuses_redirect_too(self):
        with self.assertRaises(Exception):
            self.api.download("/away", os.path.join(tempfile.mkdtemp(), "f"))
        self.assertNotIn("auth", self.seen)


class Update(unittest.TestCase):
    def test_plain_http_refused(self):
        ok, why = self_update("http://example.com/t.pyz", os.path.join(tempfile.mkdtemp(), "t.pyz"),
                              "http://example.com/t.pyz.sha256")
        self.assertFalse(ok)
        self.assertIn("https only", why)


class Bundle(unittest.TestCase):
    def tool(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "kit"))
        with open(os.path.join(d, "kit", "__main__.py"), "w") as f:
            f.write("def main():\n    print('hi')\n")
        return d

    def test_secret_in_source_stops_the_build(self):
        d = self.tool()
        with open(os.path.join(d, "kit", "conf.py"), "w") as f:
            f.write("KEY = '" + "AKIA" + "Q" * 16 + "'\n")  # built at runtime: no real key in this repo
        with self.assertRaises(install.SecretInBundle) as e:
            bundle(d, "kit.__main__:main", os.path.join(tempfile.mkdtemp(), "k.pyz"), library=False)
        self.assertIn("conf.py", str(e.exception))

    def test_key_and_env_files_left_out(self):
        import zipfile
        d = self.tool()
        for name in (".env", "deploy.pem"):
            with open(os.path.join(d, name), "w") as f:
                f.write("x\n")
        out = os.path.join(tempfile.mkdtemp(), "k.pyz")
        bundle(d, "kit.__main__:main", out, library=False)
        names = zipfile.ZipFile(out).namelist()
        self.assertNotIn(".env", names)
        self.assertNotIn("deploy.pem", names)

    def test_library_bundles_clean(self):  # the release must not trip on the library's own scan patterns
        out = os.path.join(tempfile.mkdtemp(), "k.pyz")
        self.assertEqual(len(bundle(self.tool(), "kit.__main__:main", out)), 64)


@unittest.skipIf(WIN, "sh launcher")
class Launcher(unittest.TestCase):
    def test_dollar_in_path_is_not_expanded(self):
        home = tempfile.mkdtemp()
        old = install.HOME, install.BIN, os.environ.get("PATH")
        install.HOME, install.BIN = os.path.join(home, "a$(touch pwned)"), os.path.join(home, "bin")
        try:
            src = os.path.join(home, "t.py")
            with open(src, "w") as f:
                f.write("print('ran')\n")
            os.makedirs(install.HOME)
            path = install.install_launcher("t", src)
            r = subprocess.run([path], capture_output=True, text=True, cwd=home)
            self.assertEqual(r.stdout.strip(), "ran", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(home, "pwned")))
        finally:
            install.HOME, install.BIN = old[0], old[1]
            os.environ["PATH"] = old[2] or ""


if __name__ == "__main__":
    unittest.main()
