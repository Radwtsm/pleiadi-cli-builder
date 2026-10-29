"""The terminal: colors, keys, a full-screen layout (fixed header, scrolling body, fixed footer) and the
questions (arrow-key menus, text, yes/no). Plain line output when there is no real terminal.

Functions in a tool should not print: they return values and the Screen prints, so the same logic can be
reused by another interface (a window app, a test)."""
import json, os, re, shutil, sys, textwrap, threading, time

WIN, MAC = os.name == "nt", sys.platform == "darwin"

TEXTS = {
    "it": {"hint": "↑↓ scegli · Invio conferma · Ctrl+C esci", "hint_resume": "riprende da dove eri",
           "hint_idle": "Ctrl+C esci", "hint_type": "scrivi · Invio conferma · Ctrl+C esci",
           "hint_read": "↑↓ PgSu PgGiù scorri · Inizio/Fine salta · / cerca · n successiva · Spazio apre/chiude · q chiudi",
           "recommended": "(consigliata)", "type_number": "Scrivi il numero e premi Invio:", "yes": "Sì", "no": "No",
           "done_q": "Fatto?", "retry": "Riprova adesso", "skip": "Salta per ora", "not_yet": "ancora no",
           "ok_count": "{ok}/{tot} a posto", "rerun": "rilancia `{name}`: salta ciò che è già fatto",
           "minutes": "min", "timeout": "tempo scaduto", "would": "farei", "planned": "{n} da fare, niente cambiato (prova)",
           "empty": "niente da mostrare", "rows": "{n} righe", "row": "1 riga", "open_q": "Quale apro?",
           "back": "Indietro", "not_found": "non trovato (un tasto per continuare)",
           "hint_board": "↑↓ muovi · Spazio spunta · a tutte{actions} · Invio fatto · q esci",
           "checked": "{n} di {tot} spuntate"},
    "en": {"hint": "↑↓ choose · Enter confirm · Ctrl+C quit", "hint_resume": "resumes where you left off",
           "hint_idle": "Ctrl+C quit", "hint_type": "type · Enter confirm · Ctrl+C quit",
           "hint_read": "↑↓ PgUp PgDn scroll · Home/End jump · / search · n next · Space fold · q close",
           "recommended": "(recommended)", "type_number": "Type the number and press Enter:", "yes": "Yes", "no": "No",
           "done_q": "Done?", "retry": "Try again now", "skip": "Skip for now", "not_yet": "not yet",
           "ok_count": "{ok}/{tot} ok", "rerun": "run `{name}` again: it skips what is already done",
           "minutes": "min", "timeout": "timed out", "would": "would", "planned": "{n} to do, nothing changed (dry run)",
           "empty": "nothing to show", "rows": "{n} rows", "row": "1 row", "open_q": "Which one?",
           "back": "Back", "not_found": "not found (any key to go on)",
           "hint_board": "↑↓ move · Space check · a all{actions} · Enter done · q quit",
           "checked": "{n} of {tot} checked"},
}

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\]8;;[^\x1b]*\x1b\\")


class Theme:
    """Colors as SGR codes (e.g. "38;5;153" or "38;2;232;37;63"), the spinner frames and the glyphs."""
    FULL = dict(spinner="✦✧⋆·⋆✧", mark="✦", step="⏺", attach="⎿", arrow="→", prompt="❯", yes="✓", no="✗",
                corners="╭╮╰╯")
    # only characters every console font has (the classic Windows console: Consolas, Lucida Console)
    SAFE = dict(spinner="|/-\\", mark="*", step="●", attach="└", arrow="→", prompt=">", yes="√", no="x",
                corners="┌┐└┘")

    def __init__(self, accent="38;5;153", ok="32", error="31", dim="2", bold="1", glyphs=None, warn="33",
                 select="48;5;237", **marks):
        """glyphs = "full" or "safe"; default: safe in the classic Windows console (no Windows Terminal),
        PCB_GLYPHS=safe|full to choose. marks = any of spinner, mark, step, attach, arrow, prompt, yes, no, corners."""
        # roles, like Claude Code: one accent for what is interactive or selected; dim for what is secondary
        # (borders, hints, notes); ok/warn/error only for a meaning; select = the background of the selected row
        self.accent, self.ok, self.error, self.dim, self.bold = accent, ok, error, dim, bold
        self.warn, self.select = warn, select
        glyphs = glyphs or os.environ.get("PCB_GLYPHS") or ("safe" if WIN and not os.environ.get("WT_SESSION") else "full")
        for k, v in {**(self.SAFE if glyphs == "safe" else self.FULL), **marks}.items():
            setattr(self, k, v)

    @staticmethod
    def rgb(hex_color):
        """"#e8253f" → "38;2;232;37;63" (truecolor foreground)."""
        h = hex_color.lstrip("#")
        return "38;2;" + ";".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def pairs(hint):
    """«↑↓ scegli · Invio conferma» → [("↑↓", "scegli"), ("Invio", "conferma")]: the last word says what the keys
    before it do; a single word is only a label."""
    out = []
    for part in hint.split(" · "):
        words = part.split(" ")
        out.append((" ".join(words[:-1]), words[-1]) if len(words) > 1 else ("", part))
    return out


def visible_len(s):
    return len(ANSI.sub("", s))


def clip(s, width):
    """A colored line cut to `width` visible columns (color codes don't count), never wrapping."""
    out, n, i = [], 0, 0
    while i < len(s):
        m = ANSI.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        if n >= width - 1 and i < len(s) - 1:
            out.append("…")
            break
        out.append(s[i])
        n += 1
        i += 1
    return "".join(out) + ("\x1b[0m" if "\x1b[" in s else "")


CBREAK = {"depth": 0, "saved": None}  # single-key mode kept on while a full screen is open


def cbreak(on):
    """Single-key mode for the whole time a screen is open (not toggled per key: what is typed between two reads —
    fast typing, a paste — would land in the line buffer and get lost or arrive only with Enter)."""
    if WIN or not sys.stdin.isatty():
        return
    import termios, tty
    fd = sys.stdin.fileno()
    if on:
        if CBREAK["depth"] == 0:
            CBREAK["saved"] = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        CBREAK["depth"] += 1
    elif CBREAK["depth"]:
        CBREAK["depth"] -= 1
        if CBREAK["depth"] == 0 and CBREAK["saved"]:
            termios.tcsetattr(fd, termios.TCSADRAIN, CBREAK["saved"])


def key():
    """One key without Enter: "up", "down", "enter", "backspace" or the character. Ctrl+C raises as usual."""
    if WIN:
        import msvcrt
        k = msvcrt.getwch()
        if k in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "I": "pgup", "Q": "pgdn", "G": "home", "O": "end",
                    "\x0f": "backtab"}.get(msvcrt.getwch(), "")
        if k == "\t":
            return "tab"
        if k == "\x1b":
            return "esc"
    else:
        import termios, tty
        fd = sys.stdin.fileno()
        kept = CBREAK["depth"] > 0
        before = None if kept else termios.tcgetattr(fd)
        try:
            if not kept:
                tty.setcbreak(fd)
            b = os.read(fd, 1)
            if b == b"\x1b":
                import select
                if not select.select([fd], [], [], 0.05)[0]:
                    return "esc"  # Esc alone
                b += os.read(fd, 2)
                if b[2:3].isdigit():  # \x1b[5~ PgUp, \x1b[6~ PgDn, \x1b[1~ Home, \x1b[4~ End
                    while not b.endswith(b"~") and len(b) < 8:
                        b += os.read(fd, 1)
            elif b and b[0] >= 0xC0:  # an accented letter is several bytes (UTF-8)
                b += os.read(fd, 1 if b[0] < 0xE0 else 2 if b[0] < 0xF0 else 3)
            k = b.decode(errors="ignore")
        finally:
            if before is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, before)
        k = {"\x1b[A": "up", "\x1bOA": "up", "\x1b[B": "down", "\x1bOB": "down", "\x1b[5~": "pgup", "\x1b[6~": "pgdn",
             "\x1b[H": "home", "\x1bOH": "home", "\x1b[1~": "home", "\x1b[F": "end", "\x1bOF": "end",
             "\x1b[4~": "end", "\x1b[Z": "backtab", "\t": "tab"}.get(k, k)
    if k == "\x03":
        raise KeyboardInterrupt
    if k in ("\x7f", "\x08"):
        return "backspace"
    return "enter" if k in ("\r", "\n") else k


SCREENS = []  # the open full screen (one): run(interactive=True) suspends it for programs that talk by themselves
LIVE = []  # the open status line (Screen.wait): long functions report progress into it without printing


SECRETS = set()  # values read with secret() in this run: never in arguments, masked in every output
MASK = "••••"


def mask(text):
    """The text with every secret of this run replaced by ••••."""
    if not SECRETS or not text:
        return text
    for v in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(v, MASK)
    return text


def progress(fraction=None, detail=None):
    """Report progress from inside any function: goes to the open spinner line, if there is one."""
    if LIVE:
        LIVE[-1].advance(fraction, detail)


class Screen:
    """Full screen like Claude Code: the header box stays at the top, the status line at the bottom, the content
    scrolls in between; redraws itself when the window is resized. `<NAME>_PLAIN=1`, `NO_COLOR` or no real
    terminal = plain lines."""

    def __init__(self, name="tool", title="", theme=None, lang="it", plain_env=None):
        self.name, self.title, self.theme = name, title or name, theme or Theme()
        self.t = TEXTS.get(lang, TEXTS["en"])
        self.colors = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass
        if WIN and self.colors:  # ANSI colors in the Windows console (VT mode)
            try:
                import ctypes
                k = ctypes.windll.kernel32
                h, m = k.GetStdHandle(-11), ctypes.c_uint32()
                if not (k.GetConsoleMode(h, ctypes.byref(m)) and k.SetConsoleMode(h, m.value | 4)):
                    self.colors = False
            except (OSError, AttributeError):
                self.colors = False
        plain_env = plain_env or re.sub(r"\W", "_", name).upper() + "_PLAIN"
        self.full = self.colors and sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get(plain_env)
        self.results, self.no_input, self.dry, self.read_only, self.json = [], False, False, False, False
        self.refresh, self.mode = False, "idle"  # mode: idle, choose, type, read — the hint follows it
        self.suspended = False
        self.head, self.body, self.foot, self.last = [], [], "", []
        self.opened, self.lock, self.size, self.attached, self.width = False, threading.RLock(), None, False, 0

    # ── the screen ──
    def open(self):
        if not self.full or self.opened:
            return
        self.opened = True
        cbreak(True)
        sys.stdout.write("\033[?1049h\033[?25l")
        SCREENS.append(self)
        import atexit
        atexit.register(self.close)  # any exit gives the normal terminal back
        if not WIN:
            try:
                import signal
                signal.signal(signal.SIGWINCH, lambda *_: self.draw())
            except (ValueError, OSError, AttributeError):
                pass

        def watch():  # Windows too (no SIGWINCH): check the size 5 times a second
            while self.opened:
                if shutil.get_terminal_size((80, 24)) != self.size:
                    self.draw()
                time.sleep(0.2)
        threading.Thread(target=watch, daemon=True).start()
        self.draw()

    def close(self):
        """Back to the normal screen, leaving the summary there (or the whole log if there is none)."""
        if not self.opened:
            return
        self.opened = False
        cbreak(False)
        if self in SCREENS:
            SCREENS.remove(self)
        sys.stdout.write("\033[?25h\033[?1049l")
        keep = [r for r in (self.last or "\n".join(self.body).strip("\n").split("\n")) if r]
        sys.stdout.write("\n".join(keep) + ("\n" if keep else ""))
        sys.stdout.flush()

    def suspend(self):
        """For a program that talks to the person by itself (a login, an installer): normal screen."""
        if self.opened:
            self.suspended = True  # nothing draws over the program (or the hidden prompt) meanwhile
            if CBREAK["depth"] and CBREAK["saved"]:  # the other program gets a normal terminal
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, CBREAK["saved"])
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()

    def resume(self):
        self.suspended = False
        if self.opened and CBREAK["depth"] and not WIN and sys.stdin.isatty():
            import tty
            tty.setcbreak(sys.stdin.fileno())
        if self.opened:
            sys.stdout.write("\033[?1049h\033[?25l")
            self.size = None
            self.draw()

    def out(self, line=""):
        line = mask(line)
        if not self.full:
            print(line, file=sys.stderr if self.json else sys.stdout)  # --json: stdout only for the data
            return
        self.open()
        with self.lock:
            self.body += line.split("\n")
            del self.body[:-500]
        self.draw()

    def draw(self):
        if not self.opened or self.suspended:
            return
        with self.lock:
            self.size = shutil.get_terminal_size((80, 24))
            w, h = self.size.columns, self.size.lines
            head = [clip(r, w) for r in self.head] if h >= len(self.head) + 8 else []
            foot = [self.c(self.theme.dim, "─" * w), clip(self.foot or "  " + self.hint_line(), w)]
            room = max(1, h - len(head) - len(foot))
            body = [clip(r, w) for r in self.body[-room:]]
            body += [""] * (room - len(body))
            lines = head + body + foot
            sys.stdout.write("\033[H" + "\r\n".join(r + "\033[K" for r in lines[:h]) + "\033[J")
            sys.stdout.flush()

    def clear(self):
        if self.full:
            with self.lock:
                self.body = []
            self.draw()
        elif self.colors:
            sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()

    def hint(self):
        """Only the keys that work now (owner: «arrows» shown with nothing to choose was a bug), plus the open
        menu-session accesses («VPN aperta da 4 min»)."""
        from .access import status_line
        h = self.t.get({"choose": "hint", "type": "hint_type", "read": "hint_read"}.get(self.mode, "hint_idle"), "")
        st = status_line()
        return h + (f" · {st}" if st else "")

    def keys(self, items):
        """[(keys, what they do)] → «↑↓ scegli · Invio conferma»: keys in the accent, bold; what they do, muted."""
        sep = self.dim(" · ")
        return sep.join((self.c(f"{self.theme.accent};1", k) if k else "") + self.dim((" " if k else "") + label)
                        for k, label in items)

    def hint_line(self):
        """The bottom line: the keys of this moment, then the open accesses (muted)."""
        from .access import status_line
        h = self.t.get({"choose": "hint", "type": "hint_type", "read": "hint_read"}.get(self.mode, "hint_idle"), "")
        st = status_line()
        return self.keys(pairs(h)) + (self.dim(f" · {st}") if st else "")

    # ── colors ──
    def c(self, code, text):
        return f"\033[{code}m{text}\033[0m" if self.colors else text

    def acc(self, text):
        return self.c(self.theme.accent, text)

    def dim(self, text):
        return self.c(self.theme.dim, text)

    def bold(self, text):
        return self.c(self.theme.bold, text)

    def text_width(self):
        return max(40, min(shutil.get_terminal_size((80, 24)).columns - 1, 100))

    # ── blocks ──
    def header(self, subtitle=""):
        """The opening box, like Claude Code's: fixed at the top for the whole session."""
        lines = [self.acc(self.theme.mark + " ") + self.bold(self.title) + self.dim(f"  {self.name}")]
        if subtitle:
            lines.append("  " + subtitle)
        if self.full:
            self.head = self.frame(lines)
            self.open()
            self.draw()
        else:
            self.box(lines + ["  " + self.keys(pairs(self.t["hint_idle"])) + self.dim(f" ({self.t['hint_resume']})")])

    def frame(self, lines):
        vis = [visible_len(r) for r in lines]
        w = self.width = max(max(vis) + 2, self.width)  # all boxes equally wide
        d = self.theme.dim
        tl, tr, bl, br = self.theme.corners
        return ([self.c(d, tl + "─" * w + tr)]
                + [self.c(d, "│") + " " + r + " " * (w - n - 1) + self.c(d, "│") for r, n in zip(lines, vis)]
                + [self.c(d, bl + "─" * w + br)])

    def box(self, lines):
        self.out("")
        for r in self.frame(lines):
            self.out(r)

    def section(self, text):
        self.out("")
        self.out(self.acc(self.theme.mark) + " " + self.bold(text))
        self.attached = True

    def step(self, n, total, text, why=""):
        """⏺ Step  n/total · why — the results attach below with ⎿ (like Claude Code's actions)."""
        self.out("")
        self.out(self.acc(self.theme.step) + " " + self.bold(text) + self.dim(f"  {n}/{total}" + (f" · {why}" if why else "")))
        self.attached = True

    def _indent(self):
        r = f"  {self.theme.attach} " if self.attached else "    "
        self.attached = False
        return self.dim(r)

    def info(self, text):
        if "\033" in text:  # already colored: no wrapping computed on the codes
            self.out("    " + text)
            return
        self.out(textwrap.fill(text, self.text_width(), initial_indent="    ", subsequent_indent="    ",
                               break_on_hyphens=False, break_long_words=False))

    def todo(self, text):
        """What the person has to do, with the exact names of buttons and menus."""
        for r in text.split("\n"):
            lines = textwrap.wrap(r, self.text_width() - 6, break_on_hyphens=False, break_long_words=False) or [""]
            self.out("    " + self.acc(self.theme.arrow) + " " + lines[0])
            for x in lines[1:]:
                self.out("      " + x)

    def table(self, rows, columns=None, titles=None, pick=False):
        """rows = [dict]; columns = keys to show (default: those of the first row); titles = {key: header}.
        With --json (screen.json) the rows go to stdout as JSON, for other programs; otherwise a table that fits the
        window: the widest column is cut first. pick=True in a real terminal: then the rows can be chosen with the
        arrows and Enter opens one — returns its index (None: «Indietro», or no terminal)."""
        columns = columns or (list(rows[0]) if rows else [])
        if self.json:
            print(mask(json.dumps([{k: r.get(k) for k in columns} for r in rows], ensure_ascii=False, indent=1)))
            return
        if not rows:
            self.info(self.dim(self.t["empty"]))
            return
        titles = titles or {}
        cell = lambda v: "" if v is None else " ".join(str(v).split())
        head = [str(titles.get(k, k)) for k in columns]
        body = [[cell(r.get(k)) for k in columns] for r in rows]
        widths = [max(len(h), *(len(b[i]) for b in body)) for i, h in enumerate(head)]
        room = self.text_width() - 4 - 2 * (len(columns) - 1) - (len(str(len(rows) + 1)) + 2 if pick else 0)
        while sum(widths) > room and max(widths) > 6:
            widths[widths.index(max(widths))] -= 1
        fit = lambda v, w: v if len(v) <= w else v[:w - 1] + "…"
        line = lambda vals: "  ".join(fit(v, w).ljust(w) for v, w in zip(vals, widths)).rstrip()
        count = self.dim(self.t["row"] if len(rows) == 1 else self.t["rows"].format(n=len(rows)))
        if pick and self.full and self.interactive:  # the rows once, as choices, under their column titles
            self.out("    " + count)
            i = self.choose(self.t["open_q"], [line(b) for b in body] + [self.t["back"]], header=line(head))
            return i if i < len(rows) else None
        self.out("    " + self.bold(line(head)))
        self.out("    " + self.dim("─" * len(line(head))))  # titles apart from the data, at a glance
        for b in body:
            self.out("    " + line(b))
        self.out("    " + count)
        return None

    def detail(self, d):
        """A Detail (pleiadi_cli_builder.detail): JSON with --json, plain text without a real terminal, otherwise
        the scrolling view until q/Esc/Enter."""
        from .detail import Pager
        if self.data(d.as_dict()):
            return
        size = shutil.get_terminal_size((80, 24))
        pager = Pager(d, min(size.columns - 1, 100) if not self.full else size.columns, size.lines - 2, self.c)
        if not (self.full and self.interactive):
            for l in pager.plain():
                self.out(l)
            return
        self.open()
        saved, self.mode = (self.head, self.body), "read"
        try:
            while True:
                size = shutil.get_terminal_size((80, 24))
                pager.resize(size.columns, size.lines - 2)  # rewraps when the window changes
                with self.lock:
                    self.head, self.body = [], pager.render()
                self.foot = self.foot or "  " + self.keys(pairs(pager.hint()))
                self.draw()
                what = pager.handle(key())
                self.foot = ""
                if isinstance(what, tuple):  # a one-key action: its message stays until the next key
                    label, fn = d.actions[what[1]]
                    try:
                        msg = fn(self) or label
                    except Exception as e:  # an action that fails says why, the view stays open
                        msg = f"{label}: {e}"
                    self.foot = "  " + self.acc(self.theme.arrow + " ") + str(msg)
                    continue
                if what == "quit":
                    break
                if what == "search":
                    self.mode = "type"
                    q = self._type_line("/")
                    self.mode = "read"
                    if q and not pager.search(q):
                        self.foot = self.dim(f"  «{q}»: {self.t['not_found']}")
                        self.draw()
                        key()
                        self.foot = ""
        finally:
            with self.lock:
                self.head, self.body = saved
            self.mode = "idle"
            self.draw()

    def board(self, b):
        """A Board (pleiadi_cli_builder.board): in a real terminal the grouped table with check marks, filled in the
        background, actions on one key, until Enter (returns the checked rows) or q/Esc (None). Without one: the
        groups as plain tables once every cell has arrived; with --json the rows, each with its group."""
        from .board import BoardView
        if self.json or not (self.full and self.interactive):
            b.start()
            b.wait()
            if not self.data(b.as_rows()):
                for title, rows in b.groups:
                    self.out("")
                    self.out("  " + self.bold(title))
                    self.table(rows, b.columns, b.titles)
            return None
        th = self.theme
        view = BoardView(b, color=self.c, select=f"{th.accent};1;{th.select}", error=th.error, dim=th.dim,
                         check=th.yes, texts=self.t)

        def paint():  # also from the background cells, as each one arrives
            with self.lock:
                size = shutil.get_terminal_size((80, 24))
                view.resize(size.columns, size.lines - 2)
                self.head, self.body = [], view.render()
            self.draw()
        self.open()
        saved, self.mode = (self.head, self.body), "read"
        b.start(on_change=paint)
        try:
            while True:
                self.foot = self.foot or "  " + self.keys(pairs(view.hint()))
                paint()
                k = key()
                self.foot = ""
                with self.lock:
                    what = view.handle(k)
                if isinstance(what, tuple):
                    rows = view.targets()
                    label, fn = b.actions[what[1]]
                    try:
                        msg = fn(self, rows) or label
                    except Exception as e:  # an action that fails says why, the table stays open
                        msg = f"{label}: {e}"
                    self.foot = "  " + self.acc(th.arrow + " ") + str(msg)
                    b.start(on_change=paint, rows=rows)  # what the action changed shows up by itself
                    continue
                if what == "done":
                    return view.checked()
                if what == "quit":
                    return None
        finally:
            with self.lock:
                self.head, self.body = saved
            self.mode = "idle"
            self.draw()

    def _type_line(self, prompt):
        """A short answer typed in the bottom line (the search of the detail view)."""
        text = ""
        sys.stdout.write("\033[?25h")
        try:
            while True:
                self.foot = "  " + self.acc(prompt) + text
                self.draw()
                k = key()
                if k in ("enter", "esc"):
                    return text if k == "enter" else ""
                if k == "backspace":
                    text = text[:-1]
                elif len(k) == 1 and k.isprintable():
                    text += k
        finally:
            self.foot = ""
            sys.stdout.write("\033[?25l")

    def data(self, obj):
        """With --json: `obj` (any JSON value) to stdout and True; otherwise nothing and False — for commands whose
        data isn't one table."""
        if self.json:
            print(mask(json.dumps(obj, ensure_ascii=False, indent=1)))
        return self.json

    @property
    def interactive(self):
        return sys.stdin.isatty() and not self.no_input

    def secret_input(self, question):
        """A hidden answer (a token, a password): never shown, never kept on screen."""
        import getpass
        self.suspend()
        try:
            return getpass.getpass(f"  ? {question} ").strip()
        except EOFError:
            self.no_input = True
            return ""
        finally:
            self.resume()

    def link(self, label, url):
        self.out("    " + self.dim(f"{label:<26}") + " " + (self.c("4", url) if url.startswith("http") else url))

    def result(self, r):
        """Show a Result (✓ / ✗ with what to do) and, if it has `retry`, offer to retry on the spot (max 3)."""
        self.results.append(r)
        th = self.theme
        if r.planned:
            self.out(self._indent() + self.acc("○") + f" {r.name}" + self.dim(f" · {self.t['would']}: {r.note}"))
        elif r.skipped:
            self.out(self._indent() + self.dim(f"{th.yes} {r.name}" + (f" · {r.note}" if r.note else "")))
        elif r.ok:
            self.out(self._indent() + self.c(th.ok, th.yes) + f" {r.name}" + (self.dim(f" · {r.note}") if r.note else ""))
        else:
            self.out(self._indent() + self.c(th.error, th.no) + f" {r.name}")
            if r.fix:
                self.todo(r.fix)
            tries = 0  # never forever: at most 3, and none if nobody answers
            while (r.retry and sys.stdin.isatty() and not self.no_input and tries < 3
                   and self.confirm(self.t["done_q"], self.t["retry"], self.t["skip"])):
                tries += 1
                try:
                    r.ok = bool(r.retry())
                except Exception as x:  # an error while retrying doesn't stop the run
                    self.todo(f"{self.t['not_yet']}: {x}")
                if r.ok:
                    self.out("    " + self.c(th.ok, th.yes) + f" {r.name}")
                    break
                self.out("    " + self.c(th.error, th.no) + f" {r.name} · {self.t['not_yet']}")
        return r.ok

    def summary(self, minutes=None):
        """The closing box: n/total ok and what is still ✗; it stays on screen after exit."""
        good = [r for r in self.results if r.ok or r.skipped]
        planned = [r for r in self.results if r.planned]
        everything = len(good) == len(self.results)
        th = self.theme
        lines = [(self.c(th.ok, th.yes + " ") if everything else self.acc(th.mark + " "))
                 + self.bold(self.t["ok_count"].format(ok=len(good), tot=len(self.results)))
                 + (self.dim(f" · {minutes} {self.t['minutes']}") if minutes is not None else "")]
        lines += ["  " + self.c(th.error, th.no) + f" {r.name}" for r in self.results if not (r.ok or r.skipped or r.planned)]
        if planned:
            lines.append("  " + self.acc("○ ") + self.t["planned"].format(n=len(planned)))
        elif not everything:
            lines.append(self.dim("  " + self.t["rerun"].format(name=self.name)))
        self.box(lines)
        self.last = self.frame(lines)
        return everything

    # ── questions ──
    def ask(self, question, default=""):
        if self.full:
            return self._type(question, default)
        try:
            r = input("\n  " + self.acc("?") + " " + self.bold(question) + self.dim(f" [{default}]" if default else "")
                      + "\n  " + self.acc(self.theme.prompt) + " ").strip()
        except EOFError:  # nobody answers (run by a script or by Claude): go on with the default
            self.no_input, r = True, ""
        return r or default

    def choose(self, question, options, header=None):
        """options = [text]; the first is the recommended one. Returns the index. Arrows + Enter (or the number);
        without a real terminal: type the number. header = column titles shown above the options (a table)."""
        self.out("")
        self.out("  " + self.acc("?") + " " + self.bold(question))
        if header:
            self.out(self._menu_header(header, len(options)))
        if self.colors and sys.stdin.isatty():
            try:
                return self._menu(options, recommend=not header)
            except (OSError, ImportError):
                pass  # no single keys (odd console): fall back to the number
        for i, o in enumerate(options):
            self.out(self._menu_row(i, o, None, len(options), "" if header else "  " + self.t["recommended"]))
        while True:
            r = self.ask(self.t["type_number"], "1")
            if r.isdigit() and 1 <= int(r) <= len(options):
                return int(r) - 1

    def confirm(self, question, yes=None, no=None):
        return self.choose(question, [yes or self.t["yes"], no or self.t["no"]]) == 0

    def _menu_row(self, i, o, sel, n, rec):
        """One option, its number right-aligned (1..n) so that texts start in the same column as the header. The
        selected one is a bar across the width (accent on a dark background), like Claude Code's."""
        nw = len(str(n))
        w = self.text_width() - 6 - nw
        o = o if len(o) <= w else o[:w - 1] + "…"  # one line per option, even on a narrow screen
        has_note = rec and i == 0 and len(o) + len(rec) + 1 <= w
        num = f"{i + 1:>{nw}}."
        if i == sel:
            bar = f"  {self.theme.prompt} {num} {o}" + (rec if has_note else "")
            return self.c(f"{self.theme.accent};1;{self.theme.select}", bar.ljust(self.text_width()))
        return self.dim(f"    {num} ") + o + (self.dim(rec) if has_note else "")

    def _menu_header(self, header, n):
        pad = " " * (4 + len(str(n)) + 2)
        return pad + self.bold(header) + "\n" + pad + self.dim("─" * visible_len(header))

    def _menu(self, options, recommend=True):
        rec = "  " + self.t["recommended"] if recommend else ""
        row = lambda i, o: self._menu_row(i, o, sel, n, rec)
        sel, n = 0, len(options)
        self.mode = "choose"

        def move(k):
            return ((sel - 1) % n if k == "up" else (sel + 1) % n if k == "down" else
                    int(k) - 1 if k.isdigit() and 1 <= int(k) <= n else sel)
        if self.full:  # the options stay in place; afterwards one line with the answer
            with self.lock:
                start = len(self.body)
                self.body += [row(i, o) for i, o in enumerate(options)]
            self.draw()
            while True:
                k = key()
                if k == "enter":
                    break
                sel = move(k)
                with self.lock:
                    self.body[start:start + n] = [row(i, o) for i, o in enumerate(options)]
                self.draw()
            with self.lock:
                self.body[start:] = ["    " + self.acc(self.theme.prompt + " ") + options[sel]]
            self.mode = "idle"
            self.draw()
            return sel
        sys.stdout.write("\033[?25l")
        try:
            for i, o in enumerate(options):
                print(row(i, o))
            print(self.dim("    " + self.t["hint"]))
            while True:
                k = key()
                if k == "enter":
                    return sel
                new = move(k)
                if new == sel:
                    continue
                sel = new
                sys.stdout.write(f"\033[{n + 1}F")  # back up and rewrite the options
                for i, o in enumerate(options):
                    sys.stdout.write("\033[2K" + row(i, o) + "\n")
                sys.stdout.write("\n")
                sys.stdout.flush()
        finally:
            self.mode = "idle"
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()

    def _type(self, question, default):
        """A typed answer in full screen: typed into the fixed status line at the bottom."""
        self.out("")
        self.out("  " + self.acc("?") + " " + self.bold(question) + self.dim(f" [{default}]" if default else ""))
        text = ""
        self.mode = "type"
        sys.stdout.write("\033[?25h")
        try:
            while True:
                self.foot = "  " + self.acc(self.theme.prompt + " ") + text
                self.draw()
                k = key()
                if k == "enter":
                    break
                if k == "backspace":
                    text = text[:-1]
                elif len(k) == 1 and k.isprintable():
                    text += k
        finally:
            self.foot, self.mode = "", "idle"
            sys.stdout.write("\033[?25l")
        self.out("    " + self.acc(self.theme.prompt + " ") + (text.strip() or self.dim(default or "—")))
        return text.strip() or default

    def wait(self, text):
        """`with screen.wait("downloading") as w: w.advance(0.4, "12/30 files")` — spinner, shimmer, progress
        bar with ETA, the last line of the running program and the elapsed time."""
        return Wait(self, text)


class Wait:
    """The live status line while a long step works (only in a real terminal)."""
    def __init__(self, screen, text):
        self.s, self.text, self.stop = screen, text, threading.Event()
        self.fraction, self.detail, self.start, self.k, self.thread = None, "", time.time(), -1, None

    def advance(self, fraction=None, detail=None):
        if fraction is not None:
            self.fraction = max(0.0, min(1.0, fraction))
        if detail is not None:
            self.detail = " ".join(str(detail).split())

    def shimmer(self, text):
        """A light that runs over the text, like when Claude Code is thinking."""
        if not self.s.colors:
            return text
        self.k += 1
        pos = self.k % (len(text) + 12) - 3
        return "".join(self.s.bold(x) if abs(i - pos) <= 1 else self.s.dim(x) if abs(i - pos) > 4 else x
                       for i, x in enumerate(text))

    def line(self, frame):
        """Always inside the window width (a wrapping line smears the screen on every frame): first the detail
        gets shorter, then the bar, then the text."""
        s, sec = self.s, int(time.time() - self.start)
        elapsed = f"{sec // 60}:{sec % 60:02d}" if sec >= 60 else f"{sec} s"
        if self.fraction is not None and 0.03 < self.fraction < 1 and sec >= 5:  # what's left, from the pace so far
            left = int(sec * (1 - self.fraction) / self.fraction)
            elapsed += f" · ~{left // 60} min" if left >= 90 else f" · ~{left} s"
        w = shutil.get_terminal_size((80, 24)).columns - 1
        lb = 20 if self.fraction is not None else 0
        text = self.text
        free = w - 6 - len(text) - (lb + 7 if lb else 0) - len(elapsed) - 2
        if free < 0 and lb:
            lb = max(6, lb + free)
            free = w - 6 - len(text) - lb - 7 - len(elapsed) - 2
        if free < 0:
            text = text[:max(8, len(text) + free - 1)] + "…"
            free = 0
        det = self.detail if len(self.detail) + 2 <= free else ""
        bar = ""
        if lb:
            n = round(self.fraction * lb)
            bar = "  " + s.acc("━" * n) + s.dim("─" * (lb - n)) + f" {round(self.fraction * 100):3d}%"
        return "    " + s.acc(frame) + " " + self.shimmer(text) + bar + s.dim(("  " + det if det else "") + f"  {elapsed}")

    def __enter__(self):
        LIVE.append(self)
        s = self.s
        if s.full:
            s.open()
        elif not s.colors:
            print("    … " + self.text, file=sys.stderr)  # stdout stays for the data
            return self

        def spin():
            i = 0
            while not self.stop.wait(0.12):
                if s.suspended or s.mode in ("choose", "type"):  # a question is on screen: the spinner waits
                    continue
                ln = self.line(s.theme.spinner[i % len(s.theme.spinner)])
                if s.full:
                    s.foot = ln
                    s.draw()
                else:
                    sys.stderr.write("\r" + ln + "\033[K")
                    sys.stderr.flush()
                i += 1
        self.thread = threading.Thread(target=spin, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        if self in LIVE:
            LIVE.remove(self)
        if self.thread:
            self.thread.join()
            if self.s.full:
                self.s.foot = ""
                self.s.draw()
            else:
                sys.stderr.write("\r\033[K")
                sys.stderr.flush()
