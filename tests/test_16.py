"""0.16: times per phase, colors by meaning, live output, the UX contract."""
import io, json, os, sys, tempfile, time, unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Screen, Step, phase, read_json, role_of, run_live, run_steps
from pleiadi_cli_builder import term


def quiet(fn):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        r = fn()
    return r, out.getvalue(), err.getvalue()


class Timings(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.old = os.environ.get("HOME"), os.environ.get("USERPROFILE")
        os.environ["HOME"] = os.environ["USERPROFILE"] = self.home

    def tearDown(self):
        for k, v in zip(("HOME", "USERPROFILE"), self.old):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def app(self):
        app = App("t-time", lang="en", timings=True)

        def build(screen, args):
            with phase(screen, "fetch"):
                time.sleep(0.05)
            return 0 if run_steps(screen, [Step("make", lambda: False, apply=lambda: True)]) else 1
        app.command("build")(build)
        return app

    def test_table_compares_with_the_last_run(self):
        _, first, _ = quiet(lambda: self.app().main(["build"]))
        self.assertIn("Phase", first)
        self.assertIn("fetch", first)
        saved = read_json(os.path.join(self.home, ".config", "t-time", "state.json"))["timings"]["build"]
        self.assertEqual(sorted(saved), ["fetch", "make"])
        _, second, _ = quiet(lambda: self.app().main(["build"]))
        row = next(r for r in second.splitlines() if "fetch" in r)
        self.assertNotIn("—", row)  # the time of the run before is there now

    def test_no_table_without_timings_or_in_json(self):
        app = App("t-time2", lang="en")
        app.command("build")(lambda s, a: run_steps(s, [Step("make", lambda: False, apply=lambda: True)]) and 0)
        _, out, _ = quiet(lambda: app.main(["build"]))
        self.assertNotIn("Phase", out)

    def test_duration_and_change(self):
        self.assertEqual(term.duration(125), "2:05")
        self.assertEqual(term.duration(12.3), "12 s")
        self.assertEqual(term.change(30, 20), "+50%")
        self.assertEqual(term.change(20.4, 20), "")


class Meaning(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(role_of("make: *** [all] Error 2"), "error")
        self.assertEqual(role_of("compiling errorHandler.cpp"), None)  # a file name is not an error
        self.assertEqual(role_of("see build/error.log for the details"), None)
        self.assertEqual(role_of("src/errorHandler.cpp:12: error: missing ;"), "error")
        self.assertEqual(role_of("warning: unused variable"), "warn")
        self.assertEqual(role_of("3 failed, 10 passed"), "error")  # the worst first
        self.assertEqual(role_of("Build done"), "ok")
        self.assertEqual(role_of("\x1b[31mFAILED\x1b[0m"), "error")

    def test_rules_can_be_replaced(self):
        import re
        self.assertEqual(role_of("C  conflict.txt", [(re.compile(r"^C "), "warn")]), "warn")

    def test_output_is_colored_only_on_a_terminal(self):
        s = Screen(lang="en")
        s.colors = True
        self.assertIn("\033[" + s.theme.error, s.paint("fatal: not a repository"))
        self.assertEqual(s.paint("compiling errorHandler.cpp"), "compiling errorHandler.cpp")
        s.colors = False
        self.assertEqual(s.paint("fatal: x"), "fatal: x")


class Live(unittest.TestCase):
    def screen(self):
        s = Screen(lang="en")
        s.full, s.colors, s.opened, s.suspended = True, False, True, True  # body only, nothing drawn
        return s

    def test_only_the_last_lines_stay_while_running(self):
        s = self.screen()
        s.out("step")
        for i in range(25):
            s.live(f"line {i}", keep=4)
        self.assertEqual(s.body[0], "step")
        self.assertEqual([b.split()[-1] for b in s.body[1:]], ["21", "22", "23", "24"])
        s.out("next")  # what comes after is not part of the live block
        s.live("again", keep=4)
        self.assertEqual(len(s.body), 7)

    def test_plain_mode_shows_nothing_live(self):
        s = Screen(lang="en")
        s.full = False
        self.assertFalse(s.live("x"))

    def test_run_live_counts_what_did_not_fit(self):
        from pleiadi_cli_builder import term
        s = self.screen()
        term.SCREENS.append(s)
        try:
            code, out = run_live(sys.executable, "-c", "for i in range(30): print('row', i)", show=5)
        finally:
            term.SCREENS.remove(s)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 30)  # the caller still gets everything
        self.assertIn("25 more lines above", s.body[-1])


class Rules(unittest.TestCase):
    """Every command ends with ✓/✗ and what; phases show like steps; Esc goes back; no tracebacks."""
    def test_outcome_added_when_the_command_says_nothing(self):
        app = App("t-ux", lang="en")
        app.command("ok")(lambda s, a: 0)
        app.command("bad")(lambda s, a: 4)
        app.command("own")(lambda s, a: s.done("3 files copied"))
        self.assertTrue(quiet(lambda: app.main(["ok"]))[1].rstrip().endswith("✓ ok: done"))
        self.assertTrue(quiet(lambda: app.main(["bad"]))[1].rstrip().endswith("✗ bad: failed (exit code 4)"))
        out = quiet(lambda: app.main(["own"]))[1]
        self.assertEqual(out.count("✓"), 1)  # its own outcome, not a second one

    def test_an_error_is_one_line_not_a_traceback(self):
        app = App("t-ux2", lang="en")
        app.command("boom")(lambda s, a: {}["missing"])
        code, out, err = quiet(lambda: app.main(["boom"]))
        self.assertEqual(code, 1)
        self.assertIn("✗ boom: KeyError: 'missing'", out)
        self.assertNotIn("Traceback", out + err)

    def test_phase_is_a_step_with_its_outcome(self):
        s = Screen(lang="en")
        s.full = False
        with redirect_stdout(io.StringIO()) as o:
            with phase(s, "fetch", why="from the server"):
                pass
            with self.assertRaises(ValueError):
                with phase(s, "build"):
                    raise ValueError("x")
        text = o.getvalue()
        self.assertIn("⏺ fetch", text)
        self.assertIn("✓ fetch", text)
        self.assertIn("✗ build", text)
        self.assertNotIn("1/0", text)

    def test_esc_goes_back_in_every_menu(self):
        app = App("t-esc", lang="en")
        app.command("a", menu="First")(lambda s, a: 0)
        s = app.screen()
        seen = {}
        s.choose = lambda q, o, keys=None, start=0, header=None, esc=None: seen.setdefault("esc", esc) == esc and esc
        with redirect_stdout(io.StringIO()):
            app.menu(s)
        self.assertEqual(seen["esc"], 1)  # Esc = the last option, «Quit» or «Back»

    def test_crumbs_of_a_section(self):
        host, sub = App("host", title="Host", lang="en"), App("sub", lang="en")
        host.include(sub, "task", title="Tasks")
        self.assertEqual(sub.crumbs, ["Host", "Tasks"])

    def test_contract_checks_the_outcome(self):
        from pleiadi_cli_builder import contract
        app = App("t-ux3", lang="en")

        def loud(screen, args):
            import traceback
            try:
                {}["x"]
            except KeyError:
                traceback.print_exc()  # a traceback printed by the tool itself
            return 0
        app.command("loud")(loud)
        case = contract.tests(app, source=__file__ + ".none")
        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestLoader().loadTestsFromTestCase(case))
        self.assertEqual([t[0]._testMethodName for t in r.failures], ["test_outcome_loud"])


if __name__ == "__main__":
    unittest.main()
