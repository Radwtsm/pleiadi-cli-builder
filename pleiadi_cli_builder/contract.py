"""Contract tests every tool gets for free (`new` puts them in tests/): the general rules checked by code.

    from pleiadi_cli_builder.contract import tests
    from my_tool.__main__ import app
    Contract = tests(app)          # a unittest.TestCase

- every command with effects, run with --prova in an empty HOME and working folder, creates nothing, applies no
  step and runs no declared write command;
- every command with json=True prints valid JSON on stdout with --json;
- every command, run with colors on and nobody at the keyboard (empty stdin, empty HOME; with --prova when it has
  effects), raises nothing and shows no traceback, closes every step it shows (⏺) with its ✓/✗, ends with an outcome
  (✓ green or ✗ red and what; App.call adds one when the command doesn't say it, the summary box counts too) and
  exits coherently: 0 ⇔ the outcome is not ✗ (ux_problems);
- every command run as an explicit command (in lines, as above) never leaves the screen mute: no silence longer
  than `silence` seconds (term.HEARTBEAT: run_live and screen.wait say «still running» by themselves); every line
  of every program it runs with run_live is on screen, live (never less than the program run alone); no program
  shown live gets a machine format the person didn't type (--xml, --json, --porcelain, --format=json, --quiet…)
  and no declared write command runs with its output hidden (run instead of run_live); every step says what it
  does (⏺ and a text) and how it went (✓/✗);
- the tool has a README.md (in its package folder or the one above) with a Setup section (a heading with «setup»
  or «install»/«installa») that names every program it declares (write_commands): a task that adds a tool, a
  dependency or a manual step updates the setup in the same task (and tries it on a clean machine when it can);
- every menu item, opened from the menu in a real terminal (pty, screentest.check_sizes: 60×20, 80×24, 120×40 and
  resized while open) with an empty HOME (a fake configuration: first run done, nothing else) and --prova when it
  has effects, keeps every frame inside the window with its separator and key line and shows no traceback
  (Session.problems); skipped where there is no pty (Windows);
- the tool's code never loads code at run time (exec, eval, importlib, runpy, __import__): configuration is
  read as JSON (App.config)."""
import io, json, os, re, shutil, sys, tempfile, time, unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from . import proc, screentest, steps, term
from .app import HELP, App
from .term import ANSI

CALLS, MODULES = {"exec", "eval", "__import__"}, {"importlib", "runpy"}
# arguments that turn a program's output into a format for machines (or into nothing)
MACHINE = re.compile(r"^(--(xml|json|porcelain)(=.*)?|--(format|output|out|reporter)=(json|xml|yaml|csv)|"
                     r"--(quiet|silent)|-q)$", re.I)
SETUP = re.compile(r"^#{1,6}\s.*\b(setup|install\w*)\b", re.I | re.M)


def readme_problems(source, programs=()):
    """What breaks the setup rule for the tool whose package is `source`: the README.md in it or in the folder
    above, a Setup section in it, every one of `programs` named there (as `name` or plain)."""
    folders = [source, os.path.dirname(os.path.abspath(source))] if os.path.isdir(source) else \
        [os.path.dirname(os.path.abspath(source))]
    path = next((os.path.join(f, "README.md") for f in folders if os.path.isfile(os.path.join(f, "README.md"))), None)
    if not path:
        return ["no README.md beside the tool: say how to set it up (a Setup section)"]
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = SETUP.search(text)
    if not m:
        return [f"{path}: no Setup section (a heading with «Setup» or «Install»): what to install and do first"]
    nxt = re.search(r"^#{1,%d}\s" % len(m.group(0).split()[0]), text[m.end():], re.M)
    section = text[m.start():m.end() + (nxt.start() if nxt else len(text))]
    return [f"{path}: the Setup section doesn't name `{p}` (a program the tool runs)"
            for p in sorted(set(programs)) if not re.search(r"(?<![\w-])" + re.escape(p) + r"(?![\w-])", section)]


def live_problems(runs, typed, write_commands=(), raw=""):
    """What breaks the rules for explicit commands in the programs a command ran (proc.RUNS) and what it printed
    (`raw`, both streams): lines of a live program not on screen, machine formats the person didn't type, write
    commands run with their output hidden."""
    seen = set(ANSI.sub("", raw).split("\n"))
    seen = {r.strip() for r in seen}
    found = []
    for r in runs:
        name = " ".join([os.path.basename(r["cmd"][0])] + r["cmd"][1:]) if r["cmd"] else "?"
        name = name if len(name) <= 60 else name[:59] + "…"
        if r["live"]:
            missing = [t for t in r["lines"] if t.strip() and t.strip() not in seen]
            if missing:
                found.append(f"`{name}`: {len(missing)} lines of its output not on screen (first: {missing[0][:60]!r})")
            hidden = [a for a in r["cmd"][1:] if MACHINE.match(a) and a not in typed]
            if hidden:
                found.append(f"`{name}` shown with {' '.join(hidden)}: a machine format the person didn't ask for")
        else:
            names = [os.path.basename(r["cmd"][0])] + r["cmd"][1:] if r["cmd"] else []
            if any(names[:len(w)] == list(w) for w in write_commands):
                found.append(f"`{name}` writes with its output hidden (run): run_live shows it live")
    return found


class _Clocked(io.StringIO):
    """A stream that keeps when each write arrived (the silences of a command)."""
    def __init__(self, times):
        super().__init__()
        self.times = times

    def write(self, text):
        if text:
            self.times.append(time.time())
        return super().write(text)


def code_loading(source):
    """[(file, line number, line)] where the code under `source` (a folder or a file) loads code at run time: calls
    to exec/eval/__import__ and any use of importlib/runpy (read as Python tokens: words in strings and comments
    don't count). A line ending with `# contract: ok` is accepted (say why in the comment before it)."""
    import tokenize
    files = [source] if os.path.isfile(source) else [
        os.path.join(d, f) for d, _, fs in os.walk(source)
        if not any(p in d for p in ("__pycache__", os.sep + ".", "tests")) for f in fs if f.endswith(".py")]
    base = source if os.path.isdir(source) else os.path.dirname(source)
    found = []
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        with open(path, "rb") as f:
            try:
                toks = [t for t in tokenize.tokenize(f.readline) if t.type not in (tokenize.NL, tokenize.NEWLINE)]
            except (tokenize.TokenError, SyntaxError):
                continue
        for i, t in enumerate(toks):
            hit = (t.type == tokenize.NAME and (t.string in MODULES or t.string in CALLS and i + 1 < len(toks)
                                                and toks[i + 1].string == "("))
            if hit:
                line = lines[t.start[0] - 1]
                if not line.rstrip().endswith("# contract: ok") and (rel := (os.path.relpath(path, base), t.start[0],
                                                                              line.strip())) not in found:
                    found.append(rel)
    return found


def ux_problems(raw, code, theme):
    """What breaks the UX rules in the output `raw` (with its colors) of a command that exited with `code`."""
    lines = [r for r in raw.splitlines() if r.strip()]
    plain = [ANSI.sub("", r).strip() for r in lines]
    found, open_step = [], None
    for r, raw in zip(plain, lines):
        if "Traceback (most recent call last)" in r:
            found.append("a Python traceback")
        if re.fullmatch(re.escape(theme.step) + r"\s*(\d+/\d+)?(\s*·.*)?", r):  # only its count and why
            found.append("a step that doesn't say what it does (⏺ without a text)")
            r = theme.step + " ?"
        if r.startswith(theme.step + " "):
            if open_step:
                found.append(f"step without its ✓/✗: {open_step}")
            open_step = r
        # a step's result is indented under it; the command's outcome starts the line
        elif open_step and ANSI.sub("", raw)[:1] == " " and r.lstrip(theme.attach + " ").startswith((theme.yes, theme.no, "○")):
            open_step = None
    if open_step:
        found.append(f"step without its ✓/✗: {open_step}")
    if not plain:
        return found + ["no output at all"]
    corners = theme.corners
    if plain[-1].startswith(corners[2]):  # the summary box: a ✗ row inside it = something failed
        top = max(i for i, r in enumerate(plain) if r.startswith(corners[0]))
        head = plain[top + 1].strip(" │|")
        failed = any(r.strip(" │|").startswith(theme.no + " ") for r in plain[top + 1:-1])
        last_raw = None
    else:
        head, last_raw = plain[-1], lines[-1]
        if not head.startswith((theme.yes, theme.no)):
            return found + [f"no outcome at the end (✓/✗ and what): {head!r}"]
        failed = head.startswith(theme.no)
        color = theme.error if failed else theme.ok
        if f"\033[{color}m" not in last_raw:
            found.append(f"outcome without its color ({'red' if failed else 'green'}): {head!r}")
    if failed and code == 0 or (not failed and code != 0):
        found.append(f"exit code {code} but the outcome says {head!r}")
    return found


def _tree(root):
    return sorted(os.path.relpath(os.path.join(d, x), root) for d, dirs, fs in os.walk(root) for x in dirs + fs)


def _source_of(app):
    for c in app.commands.values():
        mod = sys.modules.get(getattr(c.fn, "__module__", ""))
        if mod and getattr(mod, "__file__", None):
            return os.path.dirname(os.path.abspath(mod.__file__))
    return None


def _open_from_menu(app, home):
    """In the pty's child: the app's menu with an empty HOME of its own (the sizes run at the same time; first run
    done), commands with --prova."""
    home = tempfile.mkdtemp(dir=home)
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    os.chdir(home)
    apps = [app]
    for a in apps:
        apps += a.sections.values()
        a.state_path = os.path.join(home, ".config", a.name, "state.json")
        a.cache_dir = os.path.join(home, ".cache", a.name, "snapshots")
        def call(c, screen, args, call=a.call):  # the child is thrown away: patching it touches nothing else
            return call(c, screen, list(args) + (["--prova"] if c.dry else []))
        a.call = call
    if app.first_run:
        app.save_state(first_run_done=True)
    return app.main([])


def tests(app, source=None, screens=True, settle=0.8, silence=None):
    """A unittest.TestCase class with one test per rule and command. source = the tool's package folder (default:
    the folder of the module that defines its commands). screens=False: without the menu items in a pty (each
    takes a few seconds); settle = seconds a menu item gets to draw before its screen is read; silence = the
    longest an explicit command may stay mute (default term.HEARTBEAT plus a second)."""
    source = source or _source_of(app)

    def run_cmd(argv, home, colors=False):
        times = []
        out, err = _Clocked(times), _Clocked(times)
        runs = len(proc.RUNS)
        env = {"HOME": home, "USERPROFILE": home, "NO_COLOR": "1"} if not colors else \
            {"HOME": home, "USERPROFILE": home, "PCB_COLORS": "1", "NO_COLOR": ""}
        before, cwd, state, refused = os.getcwd(), app.state_path, list(steps.APPLIED), len(proc.REFUSED)
        os.chdir(home)
        app.state_path = os.path.join(home, ".state-outside", "state.json")  # the app's own state isn't the point
        start = time.time()
        try:
            with mock.patch.dict(os.environ, env), redirect_stdout(out), redirect_stderr(err), \
                    mock.patch("sys.stdin", io.StringIO("")):
                run_cmd.code = app.main(argv)
        finally:
            os.chdir(before)
            app.state_path = cwd
            marks = [start] + times + [time.time()]
            run_cmd.silence = max(b - a for a, b in zip(marks, marks[1:]))
            run_cmd.runs = proc.RUNS[runs:]
            del proc.RUNS[runs:]
        applied = steps.APPLIED[len(state):] + [f"(refused) {r}" for r in proc.REFUSED[refused:]]
        del steps.APPLIED[len(state):]
        del proc.REFUSED[refused:]
        return out.getvalue(), err.getvalue(), applied

    def dry_test(c, words):
        def test(self):
            home = tempfile.mkdtemp()
            try:
                _, err, applied = run_cmd([*words, *c.example, "--prova"], home)
                self.assertEqual(applied, [], f"`{c.name} --prova` applied or tried to write: {applied}")
                made = [p for p in _tree(home) if not p.startswith(".state-outside")]
                self.assertEqual(made, [], f"`{c.name} --prova` wrote {made}\n{err[-500:]}")
            finally:
                shutil.rmtree(home, ignore_errors=True)
        return test

    def ux_test(c, words):
        def test(self):
            home = tempfile.mkdtemp()
            try:
                try:
                    out, err, _ = run_cmd([*words, *c.example, *(["--prova"] if c.dry else [])], home, colors=True)
                except Exception as e:  # the rule: nothing escapes as an exception
                    self.fail(f"`{c.name}` raised {type(e).__name__}: {e}")
                problems = ux_problems(out, run_cmd.code or 0, app.theme)
                if "Traceback (most recent call last)" in err:
                    problems.append("a Python traceback on stderr")
                typed = [*words, *c.example]
                problems += live_problems(run_cmd.runs, typed, app.write_commands, out + "\n" + err)
                limit = silence if silence is not None else term.HEARTBEAT + 1
                if run_cmd.silence > limit:
                    problems.append(f"a mute screen for {run_cmd.silence:.0f} s (at most {limit:.0f}): say what is "
                                    "going on (run_live, screen.wait)")
                self.assertEqual(problems, [], f"`{c.name}`: {problems}\n{ANSI.sub('', out)[-600:]}{err[-300:]}")
            finally:
                shutil.rmtree(home, ignore_errors=True)
        return test

    def json_test(c, words):
        def test(self):
            home = tempfile.mkdtemp()
            try:
                out, err, _ = run_cmd([*words, *c.example, "--json"], home)
                try:
                    json.loads(out)
                except ValueError:
                    self.fail(f"`{c.name} --json`: stdout is not JSON:\n{out[:300]}\n{err[-300:]}")
            finally:
                shutil.rmtree(home, ignore_errors=True)
        return test

    def code_test(self):
        if not source or not os.path.exists(source):
            self.skipTest("no source folder")
        found = code_loading(source)
        self.assertEqual(found, [], "code loaded at run time (configuration must be JSON, App.config):\n"
                         + "\n".join(f"{f}:{n}: {l}" for f, n, l in found))

    def screen_test(path):
        @unittest.skipUnless(screentest.available(), "no pty here (Windows)")
        def test(self):
            home = tempfile.mkdtemp()
            try:
                keys = []
                for question, k, _, _ in path:  # each menu's question, then the item's letter
                    keys += [screentest.wait(question), screentest.keys(k)]
                env = {"HOME": home, "USERPROFILE": home, "PCB_COLORS": "1", "NO_COLOR": ""}
                runs = screentest.check_sizes(lambda: _open_from_menu(app, home), keys + [screentest.pause(settle)],
                                              env=env, settle=settle / 2)
                problems = [f"{n}: {p}" for n, s in runs.items() for p in s.problems()]
                _, _, label, a = path[-1]
                where = f" {a.theme.crumb} ".join(a.crumbs + [label])
                if where not in runs["120x40"].text():  # it was opened: «Tool › Item» on top
                    problems.append(f"«{where}» never on screen: the item didn't open")
                self.assertEqual(problems, [], f"menu {where}: {problems}\n" + "\n".join(
                    f"══ {n}\n{s.report()}" for n, s in runs.items()))
            finally:
                shutil.rmtree(home, ignore_errors=True)
        return test

    def menu_paths(a, before=()):
        """[(words, [(question, letter, label)…])] for every action reachable from a's menu."""
        out, question = [], HELP.get(a.lang, HELP["en"])[2]
        for c, k in zip(a._menu_items(), a.menu_keys()):
            step = before + ((question, k, c.menu.rstrip(" ›"), a),)
            sub = (c.fn.__defaults__ or (None,))[-1]  # a section's item opens that App's menu
            sub = sub if isinstance(sub, App) else None
            out += menu_paths(sub, step) if sub else [step]
        return out

    def setup_test(self):
        if not source or not os.path.exists(source):
            self.skipTest("no source folder")
        programs = [w[0] for a in [app, *getattr(app, "sections", {}).values()] for w in a.write_commands if w]
        self.assertEqual(readme_problems(source, programs), [])

    body = {"test_no_code_loading": code_test, "test_readme_setup": setup_test}
    entries = [([c.name], c) for c in app.commands.values()]
    for sec, sub in getattr(app, "sections", {}).items():
        entries += [([sec, sub.renamed.get(c.name, c.name)], c) for c in sub.commands.values()]
    for words, c in entries:
        key = re.sub(r"\W", "_", "_".join(words))
        if c.dry:
            body[f"test_dry_run_{key}"] = dry_test(c, words)
        body[f"test_ux_{key}"] = ux_test(c, words)
        if c.json:
            body[f"test_json_{key}"] = json_test(c, words)
    for path in menu_paths(app) if screens else []:
        body["test_screen_" + re.sub(r"\W", "_", "_".join(k for _, k, _, _ in path))] = screen_test(path)
    return type("Contract_" + re.sub(r"\W", "_", app.name), (unittest.TestCase,), body)
