"""Backlog 1: contract.tests(app) opens every menu item in a pty at every size (screentest.check_sizes)."""
import os, sys, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Step, run_steps, screentest
from pleiadi_cli_builder.contract import tests as contract_tests


def tool():
    app = App("t-screens", title="T screens", first_run="setup")
    sec = App("t-sub", title="Sub")

    @app.command("setup", menu="Prepara tutto")
    def setup(screen, args):
        screen.header("preparazione")
        return 0 if run_steps(screen, [Step("cartella", lambda: False, apply=lambda: True, plan="creo")]) else 1

    @app.command("broken", menu="Rotto")
    def broken(screen, args):
        sys.stderr.write("Traceback (most recent call last):\n  boom\n")  # what a bad command leaves on screen
        return 0

    @sec.command("list", menu="Elenco", effects=False)
    def listing(screen, args):
        screen.header("elenco")
        screen.table([{"nome": f"voce {i}", "stato": "ok"} for i in range(30)])
        return 0
    app.include(sec, "sub", title="Sezione")
    return app


def run(case, name):
    r = unittest.TestResult()
    case(name).run(r)
    return r


class Generated(unittest.TestCase):
    def test_one_test_per_menu_item_sections_included(self):
        case = contract_tests(tool(), source=__file__ + ".none")
        self.assertEqual(sorted(n for n in dir(case) if n.startswith("test_screen_")),
                         ["test_screen_p", "test_screen_r", "test_screen_s_e"])
        self.assertFalse([n for n in dir(contract_tests(tool(), source=__file__ + ".none", screens=False))
                          if n.startswith("test_screen_")])

    def test_skipped_without_a_pty(self):
        with mock.patch.object(screentest, "available", lambda: False):
            case = contract_tests(tool(), source=__file__ + ".none")
        r = run(case, "test_screen_p")
        self.assertEqual(len(r.skipped), 1)


@unittest.skipUnless(screentest.available(), "no pty")
class InAPty(unittest.TestCase):
    def setUp(self):
        self.case = contract_tests(tool(), source=__file__ + ".none")

    def test_good_items_pass(self):
        for name in ("test_screen_p", "test_screen_s_e"):  # one with --prova, one inside a section
            r = run(self.case, name)
            self.assertEqual(r.failures + r.errors, [], name)

    def test_a_bad_item_fails_with_the_screens(self):
        r = run(self.case, "test_screen_r")
        self.assertEqual(len(r.failures), 1)
        msg = r.failures[0][1]
        self.assertIn("traceback", msg)
        self.assertIn("T screens › Rotto", msg)
        self.assertIn("── 60×20", msg)  # the frames, readable as text


if __name__ == "__main__":
    unittest.main()
