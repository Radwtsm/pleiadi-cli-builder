"""0.14: in a menu or a screen that loops the next question replaces the previous one (crumbs, the last outcome on
top, the cursor back where you went in); an action of a full view may ask and wait; in a low window the question and
the selected row stay on screen."""
import io, os, sys, tempfile, unittest, unittest.mock
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, screentest, term
from pleiadi_cli_builder.screentest import keys, pause, run_screen, wait

HEAD = f"import sys, time; sys.path.insert(0, {ROOT!r})\n"


class Logic(unittest.TestCase):
    """What can be proved without a terminal (it also runs on Windows)."""
    def test_visible_keeps_question_and_selection(self):
        s = term.Screen("t")
        s.body = [f"l{i}" for i in range(20)]
        self.assertEqual(s.visible(3), ["l17", "l18", "l19"])  # no question: the last lines, as always
        s.focus = (2, 4)
        self.assertEqual(s.visible(5), ["l2", "l3", "l4", "l5", "l6"])  # it fits from the question
        s.focus = (2, 15)
        self.assertEqual(s.visible(5), ["l2", "l12", "l13", "l14", "l15"])  # scrolled: the question stays on top

    def test_fresh_without_a_terminal_only_says_the_note(self):
        s = term.Screen("t")
        buf = io.StringIO()
        with redirect_stdout(buf):
            s.fresh(["Impostazioni", "Stile"], "fatto")
        self.assertIn("fatto", buf.getvalue())
        self.assertNotIn("Stile", buf.getvalue())

    def test_action_message_and_failure(self):
        s = term.Screen("t")
        self.assertEqual(s.action(lambda: "ok", "copia"), "ok")
        self.assertEqual(s.action(lambda: None, "copia"), "copia")
        self.assertIn("division", s.action(lambda: 1 / 0, "copia"))
        self.assertFalse(s.over)

    def test_menu_comes_back_on_the_item(self):
        app = App("t")
        for name, label in (("a", "Prima"), ("b", "Seconda"), ("c", "Terza")):
            app.command(name, menu=label)(lambda s, a: 0)
        starts, answers = [], iter([2, 3])
        s = app.screen()
        s.choose = lambda q, o, keys=None, start=0, header=None: starts.append(start) or next(answers)
        s.ask = lambda *a: ""
        with unittest.mock.patch("sys.stdin.isatty", lambda: True), redirect_stdout(io.StringIO()):
            app.menu(s)
        self.assertEqual(starts, [0, 2])


SETTINGS = HEAD + """
from pleiadi_cli_builder import App, Setting, edit_settings
S = [Setting("stile", "Stile", kind="choice", choices=[("a", "Sobrio"), ("b", "Vivo")], default="a"),
     Setting("intro", "Intro", kind="yesno", default=True), Setting("nome", "Nome")]
app = App("t", title="Prova")
@app.command("impostazioni", menu="Impostazioni", key="i")
def imp(s, a):
    s.header("impostazioni")
    return edit_settings(s, %r, S, a)
@app.command("altro", menu="Altro", key="a")
def altro(s, a):
    return 0
app.run()
"""


@unittest.skipUnless(screentest.available(), "no pty")
class Replace(unittest.TestCase):
    def run_settings(self, steps):
        d = tempfile.mkdtemp()
        env = {"HOME": d, "USERPROFILE": d, "PCB_GLYPHS": "full"}
        return run_screen([sys.executable, "-c", SETTINGS % os.path.join(d, "c.json")], steps, 80, 24, env=env), d

    def test_loop_does_not_pile_up(self):
        s, d = self.run_settings([wait("Cosa vuoi fare"), keys("i"), wait("Cosa vuoi cambiare"), keys("enter"),
                                  wait("Stile"), keys("down"), keys("enter"), wait("Stile = Vivo"), pause(0.3)])
        f = s.frames(80)[-1].text()
        self.assertEqual(f.count("Cosa vuoi cambiare?"), 1, f)  # one list, not one under the other
        self.assertNotIn("Cosa vuoi fare", f)
        self.assertIn("Impostazioni", f)
        self.assertIn("✓ Stile = Vivo", f)  # the outcome stays above the list
        self.assertLess(f.index("Stile = Vivo"), f.index("Cosa vuoi cambiare?"))
        self.assertIn("❯ 1. Stile", f)  # the cursor on the item it came from
        self.assertEqual(s.problems(), [])

    def test_crumbs_inside_a_setting(self):
        s, d = self.run_settings([wait("Cosa vuoi fare"), keys("i"), wait("Cosa vuoi cambiare"), keys("down"),
                                  keys("enter"), wait("Intro"), pause(0.3)])
        f = s.frames(80)[-1].text()
        self.assertIn("Impostazioni › Intro", f)
        self.assertNotIn("Cosa vuoi cambiare?", f)
        self.assertIn("❯ 1. Sì", f)  # the current value (default: yes) is where the cursor starts

    def test_back_to_the_menu_without_a_pause(self):
        s, d = self.run_settings([wait("Cosa vuoi fare"), keys("i"), wait("Cosa vuoi cambiare"), keys("up"),
                                  keys("enter"), wait("Cosa vuoi fare"), pause(0.3)])
        f = s.frames(80)[-1].text()
        self.assertEqual(f.count("Cosa vuoi fare"), 1, f)
        self.assertIn("❯ 1. Impostazioni", f)  # back on the item it went in from


BOARD = HEAD + """
from pleiadi_cli_builder import Board, Screen
def fill(row):
    time.sleep(0.9)
    return "ok"
def update(s, rows):
    if not s.confirm(f"Aggiorno {len(rows)} copie?", "Sì, aggiorna", "No"):
        return "annullato"
    with s.wait("aggiorno") as w:
        time.sleep(0.6)
    return "aggiornate"
rows = [{"nome": f"copia {i}", "svn": ""} for i in range(8)]
b = Board("Copie", ["nome", "svn"], [("Gruppo", rows)], fill={"svn": fill}, actions={"u": ("aggiorna", update)})
s = Screen("t")
s.header("prova")
print(s.board(b), file=sys.stderr)
s.close()
"""


@unittest.skipUnless(screentest.available(), "no pty")
class BoardActions(unittest.TestCase):
    def test_confirm_and_wait_while_cells_fill(self):
        s = run_screen([sys.executable, "-c", BOARD], [wait("Copie"), keys("u"), wait("Aggiorno"), pause(1.2)],
                       100, 30, env={"PCB_GLYPHS": "full"})
        f = s.frames(100)[-1].text()
        self.assertIn("Aggiorno", f)  # the cells went on filling: the question is still there
        self.assertIn("Sì, aggiorna", f)
        self.assertEqual(s.problems(), [])

    def test_answer_then_the_table_comes_back(self):
        s = run_screen([sys.executable, "-c", BOARD], [wait("Copie"), keys("u"), wait("Aggiorno"), keys("enter"),
                                                       wait("aggiornate"), pause(0.5)],
                       100, 30, env={"PCB_GLYPHS": "full"})
        self.assertIn("aggiorno", s.text())  # the wait line was on screen
        f = s.frames(100)[-1].text()
        self.assertIn("copia 0", f)
        self.assertIn("aggiornate", f)
        self.assertNotIn("Traceback", s.text())


LOW = HEAD + """
from pleiadi_cli_builder import Screen
s = Screen("t")
s.header("prova")
s.choose("Quale scegli?", [f"voce {i}" for i in range(20)])
s.close()
"""


@unittest.skipUnless(screentest.available(), "no pty")
class LowWindow(unittest.TestCase):
    def test_question_and_selection_stay(self):
        s = run_screen([sys.executable, "-c", LOW], [wait("voce"), keys(*["down"] * 15), pause(0.4)], 60, 14,
                       env={"PCB_GLYPHS": "full"})
        f = s.frames(60)[-1].text()
        self.assertIn("Quale scegli?", f)
        self.assertIn("voce 15", f)
        self.assertEqual(s.problems(), [])


if __name__ == "__main__":
    unittest.main()
