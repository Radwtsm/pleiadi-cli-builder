"""0.5: secret sources, certificate fingerprint, long outputs to a log, snapshots — each failed before its fix."""
import io, json, os, re, shutil, subprocess, sys, tempfile, threading, unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Screen, run, run_live
from pleiadi_cli_builder import credentials, term


def quiet(fn):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        r = fn()
    return r, out.getvalue(), err.getvalue()


class SecretSources(unittest.TestCase):
    def tearDown(self):
        term.SECRETS.clear()
        credentials.KEYCHAIN = None

    def test_command_source_read_only_and_masked(self):
        src = credentials.CommandSource([sys.executable, "-c", "import sys; print('tok-' + sys.argv[1] + '-' + sys.argv[2] + '-xyz')",
                                         "{service}", "{account}"])
        v = credentials.secret("svc", "me", source=src)
        self.assertEqual(v, "tok-svc-me-xyz")
        self.assertFalse(hasattr(src, "set") or hasattr(src, "delete"))  # read-only by construction
        code, out = run(sys.executable, "-c", "import os; print(os.environ['T'])", env={**os.environ, "T": v})
        self.assertNotIn(v, out)
        with self.assertRaises(RuntimeError):
            run("echo", v)

    def test_source_missing_never_asks_or_stores(self):
        credentials.KEYCHAIN = credentials.MemoryOnly()
        src = credentials.CommandSource([sys.executable, "-c", "import sys; sys.exit(1)"])
        self.assertIsNone(credentials.secret("svc", "me", screen=Screen("t"), source=src))
        self.assertEqual(credentials.KEYCHAIN.items, {})

    def test_protected_file_outside_windows(self):
        p = os.path.join(tempfile.mkdtemp(), "s.bin")
        with open(p, "wb") as f:
            f.write(b"\x01\x02")
        src = credentials.ProtectedFile(p)
        if os.name == "nt":
            self.assertIsNone(src.get("svc", "me"))  # not a DPAPI blob: None, never garbage
        else:
            with self.assertRaises(OSError):
                src.get("svc", "me")


class Fingerprint(unittest.TestCase):
    def test_server_certificate(self):
        import http.server, ssl
        from pleiadi_cli_builder import webapi
        if not shutil.which("openssl"):
            self.skipTest("no openssl")
        d = tempfile.mkdtemp()
        key, crt = os.path.join(d, "k.pem"), os.path.join(d, "c.pem")
        if subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt,
                           "-days", "5", "-subj", "/CN=localhost"], capture_output=True).returncode:
            self.skipTest("openssl failed")

        class Quiet(http.server.HTTPServer):
            def handle_error(self, *a):
                pass
        srv = Quiet(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            sha, expires = webapi.server_certificate("127.0.0.1", srv.server_port)
            with open(crt) as f:
                self.assertEqual(sha, webapi.fingerprint(ssl.PEM_cert_to_DER_cert(f.read())))
            self.assertRegex(expires or "", r"^\d{4}-\d{2}-\d{2}$")
            env = {**os.environ, "PYTHONPATH": ROOT}
            r = subprocess.run([sys.executable, "-m", "pleiadi_cli_builder", "impronta", f"127.0.0.1:{srv.server_port}",
                                "--json"], capture_output=True, text=True, encoding="utf-8", env=env)
            row = json.loads(r.stdout)[0]
            self.assertEqual(row["sha256"], sha)
            self.assertEqual(r.stderr.count("{"), 0)  # nothing of the data on stderr, nothing else on stdout
            r = subprocess.run([sys.executable, "-m", "pleiadi_cli_builder", "impronta", f"127.0.0.1:{srv.server_port}"],
                               capture_output=True, text=True, encoding="utf-8", env=env)
            self.assertIn(sha, r.stdout)  # the whole value, to copy into the config
            self.assertIn("proprietario", r.stdout)
        finally:
            srv.shutdown()
            srv.server_close()


class LongOutput(unittest.TestCase):
    def test_log_to_file_errors_on_screen(self):
        log = os.path.join(tempfile.mkdtemp(), "build.log")
        prog = "for i in range(200): print(f'line {i}', flush=True)\nprint('ERROR: disk full')\nprint('done')"
        code, out = run_live(sys.executable, "-c", prog, log=log)
        with open(log, encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()), 202)
        self.assertIn("ERROR: disk full", out)
        self.assertNotIn("line 150", out)
        self.assertIn(log, out.splitlines()[-1])


class Snapshots(unittest.TestCase):
    def test_once_then_cached_then_refresh(self):
        home = tempfile.mkdtemp()
        app = App("t-snap", lang="en")
        app.cache_dir = os.path.join(home, "cache")
        calls = []

        def fetch():
            calls.append(1)
            return [{"id": len(calls)}]
        data, when = app.snapshot("open-issues", fetch)
        data2, when2 = app.snapshot("open-issues", fetch)
        self.assertEqual((len(calls), data2, when2), (1, data, when))
        data3, _ = app.snapshot("open-issues", fetch, refresh=True)
        self.assertEqual((len(calls), data3), (2, [{"id": 2}]))
        path = os.path.join(app.cache_dir, "open-issues.json")
        if os.name != "nt":
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            app.snapshot("../x", fetch)

    def test_refresh_flag_and_age_line(self):
        app = App("t-snap2", lang="en")
        app.cache_dir = tempfile.mkdtemp()
        seen = {}

        def show(screen, args):
            data, when = app.snapshot("x", lambda: [1], refresh=screen.refresh)
            seen["refresh"] = screen.refresh
            screen.info(app.snapshot_note(when))
        app.command("show", effects=False)(show)
        _, out, _ = quiet(lambda: app.main(["show", "--refresh"]))
        self.assertTrue(seen["refresh"])
        self.assertRegex(out, r"snapshot of \d{4}-\d{2}-\d{2} \d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()
