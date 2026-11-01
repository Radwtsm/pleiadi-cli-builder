"""The output of a running program scrolls like in Claude Code: ↑↓ PgUp PgDn Home End and the wheel while it runs;
at the bottom it follows, scrolled up it stays and counts the new lines, End follows again; at most `limit` lines.
The logic without a terminal, then one real run in a pty (Mac and Linux)."""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import Screen, screentest, term
from pleiadi_cli_builder.screentest import keys, run_screen, wait
from pleiadi_cli_builder.term import LiveView, mouse_key


def view(n, keep=3, limit=500):
    v = LiveView(keep, limit)
    for i in range(n):
        v.add(f"r{i}")
    return v


class View(unittest.TestCase):
    def test_follows_at_the_bottom(self):
        v = view(20)
        self.assertEqual(v.window(10), ["r17", "r18", "r19"])  # following: only the last `keep`
        v.add("r20")
        self.assertEqual(v.window(10)[-1], "r20")

    def test_scrolled_up_it_stays_and_counts_the_new_lines(self):
        v = view(50)
        v.key("pgup", 10)
        self.assertTrue(v.open)
        self.assertEqual(v.window(10), [f"r{i}" for i in range(31, 41)])  # taller while reading back
        for i in range(50, 170):
            v.add(f"r{i}")
        self.assertEqual(v.window(10), [f"r{i}" for i in range(31, 41)])  # the same lines, not moved
        self.assertEqual(v.new, 120)
        v.key("end", 10)
        self.assertFalse(v.open)
        self.assertEqual((v.offset, v.new), (0, 0))
        self.assertEqual(v.window(10), ["r167", "r168", "r169"])

    def test_keys(self):
        v = view(100)
        v.key("up", 10)
        self.assertEqual(v.window(10)[-1], "r98")
        v.key("wheelup", 10)
        self.assertEqual(v.window(10)[-1], "r95")
        v.key("wheeldown", 10)
        self.assertEqual(v.window(10)[-1], "r98")
        v.key("down", 10)  # at the bottom: following again
        self.assertEqual((v.window(10)[-1], v.open), ("r99", False))
        v.key("up", 10)
        v.key("home", 10)
        self.assertEqual(v.window(10)[0], "r0")
        v.key("pgup", 10)  # already at the top
        self.assertEqual(v.window(10)[0], "r0")
        v.key("pgdn", 10)
        self.assertEqual(v.window(10)[0], "r9")
        for _ in range(20):
            v.key("pgdn", 10)
        self.assertFalse(v.open)  # down to the bottom: following again
        self.assertFalse(v.key("x", 10))

    def test_up_shows_more_even_when_everything_fits(self):
        v = view(6)
        v.key("up", 10)
        self.assertEqual(len(v.window(10)), 6)

    def test_limit(self):
        v = view(1000, limit=500)
        self.assertEqual(len(v.lines), 500)
        self.assertEqual(v.lines[0], "r500")
        v.key("home", 10)
        v.add("new")  # the oldest goes, the view stays at the top
        self.assertEqual(v.window(10)[0], "r501")

    def test_wheel_events(self):
        self.assertEqual(mouse_key(b"\x1b[<64;10;5M"), "wheelup")
        self.assertEqual(mouse_key(b"\x1b[<65;10;5M"), "wheeldown")
        self.assertEqual(mouse_key(b"\x1b[<0;10;5M"), "")  # a click
        self.assertEqual(mouse_key(b"\x1b[M" + bytes([96, 40, 40])), "wheelup")
        self.assertEqual(mouse_key(b"\x1b[<80;1;1M"), "wheelup")  # with Ctrl


class OnScreen(unittest.TestCase):
    def screen(self):
        s = Screen(lang="en")
        s.full, s.colors, s.opened, s.suspended = True, False, True, True  # body only, nothing drawn
        return s

    def test_keys_written_and_the_new_lines_counted(self):
        s = self.screen()
        s.out("⏺ build")
        for i in range(40):
            s.live(f"line {i}", keep=4)
        s.live_scroll(True)
        self.assertIn("PgUp PgDn scroll", s.body[-1])
        self.assertEqual(s.body[-2].split()[-1], "39")
        s.live_key("pgup")
        for i in range(40, 52):
            s.live(f"line {i}", keep=4)
        self.assertIn("↓ 12 new lines", s.body[-1])
        self.assertNotIn("line 51", "\n".join(s.body))
        s.live_key("end")
        self.assertNotIn("new lines", s.body[-1])
        self.assertEqual(s.body[-2].split()[-1], "51")
        s.live_scroll(False)  # the program ended: its last lines, no keys line
        self.assertEqual([b.split()[-1] for b in s.body[1:]], ["48", "49", "50", "51"])

    def test_a_line_said_after_starts_a_new_block(self):
        s = self.screen()
        s.live("a", keep=4)
        s.out("next")
        s.live("b", keep=4)
        self.assertEqual(len(s.body), 3)


SCRIPT = r"""
import sys
from pleiadi_cli_builder import App, phase, run_live
app = App("t-scroll", title="Scroll", lang="it")
PROG = "import time\nfor i in range(300): print('riga', i)\nprint('fine del blocco', flush=True)\ni = 0\nwhile True:\n    i += 1\n    print('tick', i, flush=True)\n    time.sleep(0.15)\n"

@app.command("build")
def build(screen, args):
    screen.header("build")
    with phase(screen, "compila"), screen.wait("compilo"):
        run_live(sys.executable, "-c", PROG, show=6)

sys.exit(app.main(["build"]))
"""


@unittest.skipUnless(screentest.available(), "pty: Mac and Linux")
class Pty(unittest.TestCase):
    def test_scroll_while_it_runs_then_ctrl_c(self):
        s = run_screen([sys.executable, "-c", SCRIPT], [
            wait("fine del blocco"), wait("tick"),
            keys("\x1b[5~"),  # PgUp
            wait("righe nuove"),
            keys("\x1b[<64;10;10M"),  # the wheel, up
            wait("riga 2"),
            keys("\x1b[F"),  # End
            wait("tick"),
            keys("\x03"),  # Ctrl+C
            wait("interrotto"),
        ], 80, 24, env={"PYTHONPATH": ROOT}, timeout=30)
        frames = s.frames()
        scrolled = [f for f in frames if "righe nuove" in f.text()]
        self.assertTrue(scrolled, s.report())
        first = lambda f: int(next(l for l in f.lines if "⎿ riga" in l).split()[-1])
        self.assertLess(first(scrolled[0]), 290)  # back among the earlier lines, and there it stays
        self.assertEqual(first(scrolled[0]) - first(scrolled[-1]), 3)  # the wheel: 3 lines up
        self.assertTrue(any("PgSu PgGiù scorri" in f.text() for f in frames))  # keys written on screen
        after_end = [f for f in frames if "tick" in f.text() and "righe nuove" not in f.text()]
        self.assertTrue(after_end)
        for f in frames:
            self.assertFalse(f.problems(), f.text())
        text = s.text()
        self.assertIn("interrotto: `python", text)
        self.assertNotIn("Traceback", text)
        self.assertEqual(s.code, 130)


if __name__ == "__main__":
    unittest.main()
