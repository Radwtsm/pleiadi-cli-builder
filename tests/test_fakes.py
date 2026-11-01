"""Backlog 2: fake programs at the front of PATH (fakes.fake_programs), for Mac/Linux (sh) and Windows (.cmd)."""
import os, shutil, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import run
from pleiadi_cli_builder.fakes import WINDOWS, fake_programs

NAMES = {"pcb-fake-git": "git version 2.45.0",
         "pcb-fake-build": ("error MSB1009: project file not found\nBuild FAILED.", 1),
         "pcb-fake-sql": ("it's 100% «ok» $HOME `x`", 0),
         "pcb-fake-quiet": ("", 3)}


class FakePrograms(unittest.TestCase):
    def test_they_answer_always_the_same(self):
        with fake_programs(NAMES) as fake:
            exe = lambda n: fake.path(n) if WINDOWS else n  # Windows: a .cmd is found by its path, not a bare name
            self.assertEqual(run(exe("pcb-fake-git"), "--version"), (0, "git version 2.45.0"))
            self.assertEqual(run(exe("pcb-fake-git"), "anything", "else"), (0, "git version 2.45.0"))
            self.assertEqual(run(exe("pcb-fake-build"), "/m"),
                             (1, "error MSB1009: project file not found\nBuild FAILED."))
            self.assertEqual(run(exe("pcb-fake-sql"), "-Q", "select 1"), (0, "it's 100% «ok» $HOME `x`"))
            self.assertEqual(run(exe("pcb-fake-quiet")), (3, ""))

    def test_first_in_path_then_gone(self):
        before = os.environ.get("PATH")
        with fake_programs({"pcb-fake-git": "fake"}) as fake:
            found = shutil.which("pcb-fake-git")
            self.assertEqual(os.path.normcase(found), os.path.normcase(fake.path("pcb-fake-git")))
            self.assertTrue(os.environ["PATH"].startswith(fake.folder))
            folder = fake.folder
        self.assertEqual(os.environ.get("PATH"), before)
        self.assertFalse(os.path.exists(folder))
        self.assertIsNone(shutil.which("pcb-fake-git"))

    def test_shadows_a_real_program_and_cleans_up_after_an_error(self):
        real = "python3" if not WINDOWS else "python"
        with self.assertRaises(KeyError):
            with fake_programs({real: ("not python", 2)}) as fake:
                r = subprocess.run([shutil.which(real), "--version"], capture_output=True, text=True)
                self.assertEqual((r.returncode, r.stdout.strip()), (2, "not python"))
                folder = fake.folder
                raise KeyError("boom")
        self.assertFalse(os.path.exists(folder))
        self.assertNotIn(folder, os.environ.get("PATH", ""))

    def test_bad_names(self):
        for bad in ("../x", "a/b", ".hidden", ""):
            with self.assertRaises(ValueError):
                with fake_programs({bad: "x"}):
                    pass


if __name__ == "__main__":
    unittest.main()
