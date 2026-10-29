"""0.9: a visible current section in the detail view, one-key actions, clipboard copy, same-host downloads."""
import http.server, os, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import Detail, ReadOnlyClient, credentials, term
from pleiadi_cli_builder.detail import Pager

plain = lambda l: term.ANSI.sub("", l)


def detail(actions=None):
    return Detail("Task 7", fields=[("stato", "Nuova", None)],
                  sections=[("Descrizione", [(f"riga {i}", None) for i in range(12)]),
                            ("Note", [("nota", None)], True), ("Allegati", [("a.png · 1 KB", None)])],
                  actions=actions)


class CurrentSection(unittest.TestCase):
    def test_marked_and_moved_with_tab(self):
        p = Pager(detail(), width=60, height=12)
        text = [plain(l) for l in p.lines()]
        self.assertIn("▶ ▾ Descrizione", text)  # the one Space acts on is marked
        self.assertIn("  ▸ Note (1 righe)", text)
        p.handle("tab")
        self.assertIn("▶ ▸ Note (1 righe)", [plain(l) for l in p.lines()])
        p.handle(" ")  # opens the marked one, not the one at the top of the screen
        self.assertIn("▶ ▾ Note", [plain(l) for l in p.lines()])
        p.handle("backtab")
        self.assertIn("▶ ▾ Descrizione", [plain(l) for l in p.lines()])

    def test_follows_scrolling(self):
        p = Pager(detail(), width=60, height=8)
        p.handle("end")
        cur = [plain(l) for l in p.lines() if plain(l).startswith("▶")]
        self.assertEqual(len(cur), 1)
        self.assertNotIn("Descrizione", cur[0])  # scrolled past it: the mark moved on


class Actions(unittest.TestCase):
    def test_keys_and_hint(self):
        p = Pager(detail({"d": ("scarica allegati", lambda s: "ok"), "c": ("copia il numero", lambda s: "ok")}),
                  width=60, height=12)
        self.assertEqual(p.handle("d"), ("action", "d"))
        self.assertIsNone(p.handle("x"))
        self.assertIn("d scarica allegati", p.hint())
        self.assertIn("Tab", p.hint())


class Clipboard(unittest.TestCase):
    def tearDown(self):
        credentials.CLIPBOARD = None

    def test_copy(self):
        got = []
        credentials.CLIPBOARD = {"read": lambda: "", "clear": lambda: None, "write": got.append}
        self.assertTrue(credentials.copy_to_clipboard("#7"))
        self.assertEqual(got, ["#7"])


class Download(unittest.TestCase):
    def test_same_host_only_and_atomic(self):
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append(self.headers.get("X-Key"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"PNG" * 1000)
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{srv.server_port}"
            api = ReadOnlyClient(base, token="k", header="X-Key", scheme="")
            dest = os.path.join(tempfile.mkdtemp(), "7", "a.png")
            self.assertEqual(api.download(base + "/attachments/download/1/a.png", dest), 3000)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(3), b"PNG")
            self.assertEqual(seen, ["k"])
            with self.assertRaises(ValueError):  # the key never goes to another host
                api.download("http://other.example/x.png", dest)
            self.assertEqual(seen, ["k"])
            self.assertFalse(os.path.exists(dest + ".tmp"))
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
