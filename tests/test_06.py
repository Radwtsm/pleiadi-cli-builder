"""0.6: validated secrets and clipboard, page progress, menu-session access, local copy as a choice."""
import http.server, json, os, sys, tempfile, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, ReadOnlyClient, access, credentials, temporary, term, webapi


class FakeScreen:
    """Answers questions from a list; records what it was told."""
    interactive = True

    def __init__(self, answers=(), confirm=True):
        self.answers, self.yes, self.told = list(answers), confirm, []

    def secret_input(self, q):
        return self.answers.pop(0) if self.answers else ""

    def confirm(self, q, yes=None, no=None):
        self.told.append(q)
        return self.yes

    def todo(self, t):
        self.told.append(t)

    info = out = todo


class Secrets(unittest.TestCase):
    def setUp(self):
        credentials.KEYCHAIN = credentials.MemoryOnly()
        self.clip = {"value": "", "cleared": False}
        credentials.CLIPBOARD = {"read": lambda: self.clip["value"], "clear": lambda: self.clip.update(cleared=True)}

    def tearDown(self):
        credentials.KEYCHAIN = None
        credentials.CLIPBOARD = None
        term.SECRETS.clear()

    def test_control_characters_never_stored(self):
        s = FakeScreen(["\x16", "a" * 40])  # Ctrl+V in a Windows hidden prompt gives \x16
        v = credentials.secret("svc", "me", s, validate=r"[0-9a-f]{40}")
        self.assertEqual(v, "a" * 40)
        self.assertEqual(credentials.keychain().get("svc", "me"), "a" * 40)
        self.assertTrue(any("controllo" in t or "control" in t for t in s.told))

    def test_format_checked(self):
        s = FakeScreen(["short", "also bad", "nope"])
        self.assertIsNone(credentials.secret("svc", "me", s, validate=r"[0-9a-f]{40}"))
        self.assertIsNone(credentials.keychain().get("svc", "me"))

    def test_from_clipboard_then_cleared(self):
        self.clip["value"] = "  " + "b" * 40 + "\r\n"
        s = FakeScreen([""])  # empty answer → offer the clipboard
        self.assertEqual(credentials.secret("svc", "me", s, validate=r"[0-9a-f]{40}"), "b" * 40)
        self.assertTrue(self.clip["cleared"])


class PageProgress(unittest.TestCase):
    def test_pages_report_progress(self):
        items = [{"id": i} for i in range(10)]

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = dict(x.split("=") for x in self.path.split("?")[1].split("&"))
                off, lim = int(q["offset"]), int(q["limit"])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"issues": items[off:off + lim], "total_count": 10}).encode())
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        seen = []
        old = webapi.progress
        webapi.progress = lambda f=None, d=None: seen.append((f, d))
        try:
            list(ReadOnlyClient(f"http://127.0.0.1:{srv.server_port}").pages("/i", items="issues", limit=4))
        finally:
            webapi.progress = old
            srv.shutdown()
            srv.server_close()
        self.assertEqual([round(f, 1) for f, _ in seen], [0.4, 0.8, 1.0])
        self.assertEqual(seen[-1][1], "10/10 issues")


class MenuSession(unittest.TestCase):
    def test_kept_open_across_actions_closed_at_end(self):
        log = []
        with access.session(idle_minutes=5):
            for _ in range(3):
                with temporary(lambda: log.append("open"), lambda: log.append("close"), label="VPN"):
                    log.append("use")
            self.assertIn("VPN", access.status_line())
        self.assertEqual(log, ["open", "use", "use", "use", "close"])
        self.assertEqual(access.status_line(), "")

    def test_closed_on_error(self):
        log = []
        with self.assertRaises(KeyboardInterrupt):
            with access.session(idle_minutes=5):
                with temporary(lambda: log.append("open"), lambda: log.append("close"), label="VPN"):
                    raise KeyboardInterrupt
        self.assertEqual(log, ["open", "close"])

    def test_closed_after_idle(self):
        log = []
        with access.session(idle_minutes=0.002, check_every=0.02):  # ~0.12 s
            with temporary(lambda: log.append("open"), lambda: log.append("close"), label="VPN"):
                pass
            time.sleep(0.5)
            self.assertEqual(log, ["open", "close"])
            with temporary(lambda: log.append("open"), lambda: log.append("close"), label="VPN"):
                pass
        self.assertEqual(log, ["open", "close", "open", "close"])

    def test_outside_menu_unchanged(self):
        log = []
        for _ in range(2):
            with temporary(lambda: log.append("open"), lambda: log.append("close"), label="VPN"):
                pass
        self.assertEqual(log, ["open", "close", "open", "close"])


class LocalCopy(unittest.TestCase):
    def test_memory_only_writes_nothing(self):
        home = tempfile.mkdtemp()
        app = App("t-copy")
        app.cache_dir = os.path.join(home, "cache")
        calls = []
        fetch = lambda: calls.append(1) or [1, 2]
        self.assertEqual(app.snapshot("x", fetch, keep=False)[0], [1, 2])
        self.assertEqual(app.snapshot("x", fetch, keep=False)[0], [1, 2])
        self.assertEqual(len(calls), 1)  # kept in memory for this run
        self.assertEqual(os.listdir(home), [])

    def test_info_and_forget(self):
        app = App("t-copy2")
        app.cache_dir = tempfile.mkdtemp()
        self.assertIsNone(app.snapshot_info("x"))
        app.snapshot("x", lambda: {"a": 1})
        path, size, taken = app.snapshot_info("x")
        self.assertTrue(path.endswith("x.json") and size > 0 and taken)
        self.assertTrue(app.forget_snapshot("x"))
        self.assertIsNone(app.snapshot_info("x"))
        self.assertFalse(app.forget_snapshot("x"))


class DownloadNotices(unittest.TestCase):
    def test_first_then_estimate_then_memory_warning(self):
        app = App("t-notes")
        app.cache_dir = tempfile.mkdtemp()
        s = FakeScreen()
        app.snapshot("x", lambda: [1, 2, 3], screen=s)
        text = " ".join(s.told)
        self.assertIn("Primo download", text)
        self.assertIn("--aggiorna", text)
        self.assertIn("scaricati 3 elementi", text)
        s.told.clear()
        app.snapshot("x", lambda: [1, 2, 3], screen=s)
        self.assertEqual(s.told, [])  # from the local copy: nothing to warn about
        app.snapshot("x", lambda: [1, 2, 3], refresh=True, screen=s)
        self.assertIn("l'ultima volta", " ".join(s.told))
        s.told.clear()
        app.snapshot("y", lambda: [1], keep=False, screen=s)
        self.assertIn("ogni avvio riscarica", " ".join(s.told))


class Hints(unittest.TestCase):
    """The bottom line names only the keys that work in that moment."""
    def test_each_state(self):
        sc = term.Screen("t", lang="it")
        sc.mode = "idle"
        self.assertNotIn("↑↓", sc.hint())
        self.assertNotIn("Invio", sc.hint())
        sc.mode = "choose"
        self.assertIn("↑↓", sc.hint())
        sc.mode = "type"
        self.assertNotIn("↑↓", sc.hint())
        self.assertIn("Invio", sc.hint())
        sc.mode = "read"
        self.assertIn("/", sc.hint())
        self.assertNotIn("Invio conferma", sc.hint())

    def test_plain_header_has_no_arrows(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            term.Screen("t").header("x")
        self.assertNotIn("↑↓", buf.getvalue())

    def test_status_line_in_menu(self):
        sc = term.Screen("t")
        with access.session(idle_minutes=5):
            with temporary(lambda: True, lambda: None, label="VPN"):
                pass
            self.assertIn("VPN aperta da 0 min", sc.hint())


class Limits(unittest.TestCase):
    def test_client_rate_limit_waits_and_says_so(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        said = []
        old = webapi.progress
        webapi.progress = lambda f=None, d=None: said.append(d)
        try:
            api = ReadOnlyClient(f"http://127.0.0.1:{srv.server_port}", rate=(3, 0.6))
            start = time.time()
            for _ in range(4):
                api.get("/x")
            self.assertGreaterEqual(time.time() - start, 0.5)
        finally:
            webapi.progress = old
            srv.shutdown()
            srv.server_close()
        self.assertTrue(any("troppe richieste" in (d or "") for d in said))

    def test_refresh_cooldown(self):
        app = App("t-cool")
        app.cache_dir = tempfile.mkdtemp()
        calls, s = [], FakeScreen()
        fetch = lambda: calls.append(1) or [1]
        app.snapshot("x", fetch)
        app.snapshot("x", fetch, refresh=True, min_refresh_minutes=10, screen=s)
        self.assertEqual(len(calls), 1)
        self.assertIn("al massimo ogni 10 min", " ".join(s.told))
        app.snapshot("x", fetch, refresh=True, min_refresh_minutes=0)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
