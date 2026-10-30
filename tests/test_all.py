import io, json, os, pathlib, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pleiadi_cli_builder import (App, HTTPError, ReadOnlyClient, Scene, Screen, Step, Theme, bundle, clip, forget,
                                 run_steps, secret, self_update, temporary)
from pleiadi_cli_builder import credentials, webapi
from pleiadi_cli_builder.intro import SHAPES, Renderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal


def plain(fn):
    """Runs fn with stdout captured (so the Screen sees no terminal and prints plain lines)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = fn()
    return r, buf.getvalue()


class Term(unittest.TestCase):
    def test_clip_ignores_colors(self):
        s = "\033[31m" + "x" * 50 + "\033[0m"
        out = clip(s, 10)
        self.assertEqual(len(out.replace("\033[31m", "").replace("\033[0m", "")), 10)
        self.assertTrue(out.endswith("\x1b[0m"))

    def test_rgb(self):
        self.assertEqual(Theme.rgb("#e8253f"), "38;2;232;37;63")


class Steps(unittest.TestCase):
    def test_skip_apply_fail(self):
        done = []
        steps = [Step("già", lambda: True), Step("fa", lambda: bool(done), apply=lambda: done.append(1) or (True, "ok")),
                 Step("a mano", lambda: False, fix="premi «Collega»")]
        ok, out = plain(lambda: run_steps(Screen("t", lang="it"), steps))
        self.assertFalse(ok)
        self.assertIn("✓ già", out)
        self.assertIn("✓ fa · ok", out)
        self.assertIn("✗ a mano", out)
        self.assertIn("premi «Collega»", out)
        self.assertIn("2/3 a posto", out)
        ok, out = plain(lambda: run_steps(Screen("t"), steps[:2], check_only=True))  # rerun: all skipped
        self.assertTrue(ok)

    def test_broken_check_is_a_failure(self):
        ok, out = plain(lambda: run_steps(Screen("t"), [Step("rotto", lambda: 1 / 0)], check_only=True))
        self.assertFalse(ok)
        self.assertIn("division by zero", out)


class Apps(unittest.TestCase):
    def setUp(self):
        self.app = App("x-test", lang="en")
        self.app.state_path = os.path.join(tempfile.mkdtemp(), "state.json")
        self.app.command("hi", help="says hi")(lambda s, a: s.out("hi " + " ".join(a)))

    def test_dispatch_help_unknown(self):
        self.assertEqual(plain(lambda: self.app.main(["hi", "there"])), (0, "hi there\n\n✓ hi: done\n"))
        self.assertIn("x-test hi", plain(lambda: self.app.main(["help"]))[1])
        self.assertEqual(plain(lambda: self.app.main(["nope"]))[0], 2)

    def test_dry_run_and_read_only(self):
        made = []
        steps = [Step("crea", lambda: bool(made), apply=lambda: made.append(1) or True, plan="creo la cartella")]
        self.app.command("fa", help="cambia")(lambda s, a: run_steps(s, steps) or 1)
        self.app.command("guarda", help="legge", effects=False)(lambda s, a: run_steps(s, steps) or 1)
        code, out = plain(lambda: self.app.main(["fa", "--dry-run"]))
        self.assertEqual(made, [])
        self.assertIn("○ crea · would: creo la cartella", out)
        self.assertIn("1 to do, nothing changed", out)
        plain(lambda: self.app.main(["guarda"]))  # read-only: the code refuses to apply
        self.assertEqual(made, [])
        plain(lambda: self.app.main(["fa"]))
        self.assertEqual(made, [1])
        usage = self.app.usage()
        self.assertIn("x-test fa [--dry-run]", usage)
        self.assertIn("legge (read-only)", usage)

    def test_state(self):
        self.app.save_state(a=1)
        self.app.save_state(b=2)
        self.assertEqual(self.app.state(), {"a": 1, "b": 2})


class Table(unittest.TestCase):
    def test_table_and_json(self):
        app = App("t-table", lang="en")
        rows = [{"id": 1, "subject": "a very long subject " * 10, "status": "open"}, {"id": 2, "subject": "b", "status": None}]
        app.command("list", effects=False)(lambda s, a: s.table(rows, ["id", "subject", "status"], {"subject": "Title"}))
        code, out = plain(lambda: app.main(["list"]))
        self.assertIn("Title", out)
        self.assertIn("2 rows", out)
        self.assertTrue(all(len(l) <= 101 for l in out.splitlines()))
        err = io.StringIO()
        from contextlib import redirect_stderr
        with redirect_stderr(err):
            code, out = plain(lambda: app.main(["list", "--json"]))
        self.assertEqual(json.loads(out)[1], {"id": 2, "subject": "b", "status": None})


class Credentials(unittest.TestCase):
    def setUp(self):
        credentials.KEYCHAIN = credentials.MemoryOnly()

    def tearDown(self):
        credentials.KEYCHAIN = None

    def test_memory_keychain(self):
        self.assertIsNone(secret("t.tool", "me"))  # nobody to ask: None, never a guess
        credentials.keychain().set("t.tool", "me", "tok")
        self.assertEqual(secret("t.tool", "me"), "tok")
        self.assertTrue(forget("t.tool", "me"))
        self.assertIsNone(secret("t.tool", "me"))

    @unittest.skipUnless(os.environ.get("PCB_REAL_KEYCHAIN") and sys.platform == "darwin", "touches the real keychain")
    def test_real_mac_keychain(self):
        k = credentials.MacKeychain()
        self.assertTrue(k.set("pleiadi-cli-builder.test", "test", "valore di prova 123"))
        self.assertEqual(k.get("pleiadi-cli-builder.test", "test"), "valore di prova 123")
        self.assertTrue(k.delete("pleiadi-cli-builder.test", "test"))
        self.assertIsNone(k.get("pleiadi-cli-builder.test", "test"))


class Access(unittest.TestCase):
    def test_closed_even_on_failure(self):
        log = []
        with self.assertRaises(ZeroDivisionError):
            with temporary(lambda: log.append("open"), lambda: log.append("close")):
                1 / 0
        self.assertEqual(log, ["open", "close"])

    def test_leaves_open_what_was_open(self):
        log = []
        with temporary(lambda: log.append("open"), lambda: log.append("close"), is_open=lambda: True):
            pass
        self.assertEqual(log, [])

    def test_open_failure(self):
        with self.assertRaises(RuntimeError):
            with temporary(lambda: False, lambda: None, label="VPN"):
                pass


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import http.server, threading
        cls.seen, cls.fail = [], [1]
        items = [{"id": i} for i in range(1, 8)]

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                cls.seen.append((self.command, self.path, self.headers.get("X-Api-Key")))
                if cls.fail:
                    cls.fail.pop()
                    self.send_response(503)
                    self.send_header("Retry-After", "0")
                    self.end_headers()
                    return
                q = dict(x.split("=") for x in self.path.split("?")[1].split("&"))
                if self.path.startswith("/missing"):
                    self.send_response(404)
                    self.end_headers()
                    return
                off, lim = int(q["offset"]), int(q["limit"])
                body = json.dumps({"issues": items[off:off + lim], "total_count": len(items)}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_pages_retry_header(self):
        api = ReadOnlyClient(self.base, token="k", header="X-Api-Key", scheme="")
        got = [x["id"] for x in api.pages("/issues.json", {"status": "open"}, items="issues", limit=3)]
        self.assertEqual(got, list(range(1, 8)))
        self.assertEqual(self.seen[0][0], "GET")
        self.assertTrue(all(h == "k" for _, _, h in self.seen))
        self.assertTrue(all("k" not in p.split("?")[-1].split("&") and "=k" not in p for _, p, _ in self.seen))
        with self.assertRaises(HTTPError):
            api.get("/missing", {"offset": 0, "limit": 1})

    def test_read_only_by_construction(self):
        api = ReadOnlyClient(self.base)
        self.assertFalse(any(hasattr(api, m) for m in ("post", "put", "patch", "delete", "request")))
        with self.assertRaises(ValueError):
            ReadOnlyClient("http://tracker.example")
        with self.assertRaises(ValueError):
            ReadOnlyClient("https://tracker.example", pin_sha256="ab" * 32)

    def test_pin_expiry(self):
        import datetime
        der = b"cert"
        self.assertTrue(webapi._pin_ok(der, webapi.fingerprint(der), "2099-01-01"))
        self.assertFalse(webapi._pin_ok(der, "00" * 32, "2099-01-01"))
        with self.assertRaises(Exception):
            webapi._pin_ok(der, webapi.fingerprint(der), "2020-01-01", today=datetime.date(2026, 1, 1))

    def test_pinned_https_for_real(self):
        import shutil, ssl, http.server, threading
        if not shutil.which("openssl"):
            self.skipTest("no openssl")
        d = tempfile.mkdtemp()
        key, crt = os.path.join(d, "k.pem"), os.path.join(d, "c.pem")
        r = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt,
                            "-days", "2", "-subj", "/CN=localhost"], capture_output=True)
        if r.returncode:
            self.skipTest("openssl failed")

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
        class Quiet(http.server.HTTPServer):
            def handle_error(self, *a):  # the client refusing the certificate resets the connection: expected
                pass
        srv = Quiet(("127.0.0.1", 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = f"https://127.0.0.1:{srv.server_port}"
            with open(crt) as f:
                der = ssl.PEM_cert_to_DER_cert(f.read())
            ok = ReadOnlyClient(base, pin_sha256=webapi.fingerprint(der), pin_expires="2099-01-01", retries=0)
            self.assertEqual(ok.get("/x"), {"ok": True})
            with self.assertRaises(Exception):  # unknown authority, no pin: refused, never accepted silently
                ReadOnlyClient(base, retries=0).get("/x")
            with self.assertRaises(Exception):
                ReadOnlyClient(base, pin_sha256="00" * 32, pin_expires="2099-01-01", retries=0).get("/x")
        finally:
            srv.shutdown()
            srv.server_close()


class Intro(unittest.TestCase):
    def test_every_shape_renders(self):
        for quarter in (True, False):
            for true in (True, False):
                for i, a in enumerate(SHAPES):
                    sc = Scene("ciao àbc", "frase", ["riga"], colors="blue", shapes=(a, SHAPES[(i + 1) % len(SHAPES)]))
                    rd = Renderer(sc, 60, 20, quarter=quarter, true_color=true)
                    for t, spin in ((0.1, 0), (0.6, 0), (1.0, 0), (1.0, 6.0)):
                        out = rd.cells(rd.frame(t, spin), t)
                    self.assertIn("frase", out)
                    self.assertEqual(sc.title, "CIAO ABC")

    def test_bad_input_falls_back(self):
        sc = Scene("", colors=("#zzz", "x", "y"), shapes=("nope",), stars=[])
        self.assertEqual((sc.title, sc.shapes), ("HELLO", ["star", "sphere"]))
        Renderer(sc, 40, 14).cells(Renderer(sc, 40, 14).frame(1.0), 1.0)


class Ship(unittest.TestCase):
    def test_new_bundle_run_update(self):
        d = tempfile.mkdtemp()
        env = {**os.environ, "PYTHONPATH": ROOT}
        r = subprocess.run([sys.executable, "-m", "pleiadi_cli_builder", "new", "deploy-kit", os.path.join(d, "dk")],
                           env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = os.path.join(d, "dist", "deploy-kit.pyz")
        os.makedirs(os.path.dirname(out))
        digest = bundle(os.path.join(d, "dk"), "deploy_kit.__main__:main", out)
        clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}  # the .pyz must carry the library
        r = subprocess.run([sys.executable, out, "doctor"], capture_output=True, text=True, encoding="utf-8", cwd=d,
                           env=clean)
        self.assertIn("git", r.stdout, r.stderr)
        self.assertIn("a posto", r.stdout)
        dest = os.path.join(d, "installed", "deploy-kit.pyz")
        url = pathlib.Path(out).as_uri()
        self.assertEqual(self_update(url, dest, sha256_url=url + ".sha256"), (True, "updated"))
        self.assertEqual(self_update(url, dest, url + ".sha256"), (True, "up to date"))
        with open(out + ".sha256", "w") as f:
            f.write("0" * 64)
        self.assertFalse(self_update(url, dest + "2", sha256_url=url + ".sha256")[0])
        self.assertEqual(len(digest), 64)

    def test_full_screen_in_a_pty(self):
        if os.name == "nt":
            self.skipTest("no pty")
        import pty, select
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update(PYTHONPATH=ROOT, TERM="xterm-256color", COLUMNS="100", LINES="30")
            os.execv(sys.executable, [sys.executable, "-m", "pleiadi_cli_builder", "demo"])
        data = b""
        while True:
            try:
                if not select.select([fd], [], [], 15)[0]:
                    break
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data += chunk
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, data[-500:])
        self.assertIn(b"\x1b[?1049h", data)  # it really opened the full screen…
        self.assertIn("2/3 a posto".encode(), data)  # …and left the summary on the normal one


if __name__ == "__main__":
    unittest.main()
