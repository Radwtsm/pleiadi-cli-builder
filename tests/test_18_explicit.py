"""0.18.2, backlog 8 and 9: explicit commands never leave the screen mute and show the programs' output live (never
less than the program alone, no hidden machine formats); the README has a Setup section with every program."""
import io, os, sys, tempfile, time, unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Screen, Step, run, run_live, run_steps, term
from pleiadi_cli_builder import contract

PY = sys.executable
SLOW = "import time\nfor i in range(3):\n    print('row', i, flush=True)\n    time.sleep(0.4)\n"


class Clocked(io.StringIO):
    def __init__(self):
        super().__init__()
        self.seen = []  # (time, text)

    def write(self, text):
        if text.strip():
            self.seen.append((time.time(), text))
        return super().write(text)


def call(app, argv):
    out, err = Clocked(), Clocked()
    with mock.patch.dict(os.environ, {"NO_COLOR": "1", "PCB_COLORS": ""}), redirect_stdout(out), \
            redirect_stderr(err), mock.patch("sys.stdin", io.StringIO("")):
        code = app.main(argv)
    return code, out, err


class LiveInLines(unittest.TestCase):
    def test_every_line_live_while_the_program_runs(self):
        app, ended = App("t-live", lang="en"), []

        @app.command("build")
        def build(screen, args):
            code, out = run_live(PY, "-c", SLOW, log=os.path.join(tempfile.mkdtemp(), "build.log"))
            ended.append(time.time())
            return code
        code, out, _ = call(app, ["build"])
        self.assertEqual(code, 0)
        rows = [(t, x) for t, x in out.seen if "row" in x]
        self.assertEqual([x.split()[-1] for _, x in rows], ["0", "1", "2"])  # with log= too: all of them
        self.assertLess(rows[0][0], ended[0] - 0.5)  # the first one long before the program ended

    def test_a_silent_program_says_it_is_still_running(self):
        app = App("t-beat", lang="en")
        app.command("wait")(lambda s, a: run_live(PY, "-c", "import time; time.sleep(1.2)")[0])
        with mock.patch.object(term, "HEARTBEAT", 0.4):
            code, out, _ = call(app, ["wait"])
        self.assertEqual(code, 0)
        self.assertIn("still running", out.getvalue())
        self.assertIn("python", out.getvalue().split("still running")[1].splitlines()[0])

    def test_a_wait_without_colors_beats_too(self):
        s = Screen(lang="en")
        s.full, s.colors = False, False
        err = io.StringIO()
        with mock.patch.object(term, "HEARTBEAT", 0.3), redirect_stderr(err):
            with s.wait("copying"):
                time.sleep(1.0)
        self.assertGreaterEqual(err.getvalue().count("… copying"), 2)  # the first line, then at least one beat

    def test_full_screen_keeps_its_window(self):
        s = Screen(lang="en")
        s.full, s.colors, s.opened, s.suspended = True, False, True, True
        for i in range(20):
            s.live(f"line {i}", keep=4)
        self.assertEqual(len(s.body), 4)


def tool(**kw):
    app = App("t-explicit", lang="en", write_commands=[["git", "push"]], **kw)

    @app.command("status", effects=False)
    def status(screen, args):
        return run_live(PY, "-c", "print('M file.txt')", *args)[0]

    @app.command("hidden", effects=False)
    def hidden(screen, args):  # the person typed `hidden`, the tool asks for a format nobody reads
        return run_live(PY, "-c", "print('<xml/>')", "--xml")[0]

    @app.command("typed", effects=False, example=["--porcelain"])
    def typed(screen, args):  # here the person asked for it
        return run_live(PY, "-c", "print('M file.txt')", *args)[0]

    @app.command("push", dry=False)
    def push(screen, args):  # a write command run with its output out of sight
        with mock.patch("subprocess.run") as r:
            r.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            return run("git", "push")[0]

    @app.command("mute", effects=False)
    def mute(screen, args):
        time.sleep(0.6)
        screen.done("done")
        return 0

    @app.command("nameless")
    def nameless(screen, args):
        return 0 if run_steps(screen, [Step("", lambda: True)]) else 1
    return app


class Contract(unittest.TestCase):
    def failures(self, app, **kw):
        case = contract.tests(app, source=__file__ + ".none", **kw)
        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestLoader().loadTestsFromTestCase(case))
        return {t[0]._testMethodName: t[1] for t in r.failures + r.errors}

    def test_the_rules_for_explicit_commands(self):
        bad = self.failures(tool(), silence=0.4)
        self.assertEqual(sorted(bad), ["test_ux_hidden", "test_ux_mute", "test_ux_nameless", "test_ux_push"])
        self.assertIn("machine format", bad["test_ux_hidden"])
        self.assertIn("output hidden", bad["test_ux_push"])
        self.assertIn("mute screen", bad["test_ux_mute"])
        self.assertIn("doesn't say what it does", bad["test_ux_nameless"])

    def test_lines_not_on_screen(self):
        runs = [{"cmd": ["/usr/bin/svn", "update"], "live": True, "lines": ["U  a.c", "Updated to revision 7."]}]
        self.assertEqual(contract.live_problems(runs, [], raw="    U  a.c\n    Updated to revision 7.\n"), [])
        found = contract.live_problems(runs, [], raw="    \033[2mUpdated to revision 7.\033[0m\n")
        self.assertEqual(len(found), 1)
        self.assertIn("`svn update`: 1 lines", found[0])

    def test_machine_formats(self):
        for a in ("--xml", "--json", "--porcelain", "--porcelain=v2", "--format=json", "--output=xml", "-q",
                  "--quiet", "--silent"):
            self.assertTrue(contract.MACHINE.match(a), a)
        for a in ("--verbose", "-m", "--jsonfile", "--format=%H", "-qa"):
            self.assertFalse(contract.MACHINE.match(a), a)


class Setup(unittest.TestCase):
    def folder(self, readme=None):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "tool"))
        if readme is not None:
            with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
                f.write(readme)
        return os.path.join(d, "tool")

    def test_readme_rules(self):
        self.assertIn("no README.md", contract.readme_problems(self.folder())[0])
        self.assertIn("no Setup section", contract.readme_problems(self.folder("# tool\n\nhello\n"))[0])
        text = "# tool\n\n## Setup\n\n- `git`\n- msbuild 17\n\n## Other\n\nsvn is mentioned only here\n"
        self.assertEqual(contract.readme_problems(self.folder(text), ["git", "msbuild"]), [])
        found = contract.readme_problems(self.folder(text), ["git", "svn", "gi"])
        self.assertEqual(len(found), 2)  # svn only outside the section; «gi» is not «git»
        self.assertEqual(contract.readme_problems(self.folder("# t\n## Installazione\n`rm`\n"), ["rm"]), [])

    def test_the_contract_runs_it_on_the_tool(self):
        src = self.folder("# tool\n\nno setup here\n")
        case = contract.tests(tool(), source=src, screens=False)
        r = unittest.TestResult()
        case("test_readme_setup").run(r)
        self.assertEqual(len(r.failures), 1)
        case = contract.tests(tool(), source=self.folder("# tool\n## Setup\n`git`\n"), screens=False)
        r = unittest.TestResult()
        case("test_readme_setup").run(r)
        self.assertEqual(r.failures + r.errors, [])


if __name__ == "__main__":
    unittest.main()
