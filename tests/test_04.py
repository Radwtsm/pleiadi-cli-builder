"""0.4: the general rules as code — each test failed before its fix."""
import datetime, io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, ReadOnlyClient, Screen, Step, run, run_steps, temporary
from pleiadi_cli_builder import credentials, proc, steps, term

FAKE_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # built here so no scanner sees a literal token


def quiet(fn):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        r = fn()
    return r, out.getvalue(), err.getvalue()


class WriteCommands(unittest.TestCase):
    def test_read_only_command_cannot_run_a_write_command(self):
        app = App("t-wc", lang="en", write_commands=[["git", "push"], ["rm"]])
        got = {}

        def look(screen, args):
            got["read"] = run("git", "status")[0]  # not in the list: allowed
            try:
                run("git", "push", "origin")
            except RuntimeError as e:
                got["err"] = str(e)
        app.command("look", effects=False)(look)
        quiet(lambda: app.main(["look"]))
        self.assertIn("git push", got.get("err", ""))
        self.assertIn("read", got)

    def test_dry_run_refuses_write_commands_too(self):
        # the interpreter itself as the write command: `touch` doesn't exist on Windows
        app = App("t-wc2", lang="en", write_commands=[[os.path.basename(sys.executable)]])
        d = tempfile.mkdtemp()
        make = f"open({os.path.join(d, 'x')!r}, 'w').close()"
        app.command("make")(lambda s, a: run(sys.executable, "-c", make))
        r, _, _ = quiet(lambda: app.main(["make", "--dry-run"]))
        self.assertEqual(r, 3)  # refused by the rules, with a clear line
        self.assertFalse(os.path.exists(os.path.join(d, "x")))
        quiet(lambda: app.main(["make"]))
        self.assertTrue(os.path.exists(os.path.join(d, "x")))  # outside dry run and read-only: allowed


class Secrets(unittest.TestCase):
    def setUp(self):
        credentials.KEYCHAIN = credentials.MemoryOnly()
        credentials.keychain().set("t.svc", "me", "s3cr3t-value-xyz")

    def tearDown(self):
        credentials.KEYCHAIN = None
        term.SECRETS.clear()

    def test_secret_never_in_arguments(self):
        tok = credentials.secret("t.svc", "me")
        with self.assertRaises(RuntimeError) as e:
            run("echo", f"--token={tok}")
        self.assertIn("env=", str(e.exception))
        self.assertNotIn(tok, str(e.exception))

    def test_secret_masked_in_output_and_screen(self):
        tok = credentials.secret("t.svc", "me")
        code, out = run(sys.executable, "-c", "import os; print(os.environ['T'])", env={**os.environ, "T": tok})
        self.assertNotIn(tok, out)
        self.assertIn("••••", out)
        _, printed, _ = quiet(lambda: Screen("t").out(f"token is {tok}"))
        self.assertNotIn(tok, printed)


class Access(unittest.TestCase):
    def test_close_always_closes_what_was_open(self):
        log = []
        _, out, err = quiet(lambda: self._use(log))
        self.assertEqual(log, ["close"])
        self.assertIn("VPN", out + err)

    def _use(self, log):
        with temporary(lambda: log.append("open"), lambda: log.append("close"), is_open=lambda: True,
                       close_always=True, screen=Screen("t", lang="en"), label="VPN"):
            pass


class SpinnerOnStderr(unittest.TestCase):
    def test_wait_never_writes_stdout(self):
        s = Screen("t")
        s.colors = True  # line mode with colors: the spinner thread
        _, out, err = quiet(lambda: self._spin(s))
        self.assertEqual(out, "")
        self.assertIn("working", term.ANSI.sub("", err))

    def _spin(self, s):
        import time
        with s.wait("working"):
            time.sleep(0.3)


class Contract(unittest.TestCase):
    def make_app(self, bad=False):
        app = App("t-contract", lang="en", write_commands=[["touch"]])

        def setup(screen, args):
            target = os.path.join(os.path.expanduser("~"), "made")
            if bad and not screen.dry:
                pass
            if bad:
                open(target, "w").close()  # writes even in --dry-run: the contract must catch it
                return 0
            return 0 if run_steps(screen, [Step("dir", lambda: os.path.isdir(target),
                                                apply=lambda: os.makedirs(target) or True)]) else 1
        app.command("setup")(setup)
        app.command("list", effects=False, json=True)(lambda s, a: s.table([{"a": 1}]))
        return app

    def test_good_tool_passes(self):
        from pleiadi_cli_builder import contract
        case = contract.tests(self.make_app(), source=__file__ + ".none")
        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(case))
        self.assertTrue(r.wasSuccessful(), r.failures + r.errors)

    def test_writes_in_dry_run_are_caught(self):
        from pleiadi_cli_builder import contract
        case = contract.tests(self.make_app(bad=True), source=__file__ + ".none")
        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(case))
        self.assertFalse(r.wasSuccessful())

    def test_code_loading_is_caught(self):
        from pleiadi_cli_builder import contract
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "tool.py"), "w") as f:
            f.write("import importlib\nspec = importlib.util.spec_from_file_location('x', 'brand.py')\n")
        self.assertTrue(contract.code_loading(d))
        with open(os.path.join(d, "tool.py"), "w") as f:
            f.write("cfg = app.config('team.json')\n")
        self.assertEqual(contract.code_loading(d), [])

    def test_config_is_json_only(self):
        app = App("t-cfg")
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.json")
        with open(p, "w") as f:
            json.dump({"a": 1}, f)
        self.assertEqual(app.config(p), {"a": 1})
        with open(p, "w") as f:
            f.write("a = __import__('os')")
        with self.assertRaises(ValueError):
            app.config(p)


class SecretScan(unittest.TestCase):
    def test_finds_staged_token(self):
        from pleiadi_cli_builder import scan
        d = tempfile.mkdtemp()
        g = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, encoding="utf-8")
        g("init", "-q")
        with open(os.path.join(d, "a.py"), "w") as f:
            f.write(f'TOKEN = "{FAKE_TOKEN}"\n')
        g("add", "a.py")
        found = scan.staged(d)
        self.assertEqual([x[0] for x in found], ["a.py"])
        with open(os.path.join(d, "b.py"), "w") as f:
            f.write('token = secret("svc", "me")\n')
        g("rm", "-q", "--cached", "a.py")
        g("add", "b.py")
        self.assertEqual(scan.staged(d), [])


class NewTool(unittest.TestCase):
    def test_new_has_contract_tests_and_hook(self):
        d = tempfile.mkdtemp()
        env = {**os.environ, "PYTHONPATH": ROOT}
        r = subprocess.run([sys.executable, "-m", "pleiadi_cli_builder", "new", "team-kit", os.path.join(d, "tk")],
                           env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        tk = os.path.join(d, "tk")
        self.assertTrue(os.access(os.path.join(tk, ".githooks", "pre-commit"), os.X_OK))
        r = subprocess.run([sys.executable, os.path.join(tk, "tests", "test_contract.py")], env=env, cwd=tk,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class BuilderKeepsItsOwnContract(unittest.TestCase):
    def test_builder(self):
        from pleiadi_cli_builder import contract
        from pleiadi_cli_builder.__main__ import app
        case = contract.tests(app)
        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(case))
        self.assertTrue(r.wasSuccessful(), r.failures + r.errors)
        self.assertGreaterEqual(r.testsRun, 4)


class PinWarning(unittest.TestCase):
    def test_pin_step(self):
        from pleiadi_cli_builder.webapi import pin_step
        soon = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
        later = (datetime.date.today() + datetime.timedelta(days=200)).isoformat()
        c = ReadOnlyClient("https://tracker.example", pin_sha256="ab" * 32, pin_expires=soon)
        ok, _, _ = quiet(lambda: run_steps(Screen("t"), [pin_step(c)], check_only=True))
        self.assertFalse(ok)
        c = ReadOnlyClient("https://tracker.example", pin_sha256="ab" * 32, pin_expires=later)
        ok, _, _ = quiet(lambda: run_steps(Screen("t"), [pin_step(c)], check_only=True))
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
