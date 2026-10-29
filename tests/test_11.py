"""0.11: a table in groups with check marks (Board): columns filled in the background, one-key actions on the
checked rows — e.g. working copies of projects grouped by product, with the slow columns (last build, last check)
arriving while the table is already on screen."""
import io, os, sys, threading, unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import Board, term
from pleiadi_cli_builder.board import BoardView

plain = lambda l: term.ANSI.sub("", l).rstrip()


def board(fill=None, actions=None):
    return Board("Copie", ["nome", "debug", "release"],
                 [("Prodotto A", [{"nome": "a-core"}, {"nome": "a-web"}]), ("Prodotto B", [{"nome": "b-app"}])],
                 titles={"debug": "build Debug"}, fill=fill, actions=actions)


class Groups(unittest.TestCase):
    def test_groups_rows_and_header(self):
        v = BoardView(board(), width=60, height=12)
        text = [plain(l) for l in v.render()]
        self.assertIn("0 di 3 spuntate", text[0])
        self.assertIn("build Debug", text[1])  # the column titles, with a rule under them
        self.assertTrue(text[2].strip().startswith("──"))
        self.assertTrue(any("Prodotto A" in l and "(2)" in l for l in text))
        self.assertTrue(any("[ ] a-web" in l for l in text))

    def test_space_checks_a_row_or_a_whole_group(self):
        v = BoardView(board(), width=60, height=12)
        v.handle(" ")  # the cursor starts on the first group: the whole group
        self.assertEqual([r["nome"] for r in v.checked()], ["a-core", "a-web"])
        v.handle("down")
        v.handle(" ")  # one row off again
        self.assertEqual([r["nome"] for r in v.checked()], ["a-web"])
        self.assertTrue(any("[–]" in plain(l) and "Prodotto A" in plain(l) for l in v.render()))  # partly checked
        v.handle("a")  # all
        self.assertEqual(len(v.checked()), 3)
        v.handle("a")  # all already: none
        self.assertEqual(v.checked(), [])

    def test_cursor_stays_on_screen(self):
        rows = [{"nome": f"r{i}"} for i in range(40)]
        v = BoardView(Board("x", ["nome"], [("G", rows)]), width=40, height=10)
        v.handle("end")
        self.assertTrue(any("r39" in plain(l) for l in v.render()))
        self.assertEqual(len(v.render()), 10)

    def test_json_rows_have_the_group(self):
        self.assertEqual(board().as_rows()[2], {"gruppo": "Prodotto B", "nome": "b-app", "debug": None, "release": None})


class Background(unittest.TestCase):
    def test_filled_while_on_screen(self):
        gate = threading.Event()

        def slow(row):
            gate.wait(5)
            return "ok " + row["nome"]
        b = board(fill={"debug": slow})
        changed = threading.Event()
        b.start(on_change=changed.set)
        v = BoardView(b, width=60, height=12)
        self.assertTrue(any("…" in plain(l) for l in v.render()))  # not there yet: a mark, the table already shown
        gate.set()
        b.wait(5)
        self.assertTrue(changed.is_set())
        self.assertEqual(b.groups[0][1][1]["debug"], "ok a-web")

    def test_a_failing_cell_says_so_and_the_rest_arrives(self):
        def fill(row):
            if row["nome"] == "a-web":
                raise OSError("disco")
            return "ok"
        b = board(fill={"debug": fill})
        b.start()
        b.wait(5)
        self.assertEqual([r["debug"] for _, rows in b.groups for r in rows][0::2], ["ok", "ok"])
        self.assertIn("disco", b.groups[0][1][1]["debug"])


class Actions(unittest.TestCase):
    def test_on_checked_rows_or_the_current_one(self):
        got = []
        b = board(actions={"s": ("sincronizza", lambda screen, rows: got.append([r["nome"] for r in rows]) or "fatto")})
        v = BoardView(b, width=60, height=12)
        self.assertEqual(v.handle("s"), ("action", "s"))
        v.handle("down")  # nothing checked: the row under the cursor
        self.assertEqual([r["nome"] for r in v.targets()], ["a-core"])
        v.handle(" ")
        v.handle("down")
        v.handle(" ")
        self.assertEqual([r["nome"] for r in v.targets()], ["a-core", "a-web"])
        self.assertIn("s sincronizza", v.hint())
        self.assertIn("Spazio", v.hint())

    def test_screen_runs_the_action_and_refills_the_rows(self):
        calls = {"fill": 0}

        def fill(row):
            calls["fill"] += 1
            return "v%d" % calls["fill"]
        done = []
        b = board(fill={"debug": fill}, actions={"b": ("build", lambda screen, rows: done.extend(rows) or "2 build")})
        s = term.Screen("t")
        s.full, s.colors = True, True
        keys = iter([" ", "b", "enter"])  # the first group, the action, then Enter = done
        with mock.patch.object(term.Screen, "interactive", new=True), mock.patch.object(term, "key", lambda: next(keys)), \
                mock.patch.object(term.Screen, "open", lambda self: None), mock.patch.object(term.Screen, "draw", lambda self: None):
            chosen = s.board(b)
        self.assertEqual([r["nome"] for r in done], ["a-core", "a-web"])
        self.assertEqual([r["nome"] for r in chosen], ["a-core", "a-web"])
        b.wait(5)
        self.assertEqual(calls["fill"], 5)  # 3 at the start, then again the 2 the action touched

    def test_plain_without_terminal(self):
        b = board(fill={"debug": lambda row: "ok"})
        s = term.Screen("t")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertIsNone(s.board(b))
        text = out.getvalue()
        self.assertIn("Prodotto A", text)
        self.assertIn("a-core", text)
        self.assertNotIn("…", text)  # without a terminal it waits for every cell
        self.assertNotIn("[ ]", text)

    def test_json(self):
        b = board(fill={"debug": lambda row: "ok"})
        s = term.Screen("t")
        s.json = True
        out = io.StringIO()
        with redirect_stdout(out):
            s.board(b)
        self.assertIn('"gruppo": "Prodotto A"', out.getvalue())
        self.assertIn('"debug": "ok"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
