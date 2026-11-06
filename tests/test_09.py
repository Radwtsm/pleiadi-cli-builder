"""0.9: a visible current section in the detail view, one-key actions, clipboard copy, same-host downloads."""
import http.server, os, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import Detail, ReadOnlyClient, credentials, term
from pleiadi_cli_builder.detail import Pager

plain = lambda l: term.ANSI.sub("", l).rstrip()  # the marked title is a bar padded to the width


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

    def test_at_the_bottom_the_arrows_pick_the_sections_below(self):
        """Owner 06/11: scrolled to the bottom, the folded notes below could not be picked with the arrows."""
        sections = [("Descrizione", [(f"riga {i}", None) for i in range(15)])] + \
                   [(f"Nota {i}", [("testo", None)] * 6, i >= 3) for i in range(10)]
        p = Pager(Detail("Task 7", sections=sections), width=60, height=24)
        marked = lambda: p.d.sections[p.cur][0]
        p.handle("end")
        self.assertEqual(p.top, p.max_top())
        self.assertEqual(marked(), "Nota 2")  # the first title on screen, as before
        seen = {marked()}
        for _ in range(20):
            p.handle("down")
            seen.add(marked())
        self.assertEqual(marked(), "Nota 9")  # the last one, and it stays there
        self.assertTrue({f"Nota {i}" for i in range(3, 10)} <= seen, "every folded note below was marked on the way")
        p.handle(" ")
        self.assertIn("▶ ▾ Nota 9", [plain(l) for l in p.lines()])
        bottom = p.top
        p.handle("up")  # the page can scroll up again: the arrow scrolls it
        self.assertEqual(p.top, bottom - 1)

    def test_at_the_top_up_goes_back_to_the_first_section(self):
        p = Pager(detail(), width=60, height=40)  # everything fits: the arrows only move the mark
        p.handle("down")
        p.handle("down")
        self.assertEqual(p.d.sections[p.cur][0], "Allegati")
        p.handle("up")
        p.handle("up")
        p.handle("up")
        self.assertEqual(p.d.sections[p.cur][0], "Descrizione")
        self.assertEqual(p.top, 0)


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


class PickHasHeader(unittest.TestCase):
    """Owner 29/10: «le tabelle non hanno intestazione» — the rows to choose came without the column titles."""
    def test_header_above_the_choices_and_rows_once(self):
        from unittest import mock
        s = term.Screen("t")
        s.full = True
        printed, asked = [], {}
        s.out = printed.append

        def choose(question, options, header=None):
            asked.update(q=question, options=options, header=header)
            return 1
        with mock.patch.object(term.Screen, "interactive", new=True):
            s.choose = choose
            i = s.table([{"id": 101, "titolo": "Home page"}, {"id": 103, "titolo": "Menu"}], pick=True)
        self.assertEqual(i, 1)
        self.assertIn("titolo", term.ANSI.sub("", asked["header"]))
        self.assertTrue(asked["options"][0].startswith("101"))
        self.assertFalse(any("Home page" in term.ANSI.sub("", l) for l in printed))  # not printed twice

    def test_menu_rows_align_under_the_header(self):
        s = term.Screen("t")
        rows = [s._menu_row(i, f"r{i}", sel=0, n=12, rec="") for i in (0, 9)]
        head = s._menu_header("COL", 12)
        col = term.ANSI.sub("", head).index("COL")
        self.assertEqual(term.ANSI.sub("", rows[1]).index("r9"), col)
        self.assertEqual(term.ANSI.sub("", rows[0]).index("r0"), col)


if __name__ == "__main__":
    unittest.main()
