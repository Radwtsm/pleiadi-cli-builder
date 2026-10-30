"""Contract tests every tool gets for free (`new` puts them in tests/): the general rules checked by code.

    from pleiadi_cli_builder.contract import tests
    from my_tool.__main__ import app
    Contract = tests(app)          # a unittest.TestCase

- every command with effects, run with --prova in an empty HOME and working folder, creates nothing, applies no
  step and runs no declared write command;
- every command with json=True prints valid JSON on stdout with --json;
- every command run with --prova ends with its outcome (✓ or ✗ and what: App.call adds one when the command doesn't
  say it) and shows no Python traceback;
- the tool's code never loads code at run time (exec, eval, importlib, runpy, __import__): configuration is
  read as JSON (App.config)."""
import io, json, os, re, shutil, sys, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from . import proc, steps

CALLS, MODULES = {"exec", "eval", "__import__"}, {"importlib", "runpy"}


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


def _tree(root):
    return sorted(os.path.relpath(os.path.join(d, x), root) for d, dirs, fs in os.walk(root) for x in dirs + fs)


def _source_of(app):
    for c in app.commands.values():
        mod = sys.modules.get(getattr(c.fn, "__module__", ""))
        if mod and getattr(mod, "__file__", None):
            return os.path.dirname(os.path.abspath(mod.__file__))
    return None


def tests(app, source=None):
    """A unittest.TestCase class with one test per rule and command. source = the tool's package folder (default:
    the folder of the module that defines its commands)."""
    source = source or _source_of(app)

    def run_cmd(argv, home):
        out, err = io.StringIO(), io.StringIO()
        env = {"HOME": home, "USERPROFILE": home, "NO_COLOR": "1"}
        before, cwd, state, refused = os.getcwd(), app.state_path, list(steps.APPLIED), len(proc.REFUSED)
        os.chdir(home)
        app.state_path = os.path.join(home, ".state-outside", "state.json")  # the app's own state isn't the point
        try:
            with mock.patch.dict(os.environ, env), redirect_stdout(out), redirect_stderr(err):
                app.main(argv)
        finally:
            os.chdir(before)
            app.state_path = cwd
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

    def outcome_test(c, words):
        def test(self):
            home = tempfile.mkdtemp()
            try:
                out, err, _ = run_cmd([*words, *c.example, "--prova"], home)
                text = out + err
                self.assertNotIn("Traceback (most recent call last)", text, f"`{c.name} --prova` shows a traceback")
                last = [r.strip() for r in out.splitlines() if r.strip()][-1:] or [""]
                glyphs = (app.theme.yes, app.theme.no, "✓", "✗", "√", "x ")
                self.assertTrue(last[0].startswith(glyphs) or any(g in last[0] for g in ("╰", "└")),
                                f"`{c.name} --prova` doesn't end with ✓/✗ and what happened: {last[0]!r}")
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

    body = {"test_no_code_loading": code_test}
    entries = [([c.name], c) for c in app.commands.values()]
    for sec, sub in getattr(app, "sections", {}).items():
        entries += [([sec, sub.renamed.get(c.name, c.name)], c) for c in sub.commands.values()]
    for words, c in entries:
        key = re.sub(r"\W", "_", "_".join(words))
        if c.dry:
            body[f"test_dry_run_{key}"] = dry_test(c, words)
            body[f"test_outcome_{key}"] = outcome_test(c, words)
        if c.json:
            body[f"test_json_{key}"] = json_test(c, words)
    return type("Contract_" + re.sub(r"\W", "_", app.name), (unittest.TestCase,), body)
