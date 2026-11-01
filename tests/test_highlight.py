"""screen.highlight(text, rules) and run_live(rules=): only what a rule catches is colored, the first rule wins, file
names come before words; colored on screen, plain in the log; ready-made rules for svn, git, MSBuild."""
import os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import GIT_RULES, MSBUILD_RULES, SVN_RULES, Screen, role_of, run_live, term

# (rules, a real line, [(colored text, role)]) — None = the default RULES
TABLE = [
    (MSBUILD_RULES, r"src\errorHandler.cpp(12,5): error C2065: 'x': undeclared identifier [C:\proj\app.vcxproj]",
     [("error C2065", "error"), (r"[C:\proj\app.vcxproj]", "dim")]),
    (MSBUILD_RULES, r"  errorHandler.cpp", []),
    (MSBUILD_RULES, r"main.cpp(3,1): warning C4996: 'strcpy': This function or variable may be unsafe. [C:\p\a.vcxproj]",
     [("warning C4996", "warn"), (r"[C:\p\a.vcxproj]", "dim")]),
    (MSBUILD_RULES, r"C:\p\a.vcxproj : error MSB3073: The command exited with code 1.", [("error MSB3073", "error")]),
    (MSBUILD_RULES, "Build FAILED.", [("Build FAILED.", "error")]),
    (MSBUILD_RULES, "    2 Error(s)", [("2 Error(s)", "error")]),
    (MSBUILD_RULES, "    0 Error(s)", []),
    (MSBUILD_RULES, "    5 Warning(s)", [("5 Warning(s)", "warn")]),
    (MSBUILD_RULES, "Build succeeded.", [("Build succeeded.", "ok")]),
    (MSBUILD_RULES, "Time Elapsed 00:00:05.12", [("Time Elapsed 00:00:05.12", "dim")]),
    (SVN_RULES, "C    src/conflict.c", [("C", "error")]),
    (SVN_RULES, "      C src/tree", [("      C", "error")]),
    (SVN_RULES, "A    docs/error.txt", [("A", "ok")]),
    (SVN_RULES, "U    src/main.c", []),
    (SVN_RULES, "D    src/old.c", [("D", "warn")]),
    (SVN_RULES, "?       notes.txt", [("?", "dim")]),
    (SVN_RULES, "svn: E155004: Run 'svn cleanup' to remove locks", [("svn: E155004: Run 'svn cleanup' to remove locks", "error")]),
    (SVN_RULES, "svn: warning: W155010: The node 'x' was not found.", [("svn: warning: W155010: The node 'x' was not found.", "warn")]),
    (SVN_RULES, "Updated to revision 1234.", [("Updated to revision 1234.", "ok")]),
    (SVN_RULES, "Committed revision 77.", [("Committed revision 77.", "ok")]),
    (SVN_RULES, "  Text conflicts: 1", [("  Text conflicts: 1", "error")]),
    (GIT_RULES, "CONFLICT (content): Merge conflict in src/app.py", [("CONFLICT (content): Merge conflict in src/app.py", "error")]),
    (GIT_RULES, "Automatic merge failed; fix conflicts and then commit the result.",
     [("Automatic merge failed; fix conflicts and then commit the result.", "error")]),
    (GIT_RULES, "warning: LF will be replaced by CRLF in src/a.c.", [("warning:", "warn")]),
    (GIT_RULES, "hint: Updates were rejected because the tip of your current branch is behind",
     [("hint: Updates were rejected because the tip of your current branch is behind", "dim")]),
    (GIT_RULES, "error: failed to push some refs to 'origin'", [("error: failed to push some refs to 'origin'", "error")]),
    (GIT_RULES, " ! [rejected]        main -> main (fetch first)", [(" ! [rejected]        main -> main (fetch first)", "error")]),
    (GIT_RULES, "UU src/app.py", [("UU", "error")]),
    (GIT_RULES, "Already up to date.", [("Already up to date.", "ok")]),
    (GIT_RULES, " src/errorHandler.cpp | 4 ++--", []),
    (None, "make: *** [all] Error 2", [("Error", "error")]),
    (None, "see build/error.log for the details", []),
    (None, "src/errorHandler.cpp:12: error: missing ;", [("error", "error")]),
    (None, "3 failed, 10 passed", [("failed", "error"), ("passed", "ok")]),
]

SGR = re.compile(r"\x1b\[([0-9;]+)m(.*?)\x1b\[0m")


def colored(s, text):
    """[(text, role)] of a highlighted line, read back from its color codes."""
    by_code = {getattr(s.theme, r): r for r in ("dim", "ok", "warn", "error")}
    return [(m.group(2), by_code.get(m.group(1), m.group(1))) for m in SGR.finditer(text)]


class Table(unittest.TestCase):
    def test_real_lines(self):
        s = Screen(lang="en")
        s.colors = True
        for rules, line, want in TABLE:
            with self.subTest(line=line):
                got = s.highlight(line, rules)
                self.assertEqual(colored(s, got), want)
                self.assertEqual(term.ANSI.sub("", got), line)  # nothing added, nothing lost

    def test_first_rule_wins(self):
        rules = [(r"error \w+", "error"), (r"\w+ C2065", "warn"), (r"C2065:.*", "ok"), (r"x$", "dim")]
        # the later rules that overlap what the first took color nothing; one elsewhere on the line still does
        self.assertEqual(term.spans("error C2065: x", rules), [(0, 11, "error"), (13, 14, "dim")])

    def test_role_of_shares_the_rules(self):
        self.assertEqual(role_of("C    src/conflict.c", SVN_RULES), "error")
        self.assertEqual(role_of("A    docs/error.txt", SVN_RULES), "ok")
        self.assertEqual(role_of("compiling errorHandler.cpp"), None)
        self.assertEqual(role_of("x", [("x", "warn")]), "warn")  # a regex may be a string

    def test_plain_without_colors(self):
        s = Screen(lang="en")
        s.colors = False
        line = "error C2065: x"
        self.assertEqual(s.highlight("\x1b[31m" + line + "\x1b[0m", MSBUILD_RULES), line)


class Live(unittest.TestCase):
    def test_colored_on_screen_plain_in_the_log(self):
        s = Screen(lang="en")
        s.full, s.colors, s.opened, s.suspended = True, True, True, True  # body only, nothing drawn
        log = os.path.join(tempfile.mkdtemp(), "build.log")
        prog = ("print(r'a.cpp(1): error C2065: x [C:\\p\\a.vcxproj]'); print('compiling errorHandler.cpp');"
                "print('Build FAILED.')")
        term.SCREENS.append(s)
        try:
            code, out = run_live(sys.executable, "-c", prog, log=log, rules=MSBUILD_RULES)
        finally:
            term.SCREENS.remove(s)
        lines = [l for l in s.body if "C2065" in l or "errorHandler" in l]
        self.assertEqual([r for _, r in colored(s, lines[0]) if r != "dim"], ["error"])
        self.assertIn(s.c(s.theme.error, "error C2065"), lines[0])
        self.assertNotIn(s.theme.error + "m", lines[1])  # the file name stays plain
        with open(log, encoding="utf-8") as f:
            self.assertNotIn("\x1b", f.read())
        self.assertEqual(out.splitlines()[:2], [r"a.cpp(1): error C2065: x [C:\p\a.vcxproj]", "Build FAILED."])


if __name__ == "__main__":
    unittest.main()
