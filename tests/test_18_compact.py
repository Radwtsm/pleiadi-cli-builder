"""Compact mode (BACKLOG 4): below term.COMPACT (70 columns or 22 rows) the title on one line instead of the box with
the logo, the tool's notices right under it, the menu items as «[m] Mie» with their short label, a shorter key line;
a window that grows again gets the normal view back, also while a menu is open."""
import os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, screentest, term
from pleiadi_cli_builder.screentest import keys, run_screen, size, wait

plain = lambda ls: [term.ANSI.sub("", l).rstrip() for l in ls]


def screen():
    s = term.Screen("t", "Prova")
    s.head, s.rows, s.subtitle = ["box"], ["✦ Prova  t", "  menu", "  2 novità sulle tue task"], "menu"
    s.body = ["", "  ? Cosa vuoi fare?"]
    return s


class Thresholds(unittest.TestCase):
    """Without a terminal: it also runs on Windows."""
    def test_one_threshold(self):
        self.assertEqual(term.COMPACT, (70, 22))
        for w, h in ((69, 40), (120, 21), (40, 15), (60, 20)):
            self.assertTrue(term.Screen.compact(w, h), (w, h))
        for w, h in ((70, 22), (80, 24), (120, 40)):
            self.assertFalse(term.Screen.compact(w, h), (w, h))

    def test_logo_and_box_only_in_the_normal_view(self):
        big = plain(screen().layout(80, 24))
        self.assertTrue(any("▀███▀" in r for r in big))
        for w, h in ((69, 24), (80, 21)):
            got = plain(screen().layout(w, h))
            self.assertFalse(any("█" in r or "╭" in r for r in got), got)
            self.assertEqual(got[0], "✦ Prova  t · menu")  # the title on one line, with the subtitle
            self.assertEqual(got[1], "  2 novità sulle tue task")  # the notices right under it

    def test_short_key_line(self):
        s = screen()
        s.mode = "back"
        long_, short = plain(s.layout(80, 24))[-1], plain(s.layout(40, 15))[-1]
        self.assertIn("Esc", short)
        self.assertLess(len(short), len(long_))
        self.assertLessEqual(len(short), 40)
        s.narrow = False
        self.assertEqual(s.hint(), term.TEXTS["it"]["hint_back"])

    def test_menu_row_with_letter(self):
        s = term.Screen("t")
        s.narrow = True
        self.assertEqual(plain([s._menu_row(1, "Mie", sel=0, n=3, rec="", key="m")])[0], "    [m] Mie")
        bar = s._menu_row(1, "Mie", sel=1, n=3, rec="", key="m")
        self.assertIn("[m] Mie", plain([bar])[0])
        self.assertIn("1.", plain([s._menu_row(0, "Senza lettera", sel=1, n=3, rec="")])[0])  # no letter: as before

    def test_short_labels(self):
        app = App("x")
        app.command("mie", menu="Le mie task", key="m", short="Mie")(lambda s, a: 0)
        app.command("doctor", menu="Controlla che sia tutto a posto")(lambda s, a: 0)
        self.assertEqual(app.commands["mie"].short, "Mie")
        self.assertEqual(app.menu_short(), ["Mie", "Controlla che sia tutto a posto", "Esci"])


MENU = """import sys; sys.path.insert(0, {root!r})
from pleiadi_cli_builder import App
app = App("demo", title="Demo kit", banner_info=lambda: ["2 novità sulle tue task"], menu_subtitle="i progetti")
for name, label, short, key in (("mie", "Le mie task", "Mie", "m"), ("novita", "Novità sulle mie task", "Novità", "n"),
                                ("progetti", "Tutti i progetti attivi, i più a rischio prima", "Progetti", None),
                                ("setup", "Prepara demo kit", "Prepara", "s"),
                                ("altro", "Altre cose che si possono fare", "Altro", None)):
    app.command(name, menu=label, short=short, key=key)(lambda s, a: 0)
app.main([])
"""


@unittest.skipUnless(screentest.available(), "no pty")
class Resized(unittest.TestCase):
    def test_large_small_smaller_large(self):
        with tempfile.TemporaryDirectory() as home:
            s = run_screen([sys.executable, "-c", MENU.format(root=ROOT)],
                           [wait("Cosa vuoi fare?"), keys("down", "down"), size(60, 20), size(40, 15), size(100, 30)], 100, 30,
                           env={"PCB_GLYPHS": "full", "HOME": home, "USERPROFILE": home})
        self.assertEqual(s.problems(expect=["Cosa vuoi fare?", "Esci", "2 novità"]), [], s.report())
        big, mid, small, back = s.last_frames()
        for f in (big, back):  # normal view: box, logo, the full labels with their chip
            self.assertIn("▀███▀", f.text(), s.report())
            self.assertIn("Le mie task", f.text())
            self.assertNotIn("[m]", f.text())
        for f in (mid, small):  # compact: title on one line, notices on top, [letter] short label
            self.assertNotIn("█", f.text(), s.report())
            self.assertTrue(f.lines[0].startswith("✦ Demo kit"), s.report())
            self.assertIn("2 novità", f.lines[1])
            for label in ("[m] Mie", "[n] Novità", "[s] Prepara", "Altro", "[q] Esci"):
                self.assertIn(label, f.text(), s.report())
            self.assertNotIn("Le mie task", f.text())
            self.assertFalse([l for l in f.lines if "…" in l], s.report())  # menu rows and short key line fit whole
            self.assertIn("Esc", f.lines[-1])


if __name__ == "__main__":
    unittest.main()
