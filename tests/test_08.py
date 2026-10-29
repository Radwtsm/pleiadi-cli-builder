"""0.8: sections (an App inside another), names from the host, help that wraps, commands without --prova."""
import io, os, sys, unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Step, run_steps
from pleiadi_cli_builder.contract import tests as contract_tests


def quiet(fn):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        r = fn()
    return r, out.getvalue(), err.getvalue()


def tracker():
    t = App("tracker", lang="en", write_commands=[["touch"]])
    t.command("mine", help="my tasks", menu="My tasks", effects=False)(
        lambda s, a: s.out(f"mine {a} · next: `{t.cmd('setup')}`"))
    t.command("setup", help="configure")(lambda s, a: s.out("dry" if s.dry else "set up"))
    return t


class Sections(unittest.TestCase):
    def setUp(self):
        self.host = App("tool", lang="en")
        self.host.command("hello", help="says hello")(lambda s, a: s.out("hello"))
        self.t = tracker()
        self.host.include(self.t, "task", title="Tasks", rename={"setup": "configure"})

    def test_dispatch_and_names_from_host(self):
        code, out, _ = quiet(lambda: self.host.main(["task", "mine", "x"]))
        self.assertEqual(code, 0)
        self.assertIn("mine ['x']", out)
        self.assertIn("`tool task configure`", out)  # the host's name and the renamed command
        code, out, _ = quiet(lambda: self.host.main(["task", "configure", "--dry-run"]))
        self.assertEqual(out.strip(), "dry")
        self.assertEqual(quiet(lambda: self.host.main(["task", "setup"]))[0], 2)  # renamed away
        self.assertEqual(self.t.cmd("mine"), "tool task mine")

    def test_alone_it_keeps_its_own_name(self):
        t = tracker()
        self.assertEqual(t.cmd("setup"), "tracker setup")

    def test_help_lists_sections(self):
        u = self.host.usage()
        self.assertIn("tool hello", u)
        self.assertIn("tool task mine", u)
        self.assertIn("tool task configure", u)
        self.assertIn("Tasks", u)

    def test_policy_of_the_included_app(self):
        from pleiadi_cli_builder import run
        got = {}

        def look(s, a):
            try:
                run("touch", "/nonexistent/x")
            except RuntimeError as e:
                got["e"] = str(e)
        self.t.command("look", effects=False)(look)
        quiet(lambda: self.host.main(["task", "look"]))
        self.assertIn("touch", got.get("e", ""))

    def test_contract_covers_sections(self):
        case = contract_tests(self.host, source=__file__ + ".none")
        names = [n for n in dir(case) if n.startswith("test_dry_run")]
        self.assertIn("test_dry_run_task_configure", names)


class HelpWraps(unittest.TestCase):
    def test_long_arguments_go_below(self):
        a = App("w", lang="en")
        a.command("task", args="[--project ID] [--state open|closed|all] [--person me|ID] [--due DAYS] [--text WORD]",
                  help="search tasks", effects=False)(lambda s, x: 0)
        a.command("x", help="short one", effects=False)(lambda s, x: 0)
        lines = a.usage().splitlines()
        self.assertTrue(all(len(l) <= 100 for l in lines), lines)
        x = next(l for l in lines if l.strip().startswith("w x"))
        self.assertLess(x.index("short one"), 40)  # the short ones don't get pushed right


class NoDryRun(unittest.TestCase):
    def test_dry_false(self):
        a = App("nd", lang="en")
        got = []
        a.command("forward", help="runs another program", dry=False)(lambda s, args: got.append((s.dry, args)))
        self.assertNotIn("--dry-run", a.usage())
        quiet(lambda: a.main(["forward", "--dry-run"]))
        self.assertEqual(got, [(False, ["--dry-run"])])  # passed through to the other program
        case = contract_tests(a, source=__file__ + ".none")
        self.assertFalse([n for n in dir(case) if n.startswith("test_dry_run")])


if __name__ == "__main__":
    unittest.main()
