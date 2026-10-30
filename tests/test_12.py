"""0.12: lines new since the last look — marked ● in the detail view, n/N jump between them with «2/7» in the
bottom line when no search is on, the view opens on the first one, an empty search gives n/N back to them."""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import Detail, term
from pleiadi_cli_builder.detail import Pager

plain = lambda l: term.ANSI.sub("", l).rstrip()


def detail():
    return Detail("Task 7", fields=[("stato", "Nuova", None)],
                  sections=[("Cosa è cambiato", [("stato: Nuova → In corso", None), ("2 note sotto", "dim")], False, 1),
                            ("Descrizione", [(f"riga {i}", None) for i in range(12)]),
                            ("Nota · ieri", [("nuova A", None), ("nuova B", None)], True, True),
                            ("Nota · prima", [("vecchia", None)], True)])


class NewLines(unittest.TestCase):
    def test_marked_and_unfolded(self):
        p = Pager(detail(), width=60, height=10)
        text = [plain(l) for l in p.lines()]
        self.assertIn("● stato: Nuova → In corso", text)
        self.assertIn("  2 note sotto", text)  # only the first `new` lines of a section
        self.assertIn("● nuova B", text)  # a section with new lines never starts folded
        self.assertIn("  ▸ Nota · prima (1 righe)", text)
        self.assertEqual(len(p.news), 3)

    def test_n_walks_them_with_a_counter(self):
        p = Pager(detail(), width=60, height=10)
        self.assertEqual(p.new_at, 0)  # opens on the first one
        self.assertIn("n/N nuove 1/3", p.nav())
        self.assertEqual(term.pairs(p.nav())[-2], ("n/N", "nuove 1/3"))  # one label in the bottom line
        p.handle("n")
        p.handle("n")
        self.assertIn("nuove 3/3", p.nav())
        self.assertIn("● nuova B", plain(p.render()[p.news[2] - p.top + len(p.header())]))  # in view
        p.handle("n")
        self.assertEqual(p.new_at, 0)  # round
        p.handle("N")
        self.assertEqual(p.new_at, 2)

    def test_search_takes_n_then_gives_it_back(self):
        p = Pager(detail(), width=60, height=10)
        p.search("riga")
        self.assertIn("n successiva", p.nav())
        p.handle("n")
        self.assertEqual((p.hit, p.new_at), (1, 0))
        p.search("")
        p.handle("n")
        self.assertEqual(p.new_at, 1)

    def test_plain_and_json(self):
        d = detail()
        self.assertIn("● nuova A", Pager(d).plain())
        self.assertEqual(d.as_dict()["new"], {"Cosa è cambiato": ["stato: Nuova → In corso"],
                                              "Nota · ieri": ["nuova A", "nuova B"]})
        self.assertNotIn("new", Detail("x", sections=[("a", [("b", None)])]).as_dict())

    def test_nothing_new_as_before(self):
        p = Pager(Detail("x", sections=[("a", [("b", None)])]), width=60, height=10)
        self.assertEqual((p.news, p.new_at), ([], -1))
        self.assertIn("n successiva", p.nav())
        p.handle("n")  # nothing to do, no error


if __name__ == "__main__":
    unittest.main()
