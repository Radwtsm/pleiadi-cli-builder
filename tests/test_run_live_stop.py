"""run_live(on_line=) and a clean Ctrl+C: the program and everything it started stop, and the ✗ line says what may be
left half-done. The real stop is tested on POSIX; the Windows branch only with mocks (not tried on Windows)."""
import io, os, signal, subprocess, sys, threading, time, unittest, unittest.mock
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Interrupted, proc, run_live

# prints, starts a grandchild that ignores Ctrl+C (only SIGTERM stops it), then hangs
HANGS = """
import subprocess, sys, time
g = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); print('grandchild ready', flush=True); time.sleep(60)"])
print("pids", g.pid, flush=True)
print("compiling part 2 of 3", flush=True)
time.sleep(60)
"""


def alive(pid):
    """True while pid runs (a zombie waiting for its parent counts as gone)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[-1].split()[0] != "Z"
    except OSError:
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
        return bool(r.stdout.strip()) and not r.stdout.strip().startswith("Z")


def gone(pids, within=5):
    end = time.time() + within
    while time.time() < end and any(alive(p) for p in pids):
        time.sleep(0.05)
    return not any(alive(p) for p in pids)


class OnLine(unittest.TestCase):
    def test_every_line_in_order_without_colors(self):
        seen = []
        prog = "import sys\nfor i in range(5): print(f'\\x1b[32mrow {i}\\x1b[0m')\nsys.stdout.write('last, no newline')"
        code, out = run_live(sys.executable, "-c", prog, on_line=seen.append)
        self.assertEqual(code, 0)
        self.assertEqual(seen, [f"row {i}" for i in range(5)] + ["last, no newline"])
        self.assertEqual(out.splitlines(), seen)


@unittest.skipIf(os.name == "nt", "POSIX process groups; the Windows branch is in WindowsBranch")
class Stop(unittest.TestCase):
    def setUp(self):
        self.grace, proc.STOP_GRACE = proc.STOP_GRACE, 0.5

    def tearDown(self):
        proc.STOP_GRACE = self.grace

    def run_hanging(self, **kw):
        pids, ready = [], set()

        def on_line(t):
            if t.startswith("pids"):
                pids.append(int(t.split()[1]))
            ready.add(t.split()[0])
            if {"pids", "grandchild", "compiling"} <= ready and not kw.get("timeout"):
                ready.add("sent")
                threading.Timer(0.1, os.kill, (os.getpid(), signal.SIGINT)).start()  # as the terminal's Ctrl+C
        started = []
        real = subprocess.Popen

        def popen(*a, **k):
            started.append(real(*a, **k))
            return started[-1]
        with unittest.mock.patch("subprocess.Popen", popen):
            try:
                r = run_live(sys.executable, "-c", HANGS, on_line=on_line, **kw)
            except Interrupted as e:
                r = e
        return r, [started[0].pid] + pids

    def test_ctrl_c_stops_the_whole_tree_and_says_what(self):
        t0 = time.time()
        e, pids = self.run_hanging()
        self.assertIsInstance(e, Interrupted)
        self.assertIsInstance(e, KeyboardInterrupt)  # who catches Ctrl+C as before still does
        self.assertEqual(len(pids), 2)
        self.assertTrue(gone(pids), "a process of the tree is still running")
        self.assertLess(time.time() - t0, 10)
        self.assertIn(e.last, ("compiling part 2 of 3", "grandchild ready"))  # its last line, whichever came last
        line = e.describe({"interrupted": "stopped `{cmd}` after {time}", "half_done": "last «{last}»",
                           "half_done_quiet": "-"})
        self.assertTrue(line.startswith("stopped `python"), line)
        self.assertIn("last «", line)

    def test_timeout_stops_the_whole_tree_too(self):
        (code, out), pids = self.run_hanging(timeout=1.5)
        self.assertNotEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "timeout")
        self.assertTrue(gone(pids))

    def test_app_shows_the_half_done_line(self):
        app = App("t-stop", lang="en")

        def build(screen, args):
            run_live(sys.executable, "-c", "print('copying 3/10', flush=True)\nimport time; time.sleep(30)",
                     on_line=lambda t: os.kill(os.getpid(), signal.SIGINT))
        app.command("build")(build)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = app.main(["build"])
        self.assertEqual(code, 130)
        last = out.getvalue().rstrip().splitlines()[-1]
        self.assertTrue(last.startswith("✗ interrupted: `python"), last)
        self.assertIn("«copying 3/10»", last)
        self.assertNotIn("Traceback", out.getvalue() + err.getvalue())


class WindowsBranch(unittest.TestCase):
    """Only the calls (not tried on a real Windows): new process group, CTRL_BREAK first, then the tree."""
    def test_group_flags(self):
        with unittest.mock.patch.object(proc, "WIN", True), unittest.mock.patch.object(proc, "_console", lambda: True):
            self.assertEqual(proc._group(), {"creationflags": proc.NEW_GROUP})
        with unittest.mock.patch.object(proc, "WIN", True), unittest.mock.patch.object(proc, "_console", lambda: False), \
                unittest.mock.patch.object(proc, "NO_WINDOW", {"creationflags": 0x08000000}):
            self.assertEqual(proc._group(), {"creationflags": proc.NEW_GROUP | 0x08000000})

    def test_break_then_taskkill(self):
        calls = []

        class P:
            pid, n = 4242, 0

            def poll(self):
                return None if not calls or calls[-1][0] != "taskkill" else 1

            def wait(self, t=None):
                if not calls or calls[-1][0] != "taskkill":
                    raise subprocess.TimeoutExpired("x", t)
                return 1

            def kill(self):
                calls.append(("kill",))
        with unittest.mock.patch.object(proc, "WIN", True), \
                unittest.mock.patch.object(proc.os, "kill", lambda pid, sig: calls.append(("break", pid))), \
                unittest.mock.patch.object(proc.subprocess, "run", lambda a, **k: calls.append(("taskkill", a))):
            proc.stop_tree(P())
        self.assertEqual(calls[0], ("break", 4242))
        self.assertEqual(calls[1], ("taskkill", ["taskkill", "/T", "/F", "/PID", "4242"]))
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
