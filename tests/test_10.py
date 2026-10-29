"""0.10: colors by role, like Claude Code — one accent for what is interactive or selected, muted for what is
secondary, state colors only for a meaning; keys stand out in the hints; the selected row is a full-width bar."""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path[:0] = [ROOT, os.path.dirname(os.path.abspath(__file__))]  # test_09 too, even with python -I
from pleiadi_cli_builder import Theme, term
from pleiadi_cli_builder.detail import Pager
from test_09 import detail

plain = lambda s: term.ANSI.sub("", s)


def colored(theme=None):
    s = term.Screen("t", theme=theme)
    s.colors = True
    return s


class Hints(unittest.TestCase):
    def test_keys_accent_labels_muted(self):
        s = colored()
        h = s.keys([("↑↓", "scegli"), ("Invio", "conferma")])
        self.assertEqual(plain(h), "↑↓ scegli · Invio conferma")
        self.assertIn(f"\033[{s.theme.accent};1m↑↓", h)  # the key: accent, bold
        self.assertIn(f"\033[{s.theme.dim}m scegli", h)  # what it does: muted

    def test_every_mode_uses_it(self):
        s = colored()
        for mode in ("idle", "choose", "type", "read"):
            s.mode = mode
            self.assertIn(f"\033[{s.theme.accent};1m", s.hint_line())


class Selection(unittest.TestCase):
    def test_selected_row_is_a_bar(self):
        s = colored()
        row = s._menu_row(1, "Le mie task", sel=1, n=3, rec="")
        self.assertIn("48;5;", row)  # background on the selected row
        self.assertEqual(len(plain(row)), s.text_width())  # across the whole width
        other = s._menu_row(0, "Tutti i progetti", sel=1, n=3, rec="")
        self.assertNotIn("48;5;", other)

    def test_current_section_is_a_bar(self):
        p = Pager(detail(), width=60, height=12, color=colored().c)
        head = next(l for l in p.lines() if "Descrizione" in l)
        self.assertIn("48;5;", head)


class Tables(unittest.TestCase):
    def test_header_muted_with_a_rule(self):
        s = colored()
        out = []
        s.out = out.append
        s.table([{"id": 1, "titolo": "x"}])
        self.assertTrue(plain(out[1]).strip().startswith("──"))  # a rule under the column titles
        self.assertIn("\033[1m", out[0])


class Roles(unittest.TestCase):
    def test_theme_has_the_roles(self):
        t = Theme()
        for role in ("accent", "dim", "bold", "ok", "warn", "error", "select"):
            self.assertTrue(getattr(t, role), role)


if __name__ == "__main__":
    unittest.main()
