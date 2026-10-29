import io, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pleiadi_cli_builder import App, Scene, Screen, Step, Theme, bundle, clip, run_steps, self_update
from pleiadi_cli_builder.intro import SHAPES, Renderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plain(fn):
    """Runs fn with stdout captured (so the Screen sees no terminal and prints plain lines)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = fn()
    return r, buf.getvalue()


class Term(unittest.TestCase):
    def test_clip_ignores_colors(self):
        s = "\033[31m" + "x" * 50 + "\033[0m"
        out = clip(s, 10)
        self.assertEqual(len(out.replace("\033[31m", "").replace("\033[0m", "")), 10)
        self.assertTrue(out.endswith("\x1b[0m"))

    def test_rgb(self):
        self.assertEqual(Theme.rgb("#e8253f"), "38;2;232;37;63")


class Steps(unittest.TestCase):
    def test_skip_apply_fail(self):
        done = []
        steps = [Step("già", lambda: True), Step("fa", lambda: bool(done), apply=lambda: done.append(1) or (True, "ok")),
                 Step("a mano", lambda: False, fix="premi «Collega»")]
        ok, out = plain(lambda: run_steps(Screen("t", lang="it"), steps))
        self.assertFalse(ok)
        self.assertIn("✓ già", out)
        self.assertIn("✓ fa · ok", out)
        self.assertIn("✗ a mano", out)
        self.assertIn("premi «Collega»", out)
        self.assertIn("2/3 a posto", out)
        ok, out = plain(lambda: run_steps(Screen("t"), steps[:2], check_only=True))  # rerun: all skipped
        self.assertTrue(ok)

    def test_broken_check_is_a_failure(self):
        ok, out = plain(lambda: run_steps(Screen("t"), [Step("rotto", lambda: 1 / 0)], check_only=True))
        self.assertFalse(ok)
        self.assertIn("division by zero", out)


class Apps(unittest.TestCase):
    def setUp(self):
        self.app = App("x-test", lang="en")
        self.app.state_path = os.path.join(tempfile.mkdtemp(), "state.json")
        self.app.command("hi", help="says hi")(lambda s, a: s.out("hi " + " ".join(a)))

    def test_dispatch_help_unknown(self):
        self.assertEqual(plain(lambda: self.app.main(["hi", "there"])), (0, "hi there\n"))
        self.assertIn("x-test hi", plain(lambda: self.app.main(["help"]))[1])
        self.assertEqual(plain(lambda: self.app.main(["nope"]))[0], 2)

    def test_state(self):
        self.app.save_state(a=1)
        self.app.save_state(b=2)
        self.assertEqual(self.app.state(), {"a": 1, "b": 2})


class Intro(unittest.TestCase):
    def test_every_shape_renders(self):
        for quarter in (True, False):
            for true in (True, False):
                for i, a in enumerate(SHAPES):
                    sc = Scene("ciao àbc", "frase", ["riga"], colors="blue", shapes=(a, SHAPES[(i + 1) % len(SHAPES)]))
                    rd = Renderer(sc, 60, 20, quarter=quarter, true_color=true)
                    for t, spin in ((0.1, 0), (0.6, 0), (1.0, 0), (1.0, 6.0)):
                        out = rd.cells(rd.frame(t, spin), t)
                    self.assertIn("frase", out)
                    self.assertEqual(sc.title, "CIAO ABC")

    def test_bad_input_falls_back(self):
        sc = Scene("", colors=("#zzz", "x", "y"), shapes=("nope",), stars=[])
        self.assertEqual((sc.title, sc.shapes), ("HELLO", ["star", "sphere"]))
        Renderer(sc, 40, 14).cells(Renderer(sc, 40, 14).frame(1.0), 1.0)


class Ship(unittest.TestCase):
    def test_new_bundle_run_update(self):
        d = tempfile.mkdtemp()
        env = {**os.environ, "PYTHONPATH": ROOT}
        r = subprocess.run([sys.executable, "-m", "pleiadi_cli_builder", "new", "deploy-kit", os.path.join(d, "dk")],
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = os.path.join(d, "dist", "deploy-kit.pyz")
        os.makedirs(os.path.dirname(out))
        digest = bundle(os.path.join(d, "dk"), "deploy_kit.__main__:main", out)
        clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}  # the .pyz must carry the library
        r = subprocess.run([sys.executable, out, "doctor"], capture_output=True, text=True, cwd=d, env=clean)
        self.assertIn("git", r.stdout, r.stderr)
        self.assertIn("a posto", r.stdout)
        dest = os.path.join(d, "installed", "deploy-kit.pyz")
        url = "file://" + out
        self.assertEqual(self_update(url, dest, sha256_url=url + ".sha256"), (True, "updated"))
        self.assertEqual(self_update(url, dest), (True, "up to date"))
        with open(out + ".sha256", "w") as f:
            f.write("0" * 64)
        self.assertFalse(self_update(url, dest + "2", sha256_url=url + ".sha256")[0])
        self.assertEqual(len(digest), 64)

    def test_full_screen_in_a_pty(self):
        if os.name == "nt":
            self.skipTest("no pty")
        import pty, select
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update(PYTHONPATH=ROOT, TERM="xterm-256color", COLUMNS="100", LINES="30")
            os.execv(sys.executable, [sys.executable, "-m", "pleiadi_cli_builder", "demo"])
        data = b""
        while True:
            try:
                if not select.select([fd], [], [], 15)[0]:
                    break
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data += chunk
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, data[-500:])
        self.assertIn(b"\x1b[?1049h", data)  # it really opened the full screen…
        self.assertIn("2/3 a posto".encode(), data)  # …and left the summary on the normal one


if __name__ == "__main__":
    unittest.main()
