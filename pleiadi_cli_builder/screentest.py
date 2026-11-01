"""Screens tested as a person sees them: a command runs in a real pseudo-terminal of a given size, keys are typed
when some text appears, the window is resized while it runs, and every full-screen frame is read back as plain
lines — so a test (or Claude, reading text) can check what was on screen and that the layout holds at every size.

    s = run_screen([sys.executable, "-m", "my_tool"], [wait("Cosa vuoi fare?"), size(60, 20), wait("Cosa"), keys("q")])
    assert not s.problems(expect=["Cosa vuoi fare?"]), s.report()

Checks every frame shown at the end of each size (problems()): no more lines than the window, none wider, the
separator and the key line under the content, no Python traceback. Mac and Linux (stdlib pty); Windows: available()
is False and the tests skip.

argv can also be a function: it runs in the forked child (with the same modules already loaded, e.g. an App and its
commands: run_screen(lambda: app.main([]), …)), its return is the exit code."""
import os, select, signal, struct, sys, time, traceback

from .term import ANSI, visible_len

DRAW = b"\x1b[H"  # every full-screen frame starts at the top left (Screen.draw)


def available():
    return os.name != "nt"


def wait(text):
    """Waits until `text` is on screen (in the output since the previous step)."""
    return ("wait", text)


def keys(*ks):
    """Types keys: text, or names "enter", "esc", "up", "down", "tab", "backspace", "space"."""
    names = {"enter": b"\r", "esc": b"\x1b", "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C",
             "left": b"\x1b[D", "tab": b"\t", "backspace": b"\x7f", "space": b" "}
    return ("keys", b"".join(names[k] if k in names else k.encode() for k in ks))


def size(columns, lines):
    """Resizes the window (the program gets SIGWINCH, as with a real terminal)."""
    return ("size", (columns, lines))


def pause(seconds):
    return ("pause", seconds)


class Frame:
    def __init__(self, lines, columns, rows):
        self.lines, self.columns, self.rows = lines, columns, rows

    def text(self):
        return "\n".join(self.lines)

    def problems(self):
        out = []
        if len(self.lines) > self.rows:
            out.append(f"{len(self.lines)} righe in una finestra di {self.rows}")
        for n, l in enumerate(self.lines, 1):
            if visible_len(l) > self.columns:
                out.append(f"riga {n} larga {visible_len(l)} (finestra {self.columns}): {l[:40]}…")
        if len(self.lines) >= 2:
            if set(self.lines[-2].strip()) != {"─"}:
                out.append("manca il separatore sopra la riga dei tasti")
            if not self.lines[-1].strip():
                out.append("riga dei tasti vuota")
        return out


class Session:
    def __init__(self, raw, phases, code):
        self.raw, self.phases, self.code = raw, phases, code  # phases = [(columns, rows, start, end)] in raw

    def frames(self, columns=None):
        """The complete frames drawn while the window was columns wide (all sizes: None)."""
        out = []
        for c, r, start, end in self.phases:
            if columns not in (None, c):
                continue
            for chunk in self.raw[start:end].split(DRAW)[1:]:
                if b"\x1b[J" not in chunk:
                    continue
                text = chunk.split(b"\x1b[J")[0].decode("utf-8", "replace").replace("\r", "")  # the pty adds \r
                out.append(Frame([ANSI.sub("", l) for l in text.split("\n")], c, r))
        return out

    def last_frames(self):
        """The last frame of each size: what stayed on screen once it settled."""
        out = []
        for c, r, start, end in self.phases:
            fr = Session(self.raw, [(c, r, start, end)], self.code).frames()
            if fr:
                out.append(fr[-1])
        return out

    def text(self):
        return ANSI.sub("", self.raw.decode("utf-8", "replace"))

    def problems(self, expect=()):
        """expect = texts that must stay on screen at every size (e.g. the question being asked)."""
        out = [f"{f.columns}×{f.rows}: {p}" for f in self.last_frames() for p in f.problems()]
        out += [f"{f.columns}×{f.rows}: «{e}» non è sullo schermo" for f in self.last_frames() for e in expect
                if e not in f.text()]
        if "Traceback (most recent call last)" in self.text():
            out.append("traceback Python nell'output")
        if not self.last_frames():
            out.append("nessuna schermata intera disegnata")
        return out

    def report(self, expect=()):
        """The problems, then each size's last frame: readable as text (by a person or by Claude)."""
        parts = self.problems(expect) or ["nessun problema"]
        for f in self.last_frames():
            parts.append(f"── {f.columns}×{f.rows} " + "─" * 20)
            parts.append(f.text())
        return "\n".join(parts)


def _set_size(fd, columns, lines):
    import fcntl, termios  # already loaded by run_screen: nothing is imported in the forked child
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", lines, columns, 0, 0))


def _call(fn, env):
    """In the forked child: fn() with the pty as stdin/stdout/stderr, then exit without running the parent's
    cleanups (its buffered output, atexit)."""
    code = 1
    try:
        for k in ("COLUMNS", "LINES"):
            os.environ.pop(k, None)
        os.environ.update(env)
        sys.stdin = open(0, "r", encoding="utf-8", closefd=False)
        sys.stdout = open(1, "w", encoding="utf-8", closefd=False)
        sys.stderr = open(2, "w", encoding="utf-8", closefd=False)
        r = fn()
        code = r if isinstance(r, int) else 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except BaseException:
        traceback.print_exc()
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            os._exit(code)


def run_screen(argv, steps=(), columns=80, lines=24, env=None, timeout=20, settle=0.6):
    """Runs argv (a command line, or a function called in the child) in a pty columns×lines and plays `steps`
    (wait/keys/size/pause); at the end, if it is still running, it is stopped. Returns a Session."""
    import fcntl, pty, termios, tty  # noqa: F401 — imported before fork (an import in the child can deadlock)
    pid, fd = pty.fork()
    if pid == 0:
        _set_size(0, columns, lines)
        if callable(argv):
            _call(argv, {"TERM": "xterm-256color", **(env or {})})
        e = {k: v for k, v in os.environ.items() if k not in ("COLUMNS", "LINES")}  # they would pin the size
        e.update(TERM="xterm-256color", **(env or {}))
        os.execvpe(argv[0], list(argv), e)
    raw, mark, phases, start = b"", 0, [], 0
    cur, end = (columns, lines), time.time() + timeout
    steps, done = list(steps), None

    def read(seconds):
        nonlocal raw, done
        stop = time.time() + seconds
        while time.time() < stop and done is None:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    done = True
                    return
                raw += chunk
    read(settle)
    while steps and done is None and time.time() < end:
        kind, arg = steps.pop(0)
        if kind == "wait":
            while arg.encode() not in ANSI.sub("", raw[mark:].decode("utf-8", "replace")).encode() \
                    and done is None and time.time() < end:
                read(0.1)
            mark = len(raw)
            read(0.2)
        elif kind == "keys":
            os.write(fd, arg)
            mark = len(raw)
            read(0.3)
        elif kind == "size":
            read(settle)
            phases.append((*cur, start, len(raw)))
            start, cur = len(raw), arg
            _set_size(fd, *arg)
            read(settle)
        elif kind == "pause":
            read(arg)
    read(settle)
    phases.append((*cur, start, len(raw)))
    if done is None:
        os.kill(pid, signal.SIGTERM)
        read(0.3)
    try:
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else status >> 8
    except ChildProcessError:
        code = None
    os.close(fd)
    return Session(raw, phases, code)


def _in_parallel(runs):
    """{name: fn} → {name: fn()}, each in a forked process at the same time (a session is mostly waiting)."""
    import pickle
    pending = {}
    for name, fn in runs.items():
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(r)
            try:
                data = pickle.dumps(fn())
            except BaseException as e:
                data = pickle.dumps(RuntimeError(f"{type(e).__name__}: {e}"))
            with os.fdopen(w, "wb") as f:
                f.write(data)
            os._exit(0)
        os.close(w)
        pending[name] = (pid, r)
    out = {}
    for name, (pid, r) in pending.items():
        with os.fdopen(r, "rb") as f:
            data = f.read()
        os.waitpid(pid, 0)
        out[name] = pickle.loads(data) if data else RuntimeError("the session process ended without a result")
    for name, v in out.items():
        if isinstance(v, BaseException):
            raise RuntimeError(f"{name}: {v}")
    return out


def check_sizes(argv, steps=(), sizes=((60, 20), (80, 24), (120, 40)), **kw):
    """The same screen at several sizes, then resized while open (largest → smallest → largest): {name: Session}.
    `steps` should reach the screen and leave it open; the run ends by itself. The sessions run at the same time."""
    big, small = max(sizes), min(sizes)
    runs = {f"{c}x{l}": (lambda c=c, l=l: run_screen(argv, steps, c, l, **kw)) for c, l in sizes}
    runs["resize"] = lambda: run_screen(argv, list(steps) + [size(*small), size(*big)], *big, **kw)
    return _in_parallel(runs)
