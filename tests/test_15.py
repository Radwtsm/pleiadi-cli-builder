"""0.15: the line you type on, the keys and the wait line stay right under the content, like Claude Code; the fixed box
on top has a logo beside the information, chosen by the App; no logo in a narrow or low window."""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import App, screentest, term
from pleiadi_cli_builder.screentest import keys, pause, run_screen, size, wait

plain = lambda ls: [term.ANSI.sub("", l).rstrip() for l in ls]


def screen(body=("  una riga",)):
    s = term.Screen("t", "Prova")
    s.head, s.rows, s.body = ["box"], ["Prova", "  1.0"], list(body)
    return s


class Layout(unittest.TestCase):
    """Without a terminal: it also runs on Windows."""
    def test_bottom_line_follows_the_content(self):
        s = screen()
        s.logo = ()
        s.foot = "> scrivo"
        self.assertEqual(plain(s.layout(80, 40)), ["box", "  una riga", "─" * 80, "> scrivo"])

    def test_goes_down_only_when_the_content_fills_the_window(self):
        s = screen([f"riga {i}" for i in range(50)])
        s.logo = ()
        got = plain(s.layout(80, 12))
        self.assertEqual(len(got), 12)
        self.assertEqual(got[-3], "riga 49")
        self.assertEqual(got[-2], "─" * 80)

    def test_logo_beside_the_information(self):
        got = plain(screen().layout(80, 24))
        self.assertTrue(any("▄█▄" in r and "Prova" in r for r in got), got)
        self.assertTrue(any("▀███▀" in r and "1.0" in r for r in got), got)

    def test_no_logo_when_narrow_or_low(self):
        for w, h in ((59, 24), (80, 19)):
            self.assertFalse(any("█" in r for r in plain(screen().layout(w, h))), (w, h))

    def test_app_chooses_logo_and_information(self):
        app = App("t", title="Prova", banner=("##", "##"), banner_info=lambda: ["versione 2", "C:/lavoro"])
        s = app.screen()
        s.full = False
        s.colors = False
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as buf:
            s.header("menu")
        self.assertIn("versione 2", buf.getvalue())
        s.head = ["box"]
        self.assertTrue(any("##" in r and "C:/lavoro" not in r for r in plain(s.banner(80, 24))))
        self.assertTrue(any("C:/lavoro" in r for r in plain(s.banner(80, 24))))
        self.assertEqual(App("t", banner=()).screen().logo, ())

    def test_information_that_fails_does_not_stop_the_tool(self):
        s = App("t", banner_info=lambda: 1 / 0).screen()
        s.full, s.colors = False, False
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            s.header()


TYPED = f"""import sys; sys.path.insert(0, {ROOT!r})
from pleiadi_cli_builder import Screen
s = Screen("t", "Prova")
s.header("prova")
s.ask("Come ti chiami?")
s.close()
"""


@unittest.skipUnless(screentest.available(), "no pty")
class Real(unittest.TestCase):
    def test_typing_right_under_the_question(self):
        s = run_screen([sys.executable, "-c", TYPED], [wait("Come ti chiami"), keys("abc"), pause(0.3)], 100, 40,
                       env={"PCB_GLYPHS": "full"})
        f = s.frames(100)[-1]
        at = next(i for i, l in enumerate(f.lines) if "Come ti chiami" in l)
        self.assertEqual(f.lines[at + 1].strip(" "), "─" * 100)  # no empty space to cross with the eyes
        self.assertIn("abc", f.lines[at + 2])
        self.assertEqual(s.problems(), [])

    def test_resized_the_box_follows(self):
        s = run_screen([sys.executable, "-c", TYPED], [wait("Come ti chiami"), size(50, 30), size(100, 30), pause(0.3)],
                       100, 30, env={"PCB_GLYPHS": "full"})
        big, small, back = s.last_frames()
        self.assertIn("▀███▀", big.text())
        self.assertNotIn("▀███▀", small.text())
        self.assertIn("▀███▀", back.text())
        self.assertEqual(s.problems(), [])


if __name__ == "__main__":
    unittest.main()
