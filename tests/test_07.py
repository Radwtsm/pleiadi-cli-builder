"""0.7: the scrolling detail view (pure pager logic, plain text, JSON) and pickable tables."""
import io, json, os, sys, unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import Detail, Screen, term
from pleiadi_cli_builder.detail import Pager


def sample():
    long = "Questa è una descrizione lunga " * 20
    return Detail("Task 42 · Pagina contatti",
                  fields=[("stato", "In corso", None), ("scadenza", "2026-10-20", "alarm"), ("persona", "Anna Prova", "ok")],
                  sections=[("Descrizione", [(long, None), ("riga con parola-chiave", "warn")]),
                            ("Note", [(f"nota {i}", None) for i in range(30)], True),
                            ("Allegati", [("logo.png · 12 KB", "dim")])],
                  legend={"alarm": "in ritardo", "warn": "attenzione", "ok": "assegnata a te"})


def plain(text):
    return term.ANSI.sub("", text)


class PagerLogic(unittest.TestCase):
    def test_wraps_to_width_and_rewraps(self):
        p = Pager(sample(), width=40, height=12)
        self.assertTrue(all(len(plain(l)) <= 40 for l in p.lines()))
        n40 = len(p.lines())
        p.resize(80, 12)
        self.assertLess(len(p.lines()), n40)

    def test_scroll_keys(self):
        p = Pager(sample(), width=60, height=10)
        self.assertEqual(p.top, 0)
        p.handle("down")
        self.assertEqual(p.top, 1)
        p.handle("pgdn")
        self.assertGreater(p.top, 1)
        p.handle("end")
        self.assertEqual(p.top, p.max_top())
        p.handle("home")
        self.assertEqual(p.top, 0)
        self.assertEqual(p.handle("q"), "quit")

    def test_collapse_and_expand(self):
        p = Pager(sample(), width=60, height=10)
        text = "\n".join(plain(l) for l in p.lines())
        self.assertIn("▸ Note (30 righe)", text)  # collapsed from the start: the tool said so
        self.assertNotIn("nota 5", text)
        p.toggle("Note")
        self.assertIn("nota 5", "\n".join(plain(l) for l in p.lines()))

    def test_search_jumps_and_next(self):
        p = Pager(sample(), width=60, height=8)
        p.search("nota 2")  # also inside a collapsed section: it opens it
        first = p.top
        self.assertIn("nota 2", plain(p.lines()[p.hits[p.hit]]))
        p.handle("n")
        self.assertGreater(p.top, first)  # «nota 2», then «nota 20»…
        self.assertEqual(p.search("assente"), 0)

    def test_view_has_fixed_header(self):
        p = Pager(sample(), width=60, height=10)
        p.handle("end")
        head = [plain(l) for l in p.header()]
        self.assertTrue(any("scadenza" in l and "2026-10-20" in l for l in head))
        self.assertTrue(any("in ritardo" in l for l in p.legend_lines()))


class OutsideTerminal(unittest.TestCase):
    def test_plain_text_everything_open(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            Screen("t").detail(sample())
        out = buf.getvalue()
        self.assertIn("Task 42", out)
        self.assertIn("nota 29", out)  # collapsed sections are printed whole outside a terminal
        self.assertIn("in ritardo", out)

    def test_json(self):
        s = Screen("t")
        s.json = True
        buf = io.StringIO()
        with redirect_stdout(buf):
            s.detail(sample())
        d = json.loads(buf.getvalue())
        self.assertEqual(d["title"], "Task 42 · Pagina contatti")
        self.assertEqual(d["fields"]["scadenza"], "2026-10-20")
        self.assertEqual(len(d["sections"]["Note"]), 30)


class Pick(unittest.TestCase):
    def test_pick_outside_terminal_is_none(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertIsNone(Screen("t").table([{"id": 1}], pick=True))


class FullScreen(unittest.TestCase):
    def test_keys_in_a_pty(self):
        if os.name == "nt":
            self.skipTest("no pty")
        import pty, select, time
        script = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
                  "from test_07 import sample\nfrom pleiadi_cli_builder import Screen\n"
                  "s = Screen('t'); s.detail(sample()); s.close(); print('USCITO')\n") % (ROOT, os.path.dirname(__file__))
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update(TERM="xterm-256color", COLUMNS="70", LINES="20")
            os.execv(sys.executable, [sys.executable, "-c", script])
        data, keys = b"", [b"j", b"\x1b[6~", b"/", b"nota 2", b"\r", b"n", b" ", b"\x1b[H", b"q"]
        end = time.time() + 15
        while time.time() < end:
            r = select.select([fd], [], [], 0.3)[0]
            if r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                data += chunk
            elif keys:
                os.write(fd, keys.pop(0))
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, data[-400:])
        self.assertIn(b"USCITO", data)
        self.assertIn(b"nota 2", data)  # the search opened the folded section
        self.assertIn("/ cerca".encode(), data)  # the read-mode hint, not the menu one


if __name__ == "__main__":
    unittest.main()
