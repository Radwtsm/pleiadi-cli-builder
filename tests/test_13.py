"""0.13: settings changeable from the tool (never the JSON by hand), «start over»; screens tested in a real pty at
several sizes and resized while open."""
import io, os, sys, tempfile, unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import KEEP, Setting, edit_settings, read_json, term, write_json
from pleiadi_cli_builder import screentest
from pleiadi_cli_builder.settings import reset, set_value

T = term.TEXTS["it"]
SETTINGS = [Setting("url", "Indirizzo", check=lambda v: v.startswith("https://") or "deve iniziare con https://"),
            Setting("keep", "Copia locale", kind="yesno", default=False),
            Setting("role", "Ruolo", kind="choice", choices=[("me", "le mie"), ("pm", "PM")], default="me"),
            Setting("minutes", "Minuti", kind="number", default=10),
            Setting("projects", "Progetti", kind="list"),
            Setting("vpn", "VPN", kind="command")]


class Values(unittest.TestCase):
    def test_show(self):
        s = {x.key: x for x in SETTINGS}
        self.assertEqual(s["url"].show(None, T), "—")
        self.assertEqual(s["keep"].show(None, T), "No (predefinito)")
        self.assertEqual(s["role"].show("pm", T), "PM")
        self.assertEqual(s["projects"].show(["a", "b"], T), "a, b")
        self.assertEqual(s["vpn"].show(["vpn", "up", "my net"], T), "vpn up 'my net'")

    def test_parse(self):
        s = {x.key: x for x in SETTINGS}
        self.assertIs(s["keep"].parse("sì", T), True)
        self.assertIs(s["keep"].parse("no", T), False)
        self.assertEqual(s["role"].parse("PM", T), "pm")
        self.assertEqual(s["minutes"].parse("7,5", T), 7.5)
        self.assertEqual(s["minutes"].parse("3", T), 3)
        self.assertEqual(s["projects"].parse("a, b,,c", T), ["a", "b", "c"])
        self.assertEqual(s["vpn"].parse("vpn up 'my net'", T), ["vpn", "up", "my net"])
        self.assertIsNone(s["url"].parse("-", T))  # back to the default
        for key, bad in (("keep", "forse"), ("role", "capo"), ("minutes", "tanti"), ("minutes", "-3")):
            with self.assertRaises(ValueError):
                s[key].parse(bad, T)

    def test_check_before_saving(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            write_json(path, {"url": "https://a.example", "pin_sha256": "x"})
            self.assertIn("https", set_value(path, SETTINGS[0], "http://b.example"))
            self.assertEqual(read_json(path)["url"], "https://a.example")  # refused: nothing written
            self.assertIsNone(set_value(path, SETTINGS[3], 5))
            self.assertIsNone(set_value(path, SETTINGS[0], None))
            self.assertEqual(read_json(path), {"pin_sha256": "x", "minutes": 5})
            self.assertEqual(reset(path, SETTINGS), ["minutes"])
            self.assertEqual(read_json(path), {"pin_sha256": "x"})  # what the tool doesn't list stays


def run(args, path, json=False, dry=False):
    s = term.Screen("t")
    s.json, s.dry = json, dry
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = edit_settings(s, path, SETTINGS, args)
    return code, buf.getvalue()


class CommandLine(unittest.TestCase):
    def test_list_get_set(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            code, out = run([], path)
            self.assertEqual(code, 0)
            self.assertIn("Copia locale", out)
            self.assertIn("No (predefinito)", out)
            self.assertEqual(run(["keep", "sì"], path)[0], 0)
            self.assertIs(read_json(path)["keep"], True)
            self.assertIn('"keep": true', run([], path, json=True)[1])
            self.assertIn("Sì", run(["keep"], path)[1])
            code, out = run(["minutes", "tanti"], path)
            self.assertEqual(code, 2)
            self.assertIn("serve un numero", out)
            code, out = run(["colore", "blu"], path)
            self.assertEqual(code, 2)
            self.assertIn("Ci sono: url, keep", out)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            code, out = run(["minutes", "3"], path, dry=True)
            self.assertEqual(code, 0)
            self.assertIn("farei", out)
            self.assertFalse(os.path.exists(path))
            write_json(path, {"minutes": 3})
            run(["--reset"], path, dry=True)
            self.assertEqual(read_json(path), {"minutes": 3})


class FakeScreen:
    """The questions answered from a list: choose → index, ask → text, confirm → bool."""
    def __init__(self, answers):
        self.answers, self.t, self.theme = list(answers), T, term.Theme()
        self.full = self.interactive = True
        self.dry = self.json = False
        self.said, self.asked = [], []

    def choose(self, question, options, header=None, keys=None):
        self.asked.append((question, options))
        return self.answers.pop(0)

    def ask(self, question, default=""):
        self.asked.append((question, default))
        a = self.answers.pop(0)
        return a or default

    def confirm(self, question, yes=None, no=None):
        return self.choose(question, [yes, no]) == 0

    def info(self, text):
        self.said.append(term.ANSI.sub("", text))

    c = staticmethod(lambda code, text: text)


class Interactive(unittest.TestCase):
    def test_change_refuse_and_back(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            # Copia locale → Sì; Indirizzo → http (refused); Minuti → Invio (unchanged); Indietro
            s = FakeScreen([1, 0, 0, "http://x", 3, "", len(SETTINGS) + 1])
            self.assertEqual(edit_settings(s, path, SETTINGS), 0)
            self.assertEqual(read_json(path), {"keep": True})
            self.assertIn("(attuale)", s.asked[1][1][1])  # the current value is marked among the choices
            self.assertIn("No (predefinito)", s.asked[0][1][1])  # every setting with its value
            self.assertTrue(any("deve iniziare con https://" in m for m in s.said))

    def test_start_over_runs_the_setup(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            write_json(path, {"keep": True, "ca_file": "x"})
            ran = []
            s = FakeScreen([len(SETTINGS) + 1, 0])  # actions: one → «Rifai da capo» is right after it
            code = edit_settings(s, path, SETTINGS, actions=[("Chiave", lambda sc: "ok")],
                                 on_reset=lambda sc: ran.append(1) or 0)
            self.assertEqual(code, 0)
            self.assertEqual(read_json(path), {"ca_file": "x"})
            self.assertEqual(ran, [1])

    def test_custom_edit(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            st = [Setting("vpn", "VPN", edit=lambda sc, cur: {}, show=lambda v: "non serve" if v == {} else "—"),
                  Setting("x", "X", edit=lambda sc, cur: KEEP)]
            s = FakeScreen([0, 1, 3])
            edit_settings(s, path, st)
            self.assertEqual(read_json(path), {"vpn": {}})


@unittest.skipUnless(screentest.available(), "no pty")
class Sizes(unittest.TestCase):
    SCRIPT = ("import sys; sys.path.insert(0, {root!r})\n"
              "from pleiadi_cli_builder import Screen\n"
              "s = Screen('t'); s.header('prova')\n"
              "s.choose('Cosa scegli?', ['Una voce abbastanza lunga da non stare in sessanta colonne, davvero', 'Due', 'Tre'])\n"
              "s.close()\n")

    def test_frame_checks(self):
        f = screentest.Frame(["x" * 61, "─" * 60, ""], 60, 4)
        p = f.problems()
        self.assertTrue(any("4" in x for x in p))
        self.assertTrue(any("larga 61" in x for x in p))
        self.assertIn("riga dei tasti vuota", p)

    def test_every_size_and_resize(self):
        import sys as _sys
        argv = [_sys.executable, "-c", self.SCRIPT.format(root=ROOT)]
        runs = screentest.check_sizes(argv, [screentest.wait("Cosa scegli?")])
        for name, s in runs.items():
            self.assertEqual(s.problems(expect=["Cosa scegli?", "Tre"]), [], f"{name}\n{s.report()}")
        sizes = {(f.columns, f.rows) for f in runs["resize"].last_frames()}
        self.assertEqual(sizes, {(120, 40), (60, 20)})  # redrawn at the new size each time


if __name__ == "__main__":
    unittest.main()
