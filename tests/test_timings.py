"""Backlog 3: every command's duration in a local file (command, seconds, outcome; never arguments or data),
read back with App.timings() — tested with a fake clock."""
import io, json, os, sys, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, PolicyError
from pleiadi_cli_builder import app as app_module


class Clock:
    def __init__(self, *durations):
        self.now, self.durations, self.started = 100.0, list(durations), False

    def __call__(self):  # called once at the start and once at the end of each command
        if self.started:
            self.now += self.durations.pop(0)
        self.started = not self.started
        return self.now


def quiet(fn):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn()


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

    def app(self, **kw):
        app = App("t-dur", lang="en", **kw)
        app.command("build", args="TARGET")(lambda s, a: 0 if a != ["bad"] else 2)
        app.command("crash")(lambda s, a: 1 / 0)

        def stop(s, a):
            raise KeyboardInterrupt
        app.command("stop")(stop)

        def refused(s, a):
            raise PolicyError("no")
        app.command("refused")(refused)
        return app

    def test_each_run_with_duration_and_outcome_no_arguments(self):
        app = self.app(timings=True)
        app.clock = Clock(1.5, 62.25, 0.5, 0.1, 2)
        for argv in (["build", "secret-target"], ["build", "bad"], ["crash"], ["stop"], ["refused"]):
            quiet(lambda: app.main(argv))
        rows = app.timings()
        self.assertEqual([(r["command"], r["seconds"], r["outcome"], r["code"]) for r in rows],
                         [("build", 1.5, "ok", 0), ("build", 62.25, "error", 2), ("crash", 0.5, "error", 1),
                          ("stop", 0.1, "interrupted", 130), ("refused", 2, "refused", 3)])
        self.assertEqual(sorted(rows[0]), ["at", "code", "command", "outcome", "seconds"])
        self.assertEqual([r["seconds"] for r in app.timings("build")], [1.5, 62.25])
        path = os.path.join(self.home, ".config", "t-dur", "timings.jsonl")
        self.assertEqual(app.timings_path(), path)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("secret-target", text)  # never the arguments
        self.assertNotIn("bad", text)

    def test_off_by_default_and_not_in_dry_runs(self):
        app = self.app()
        self.assertFalse(app.timings)
        app.clock = Clock(1, 1)
        quiet(lambda: app.main(["build", "x"]))
        self.assertEqual(app.timings(), [])
        app.timings = True  # the flag is still settable
        self.assertTrue(app.timings)
        quiet(lambda: app.main(["build", "x", "--prova"]))
        self.assertEqual(app.timings(), [])
        quiet(lambda: app.main(["build", "x"]))
        self.assertEqual(len(app.timings()), 1)

    def test_a_broken_line_and_trimming(self):
        app = self.app(timings=True)
        os.makedirs(os.path.dirname(app.timings_path()))
        with open(app.timings_path(), "w", encoding="utf-8") as f:
            f.write('{"command": "build", "seconds": 1, "outcome": "ok", "code": 0, "at": ""}\n{"comm')
        self.assertEqual(len(app.timings()), 1)
        old = app_module.TIMINGS_KEEP
        app_module.TIMINGS_KEEP = 3
        try:
            app.clock = Clock(*[1] * 40)
            for _ in range(20):
                quiet(lambda: app.main(["build", "x"]))
        finally:
            app_module.TIMINGS_KEEP = old
        rows = app.timings()
        self.assertTrue(3 <= len(rows) < 21, len(rows))  # trimmed to the last ones, never emptied
        with open(app.timings_path(), encoding="utf-8") as f:
            self.assertTrue(all(json.loads(line) for line in f))


if __name__ == "__main__":
    unittest.main()
