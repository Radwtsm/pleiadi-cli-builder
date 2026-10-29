"""0.11: shortcuts on every screen — the keys of this screen's own operations stand out (a chip in the accent) from
the generic ones (arrows, Enter, quit), so it is clear they belong to what is on screen; menu items get a letter."""
import io, os, sys, unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path[:0] = [ROOT, os.path.dirname(os.path.abspath(__file__))]  # test_09 too, even with python -I
from pleiadi_cli_builder import App, Board, term
from pleiadi_cli_builder.board import BoardView
from pleiadi_cli_builder.detail import Pager
from test_09 import detail

plain = lambda s: term.ANSI.sub("", s)


def colored():
    s = term.Screen("t")
    s.colors = True
    return s


class Highlight(unittest.TestCase):
    def test_contextual_keys_are_a_chip(self):
        s = colored()
        ctx = s.keys([("d", "scarica")], context=True)
        self.assertIn(f"\033[{s.theme.shortcut}m d ", ctx)  # this screen's key: a chip
        self.assertNotIn(f"\033[{s.theme.accent};1md", ctx)
        self.assertNotEqual(s.theme.shortcut, f"{s.theme.accent};1")

    def test_screen_line_puts_them_first(self):
        s = colored()
        line = s.shortcut_line("↑↓ scorri · q chiudi", {"d": ("scarica", None), "c": ("copia", None)})
        self.assertLess(plain(line).index(" d  scarica"), plain(line).index("↑↓ scorri"))
        self.assertEqual(line.count(f"\033[{s.theme.shortcut}m"), 2)

    def test_views_split_their_own_keys(self):
        p = Pager(detail({"d": ("scarica allegati", lambda s: "ok")}), width=60, height=12)
        self.assertNotIn("scarica", p.nav())
        v = BoardView(Board("x", ["n"], [("G", [{"n": 1}])], actions={"b": ("build", None)}))
        self.assertNotIn("build", v.nav())
        self.assertIn("Spazio", v.nav())


class MenuLetters(unittest.TestCase):
    def test_letter_picks_at_once(self):
        s = colored()
        s.full = True
        keys = iter(["m"])
        with mock.patch.object(term, "key", lambda: next(keys)), mock.patch.object(term.Screen, "open", lambda self: None), \
                mock.patch.object(term.Screen, "draw", lambda self: None), mock.patch("sys.stdin.isatty", lambda: True):
            self.assertEqual(s.choose("Cosa?", ["Prepara", "Le mie task", "Esci"], keys=["s", "m", "q"]), 1)

    def test_row_shows_the_letter(self):
        s = colored()
        row = s._menu_row(1, "Le mie task", sel=0, n=3, rec="", key="m")
        self.assertIn(f"\033[{s.theme.shortcut}m m ", row)
        bar = s._menu_row(1, "Le mie task", sel=1, n=3, rec="", key="m")
        self.assertIn(f"\033[{s.theme.shortcut}m m ", bar)

    def test_typed_letter_without_terminal(self):
        s = term.Screen("t")
        with mock.patch.object(s, "ask", lambda *a: "m"), redirect_stdout(io.StringIO()):
            self.assertEqual(s.choose("Cosa?", ["Prepara", "Le mie task"], keys=["s", "m"]), 1)

    def test_app_gives_every_item_a_letter(self):
        app = App("x")
        for name, label, k in (("setup", "Prepara", None), ("mie", "Le mie task", "m"), ("menu2", "Mostra tutto", None)):
            app.command(name, menu=label, key=k)(lambda s, a: 0)
        letters = app.menu_keys()
        self.assertEqual(letters, ["p", "m", "o", "q"])  # chosen ones win; others: the first free letter; q = quit
        self.assertEqual(len(set(letters)), len(letters))


class JsonStdoutClean(unittest.TestCase):
    """From a tool using the library: with --json set by the tool itself, a wait line came out on stdout before
    the JSON (the full screen was still on)."""
    def test_wait_and_lines_never_on_stdout(self):
        s = colored()
        s.full, s.json = True, True
        out, err = io.StringIO(), io.StringIO()
        from contextlib import redirect_stderr
        with redirect_stdout(out), redirect_stderr(err), mock.patch.object(term.Screen, "open", lambda self: None):
            with s.wait("scarico"):
                pass
            s.out("nota")
            s.data({"a": 1})
        self.assertEqual(out.getvalue().strip(), '{\n "a": 1\n}')
        self.assertIn("nota", err.getvalue())


if __name__ == "__main__":
    unittest.main()
