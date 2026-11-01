"""0.8.2: a question asked while a spinner runs is visible at once; the menu opens after the first setup; safe
glyphs in the classic Windows console."""
import io, os, sys, unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, Theme, term


def pty_run(script, keys, wait_for=None):
    """Runs `script` in a pseudo-terminal; each key is sent only once `wait_for[i]` (bytes) has appeared."""
    import pty, select, time
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(TERM="xterm-256color", COLUMNS="80", LINES="24")
        os.execv(sys.executable, [sys.executable, "-c", script])
    data, end, seen = b"", time.time() + 20, []
    keys, wait_for = list(keys), list(wait_for or [None] * len(keys))
    while time.time() < end:
        if select.select([fd], [], [], 0.2)[0]:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data += chunk
        if keys and (wait_for[0] is None or wait_for[0] in data[len(b"".join(seen)):] or wait_for[0] in data):
            seen.append(data)
            time.sleep(0.3)
            os.write(fd, keys.pop(0))
            wait_for.pop(0)
    _, status = os.waitpid(pid, 0)
    return (os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else status >> 8), data


@unittest.skipIf(os.name == "nt", "no pty")
class QuestionUnderSpinner(unittest.TestCase):
    def test_prompt_visible_before_enter(self):
        script = (f"import sys; sys.path.insert(0, {ROOT!r})\n"
                  "from pleiadi_cli_builder import Screen, Step, run_steps\n"
                  "s = Screen('t')\n"
                  "s.header('x')\n"
                  "answers = []\n"
                  "def apply():\n"
                  "    answers.append(s.ask('Percorso della cartella:'))\n"
                  "    answers.append(s.ask('Secondo valore:'))\n"
                  "    return True\n"
                  "run_steps(s, [Step('cartella', lambda: False, apply=apply, wait='preparo')])\n"
                  "s.close(); print('RISPOSTE', answers)\n")
        code, data = pty_run(script, [b"abc", b"\r", b"xyz", b"\r"],
                             [b"Percorso della cartella", None, b"Secondo valore", None])
        self.assertEqual(code, 0, data[-300:])
        # what was typed is drawn in the bottom line before Enter (it was hidden under the spinner line)
        before_enter = data.split(b"Secondo valore")[0]
        self.assertIn(b"abc", before_enter)
        self.assertIn(b"RISPOSTE ['abc', 'xyz']", data)


class MenuAfterSetup(unittest.TestCase):
    def test_first_run_then_menu(self):
        app = App("t-first", lang="en", first_run="setup")
        import tempfile
        app.state_path = os.path.join(tempfile.mkdtemp(), "state.json")
        done = []
        app.command("setup", menu="Setup")(lambda s, a: done.append("setup"))
        with mock.patch.object(App, "menu", lambda self, screen: done.append("menu") or 0), \
             mock.patch("sys.stdin.isatty", lambda: True), \
             mock.patch("pleiadi_cli_builder.term.Screen.ask", lambda self, q, d="": ""):  # «Enter for the menu»
            buf = io.StringIO()
            with redirect_stdout(buf):
                app.main([])
        self.assertEqual(done, ["setup", "menu"])


class SafeGlyphs(unittest.TestCase):
    FANCY = "✦✧⋆⏺⎿❯╭╮╰╯"

    def test_classic_windows_console(self):
        with mock.patch.object(term, "WIN", True), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WT_SESSION", None)
            os.environ.pop("PCB_GLYPHS", None)
            th = Theme()
        used = th.mark + th.step + th.attach + th.prompt + th.spinner + "".join(th.corners)
        self.assertFalse(set(used) & set(self.FANCY), used)

    def test_windows_terminal_and_mac_keep_them(self):
        with mock.patch.object(term, "WIN", True), mock.patch.dict(os.environ, {"WT_SESSION": "x"}):
            self.assertEqual(Theme().mark, "✦")
        with mock.patch.object(term, "WIN", False):
            self.assertEqual(Theme().corners[0], "╭")

    def test_forced(self):
        with mock.patch.dict(os.environ, {"PCB_GLYPHS": "safe"}):
            self.assertNotEqual(Theme().mark, "✦")

    def test_box_uses_theme_corners(self):
        s = term.Screen("t", theme=Theme(glyphs="safe"))
        self.assertTrue(s.frame(["x"])[0].startswith("┌"))


if __name__ == "__main__":
    unittest.main()
