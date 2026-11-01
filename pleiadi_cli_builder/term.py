"""The terminal: colors, keys, a full-screen layout (fixed header, scrolling body, fixed footer) and the
questions (arrow-key menus, text, yes/no). Plain line output when there is no real terminal.

Functions in a tool should not print: they return values and the Screen prints, so the same logic can be
reused by another interface (a window app, a test)."""
import json, os, re, shutil, sys, textwrap, threading, time

WIN, MAC = os.name == "nt", sys.platform == "darwin"

TEXTS = {
    "it": {"hint": "↑↓ scegli · Invio conferma · Ctrl+C esci", "hint_resume": "riprende da dove eri",
           "hint_idle": "Ctrl+C esci", "hint_back": "↑↓ scegli · Invio conferma · Esc indietro · Ctrl+C esci", "hint_type": "scrivi · Invio conferma · Ctrl+C esci",
           "hint_read": "↑↓ PgSu PgGiù scorri · Inizio/Fine salta · / cerca · n successiva · Spazio apre/chiude · q chiudi",
           "recommended": "(consigliata)", "type_number": "Scrivi il numero e premi Invio:", "yes": "Sì", "no": "No",
           "done_q": "Fatto?", "retry": "Riprova adesso", "skip": "Salta per ora", "not_yet": "ancora no",
           "ok_count": "{ok}/{tot} a posto", "rerun": "rilancia `{name}`: salta ciò che è già fatto",
           "minutes": "min", "timeout": "tempo scaduto", "would": "farei", "planned": "{n} da fare, niente cambiato (prova)",
           "empty": "niente da mostrare", "rows": "{n} righe", "row": "1 riga", "open_q": "Quale apro?",
           "back": "Indietro", "not_found": "non trovato (un tasto per continuare)",
           "hint_board": "↑↓ muovi · Spazio spunta · a tutte · Invio fatto · q esci",
           "checked": "{n} di {tot} spuntate",
           "settings": "Impostazioni", "settings_q": "Cosa vuoi cambiare?", "setting": "Impostazione", "value": "Valore", "key": "nome",
           "unset": "—", "default": "(predefinito)", "current": "(attuale)", "dash_unset": "- = non impostato",
           "reset": "Rifai da capo", "reset_q": "Tolgo tutte queste impostazioni e rifaccio la preparazione?",
           "reset_yes": "Sì, rifai da capo", "reset_done": "{n} impostazioni tolte",
           "bad_yesno": "rispondi sì o no", "bad_choice": "scegli fra: {options}",
           "bad_number": "serve un numero (0 o più)",
           "unknown_setting": "Impostazione «{key}» sconosciuta. Ci sono: {keys}",
           "settings_cli": "cambiarle: nel menu, oppure `impostazioni NOME VALORE` («-» = predefinito) · file: {path}",
           "phase": "Fase", "now": "Ora", "before": "Prima", "change": "Differenza", "total": "Totale", "done": "fatto", "failed": "non riuscito (codice {code})", "debug": "dettagli: {env}=1", "more_lines": "… altre {n} righe sopra",
           # compact mode (Screen.compact): the same keys in fewer words
           "hint_short": "↑↓ Invio scegli · ^C esci", "hint_back_short": "↑↓ Invio scegli · Esc torna · ^C esci",
           "hint_type_short": "Invio conferma · ^C esci", "hint_read_short": "↑↓ scorri · / cerca · q chiudi",
           "interrupted": "interrotto: `{cmd}` fermato dopo {time} con tutto ciò che aveva avviato",
           "half_done": "può essere rimasto a metà ciò che faceva, l'ultima riga: «{last}»",
           "half_done_quiet": "può essere rimasto a metà ciò che faceva (non aveva scritto niente)",
           "hint_live": "↑↓ PgSu PgGiù scorri · Fine segui · Ctrl+C ferma", "new_below": "↓ {n} righe nuove",
           "new_below_1": "↓ 1 riga nuova", "below": "↓ {n} righe sotto", "below_1": "↓ 1 riga sotto"},
    "en": {"hint": "↑↓ choose · Enter confirm · Ctrl+C quit", "hint_resume": "resumes where you left off",
           "hint_idle": "Ctrl+C quit", "hint_back": "↑↓ choose · Enter confirm · Esc back · Ctrl+C quit", "hint_type": "type · Enter confirm · Ctrl+C quit",
           "hint_read": "↑↓ PgUp PgDn scroll · Home/End jump · / search · n next · Space fold · q close",
           "recommended": "(recommended)", "type_number": "Type the number and press Enter:", "yes": "Yes", "no": "No",
           "done_q": "Done?", "retry": "Try again now", "skip": "Skip for now", "not_yet": "not yet",
           "ok_count": "{ok}/{tot} ok", "rerun": "run `{name}` again: it skips what is already done",
           "minutes": "min", "timeout": "timed out", "would": "would", "planned": "{n} to do, nothing changed (dry run)",
           "empty": "nothing to show", "rows": "{n} rows", "row": "1 row", "open_q": "Which one?",
           "back": "Back", "not_found": "not found (any key to go on)",
           "hint_board": "↑↓ move · Space check · a all · Enter done · q quit",
           "checked": "{n} of {tot} checked",
           "settings": "Settings", "settings_q": "What do you want to change?", "setting": "Setting", "value": "Value", "key": "name",
           "unset": "—", "default": "(default)", "current": "(current)", "dash_unset": "- = not set",
           "reset": "Start over", "reset_q": "Remove all these settings and run the setup again?",
           "reset_yes": "Yes, start over", "reset_done": "{n} settings removed",
           "bad_yesno": "answer yes or no", "bad_choice": "choose among: {options}",
           "bad_number": "a number is needed (0 or more)",
           "unknown_setting": "Unknown setting «{key}». There are: {keys}",
           "settings_cli": "to change them: in the menu, or `settings NAME VALUE` («-» = default) · file: {path}",
           "phase": "Phase", "now": "Now", "before": "Before", "change": "Change", "total": "Total", "done": "done", "failed": "failed (exit code {code})", "debug": "details: {env}=1", "more_lines": "… {n} more lines above",
           "hint_short": "↑↓ Enter choose · ^C quit", "hint_back_short": "↑↓ Enter choose · Esc back · ^C quit",
           "hint_type_short": "Enter confirm · ^C quit", "hint_read_short": "↑↓ scroll · / search · q close",
           "interrupted": "interrupted: `{cmd}` stopped after {time} with everything it had started",
           "half_done": "what it was doing may be left half-done, its last line: «{last}»",
           "half_done_quiet": "what it was doing may be left half-done (it had printed nothing)",
           "hint_live": "↑↓ PgUp PgDn scroll · End follow · Ctrl+C stop", "new_below": "↓ {n} new lines",
           "new_below_1": "↓ 1 new line", "below": "↓ {n} lines below", "below_1": "↓ 1 line below"},
}

# the default logo of the box on top; only blocks every console font has (the classic Windows console too)
LOGO = (" ▄█▄ ", "▀███▀", " ▀█▀ ")

# below this many columns or rows the full screen is compact (Screen.compact): the title on one line instead of the
# box with the logo, the information under it, menu items as «[m] Mie» with their short label, a shorter key line.
# One threshold for all of it (the logo used to go below 60×20); a window that grows again gets the normal view back.
COMPACT = (70, 22)

MOUSE_ON, MOUSE_OFF = "\033[?1000h\033[?1006h", "\033[?1000l\033[?1006l"  # wheel reports (SGR form)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\]8;;[^\x1b]*\x1b\\")


class Label(str):
    """A menu option's text with its short form for the compact menu: Label("Le mie task", "Mie") (a str everywhere
    else, so code that reads the options as text keeps working)."""
    def __new__(cls, text, short=None):
        o = str.__new__(cls, text)
        o.short = short
        return o


class Theme:
    """Colors as SGR codes (e.g. "38;5;153" or "38;2;232;37;63"), the spinner frames and the glyphs."""
    FULL = dict(spinner="✦✧⋆·⋆✧", mark="✦", step="⏺", attach="⎿", arrow="→", prompt="❯", yes="✓", no="✗",
                corners="╭╮╰╯", crumb="›")
    # only characters every console font has (the classic Windows console: Consolas, Lucida Console)
    SAFE = dict(spinner="|/-\\", mark="*", step="●", attach="└", arrow="→", prompt=">", yes="√", no="x", crumb=">",
                corners="┌┐└┘")

    def __init__(self, accent="38;5;153", ok="32", error="31", dim="2", bold="1", glyphs=None, warn="33",
                 select="48;5;237", shortcut=None, **marks):
        """glyphs = "full" or "safe"; default: safe in the classic Windows console (no Windows Terminal),
        PCB_GLYPHS=safe|full to choose. marks = any of spinner, mark, step, attach, arrow, prompt, yes, no, corners."""
        # roles, like Claude Code: one accent for what is interactive or selected; dim for what is secondary
        # (borders, hints, notes); ok/warn/error only for a meaning; select = the background of the selected row;
        # shortcut = the keys of this screen's own operations, a chip in the accent (the generic keys are plain accent)
        self.accent, self.ok, self.error, self.dim, self.bold = accent, ok, error, dim, bold
        self.shortcut = shortcut or f"1;7;{accent}"
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


def duration(seconds):
    """12.3 → "12 s", 125 → "2:05", 0.4 → "0.4 s"."""
    s = round(seconds)
    return f"{seconds:.1f} s" if seconds < 1 else f"{s} s" if s < 60 else f"{s // 60}:{s % 60:02d}"


def change(now, before):
    """"+12%" / "-30%" against the last run; "" when unknown or under a second either way."""
    if not before or abs(now - before) < 1:
        return ""
    return f"{(now - before) / before * 100:+.0f}%"


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
    if WIN or not stdin_tty():
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


def stdin_tty():
    """True when a person can type keys: on Windows isatty() is True for NUL too (a character device), so a
    redirected `< NUL` would hang in getwch(); there only a real console counts."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if not WIN:
        return True
    try:
        import ctypes, msvcrt
        mode = ctypes.c_uint32()
        return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()), ctypes.byref(mode)))
    except (OSError, AttributeError, ValueError):
        return False


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
                if b == b"\x1b[<":  # a mouse event, SGR form: \x1b[<64;x;yM
                    while not b[-1:] in (b"M", b"m") and len(b) < 24:
                        b += os.read(fd, 1)
                    return mouse_key(b)
                if b == b"\x1b[M":  # a mouse event, old form: 3 bytes
                    return mouse_key(b + os.read(fd, 3))
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


def mouse_key(b):
    """A mouse event read by key() → "wheelup", "wheeldown" or "" (clicks are ignored)."""
    if b.startswith(b"\x1b[<"):
        button = b[3:].split(b";")[0]
        button = int(button) if button.isdigit() else -1
    elif b.startswith(b"\x1b[M") and len(b) >= 4:
        button = b[3] - 32
    else:
        return ""
    return {64: "wheelup", 65: "wheeldown"}.get(button & ~0x1c if button >= 0 else -1, "")  # without Shift/Alt/Ctrl


def key_ready(timeout):
    """A key if one is typed within `timeout` seconds, else None — for loops that do something else meanwhile
    (run_live reads the scroll keys while the program runs). Ctrl+C raises as usual."""
    if WIN:
        import msvcrt
        end = time.time() + timeout
        while not msvcrt.kbhit():
            if time.time() >= end:
                return None
            time.sleep(0.01)
        return key()
    import select
    try:
        if not select.select([sys.stdin.fileno()], [], [], timeout)[0]:
            return None
    except (OSError, ValueError):
        return None
    return key()


class LiveView:
    """The lines of a running program as a view that scrolls (no terminal needed: the Screen draws it). At the bottom
    it follows the program and shows the last `keep`; a key up opens it (taller: Screen gives the height) and it stops
    there while new lines arrive (counted in `new`); down to the bottom or End go back to following. At most `limit`
    lines are kept."""
    UP = {"up": 1, "down": -1, "wheelup": 3, "wheeldown": -3}

    def __init__(self, keep=10, limit=500, rules=None):
        self.keep, self.limit, self.rules = keep, max(limit, keep), rules
        self.lines, self.offset, self.new, self.open = [], 0, 0, False  # offset = lines under the view

    def add(self, line):
        self.lines.append(line)
        if self.offset:
            self.offset += 1  # the view stays on the same lines
            self.new += 1
        del self.lines[:-self.limit]

    def key(self, k, height):
        """Moves the view (height = its rows while open); False for a key that isn't a scroll key."""
        page = max(1, height - 1)
        if k == "end":
            self.offset = 0
        elif k == "home":
            self.offset = len(self.lines)
        elif k in self.UP or k in ("pgup", "pgdn"):
            self.offset += self.UP.get(k) or (page if k == "pgup" else -page)
        else:
            return False
        self.open = not (self.offset <= 0 and (k in ("end", "pgdn") or self.UP.get(k, 1) < 0))
        self.clamp(height)
        return True

    def clamp(self, height):
        self.offset = max(0, min(self.offset, len(self.lines) - height))
        self.new = min(self.new, self.offset)

    def window(self, height=None):
        """The lines in view: the last `keep` when following, `height` rows when open."""
        height = height if self.open and height else self.keep
        self.clamp(height)
        end = len(self.lines) - self.offset
        return self.lines[max(0, end - height):end]


# Colors by meaning for the output of programs: (regex, Theme role) rules, the first one wins. role_of() gives a whole
# line the role of the first rule that matches it; Screen.highlight() colors only what each rule catches. File names
# come before words: a match that cuts a file name doesn't count, so "errorHandler.cpp" or "error.log" are not errors
# (a rule may still catch a whole file name). A regex may be a string or compiled.
RULES = [(re.compile(r"(?i)\b(error|errore|errors|failed|failure|fatal|exception|traceback|denied|panic|conflict)\b"), "error"),
         (re.compile(r"(?i)\b(warn|warning|warnings|attenzione|avviso|deprecated|skipped)\b"), "warn"),
         (re.compile(r"(?i)\b(ok|done|success|successful|passed|completed|completato|fatto|riuscito)\b"), "ok")]
FILE_NAME = re.compile(r"[\w.~/\\-]*\w\.[A-Za-z][A-Za-z0-9]{0,5}\b")


def _rules(rules):
    return [(re.compile(rx) if isinstance(rx, str) else rx, role) for rx, role in rules]


# ready-made rules for the output of some common programs (screen.highlight(text, GIT_RULES), run_live(rules=…))
SVN_RULES = _rules([
    (r"^svn: E\d+:.*", "error"),
    (r"^svn: warning: W\d+:.*", "warn"),
    (r"^(?:Conflict discovered in|Tree conflict on|Summary of conflicts:|\s+(?:Text|Property|Tree) conflicts: \d+).*",
     "error"),
    (r"^ {0,6}C(?= )", "error"),  # the conflict letter: content (1st column), properties (2nd), tree (7th)
    (r"^[!~](?= )", "warn"),  # missing, obstructed
    (r"^D(?= )", "warn"),
    (r"^A(?= )", "ok"),
    (r"^\?(?= )", "dim"),
    (r"^(?:Updated to|At|Committed|Checked out) revision \d+\.", "ok")])
GIT_RULES = _rules([
    (r"^(?:fatal|error):.*", "error"),
    (r"^CONFLICT \(.*", "error"),
    (r"^Automatic merge failed.*", "error"),
    (r"^ ! \[(?:remote )?rejected\].*", "error"),
    (r"^\s+both (?:modified|added|deleted):.*", "error"),
    (r"^(?:UU|AA|DD|AU|UA|UD|DU)(?= )", "error"),
    (r"^warning:", "warn"),
    (r"^hint:.*", "dim"),
    (r"^(?:Already up to date\.|Fast-forward|Switched to (?:a new )?branch .*|Successfully rebased.*)$", "ok")])
MSBUILD_RULES = _rules([
    (r"\b(?:fatal )?(?:error|errore) [A-Z]{1,4}\d{3,5}\b", "error"),
    (r"\b(?:warning|avviso) [A-Z]{1,4}\d{3,5}\b", "warn"),
    (r"^(?:Build FAILED\.|Compilazione NON riuscita\.)", "error"),
    (r"(?<!\S)[1-9]\d* (?:Error\(s\)|errori)$", "error"),
    (r"(?<!\S)[1-9]\d* (?:Warning\(s\)|avvisi)$", "warn"),
    (r"^(?:Build succeeded\.|Compilazione completata\.)", "ok"),
    (r"\[[^\[\]]+\.\w*proj\]$", "dim"),  # the project at the end of each line
    (r"^\s*(?:Time Elapsed|Tempo trascorso) .*", "dim")])


def _found(text, rx, names):
    """The matches of rx in text that don't cut a file name (names = their spans)."""
    pos = 0
    while pos <= len(text):
        m = rx.search(text, pos)
        if not m:
            return
        a, b = m.span()
        pos = b if b > a else b + 1
        if a == b:
            continue
        if any(a < e and b > s and not (a <= s and b >= e) for s, e in names):
            pos = a + 1  # inside a file name: look further on
            continue
        yield a, b


def spans(line, rules=None):
    """[(start, end, role)] of a line (without color codes): what each rule catches; where two overlap, the first
    rule wins."""
    names = [m.span() for m in FILE_NAME.finditer(line)]
    taken = []
    for rx, role in _rules(RULES if rules is None else rules):
        taken += [(a, b, role) for a, b in _found(line, rx, names)
                  if not any(a < e and b > s for s, e, _ in taken)]
    return sorted(taken)


def role_of(line, rules=None):
    """The Theme role of a line of output ("error", "warn", "ok", …) or None: the first rule that matches it."""
    text = ANSI.sub("", line)
    names = [m.span() for m in FILE_NAME.finditer(text)]
    for rx, role in _rules(RULES if rules is None else rules):
        if next(_found(text, rx, names), None):
            return role
    return None


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
        # PCB_COLORS=1: colors also into a pipe (the contract tests check them); full screen still needs a terminal
        self.colors = bool(os.environ.get("PCB_COLORS")) or (
            sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb")
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
        self.results, self.no_input, self.dry, self.read_only, self.json = [], False, False, False, False
        self.timings = {}  # phase → seconds in this command (run_steps, steps.phase)
        self.rules, self.live_n, self.view, self.scrolling = RULES, 0, None, False  # see live()
        self.outcome = False  # the command has said how it ended (done(), summary()): App.call adds one otherwise  # colors by meaning of output(); live lines now at the end of the body
        self.focus, self.over, self.stay = None, False, False  # see visible(), out() and App.menu
        self.logo, self.about, self.rows, self.subtitle = LOGO, None, [], ""  # the box on top: header(), banner()
        self.narrow, self.picking = False, None  # compact at the last layout; the open menu's rows (redrawn)
        self.full = self.colors and stdin_tty() and sys.stdout.isatty() and not os.environ.get(plain_env)
        self.refresh, self.mode = False, "idle"  # mode: idle, choose, type, read — the hint follows it
        self.suspended = False
        self.head, self.body, self.foot, self.last = [], [], "", []
        self.opened, self.lock, self.size, self.attached, self.width = False, threading.RLock(), None, False, 0

    @property
    def full(self):
        """Full screen: never with --json, even when a tool sets screen.json itself (stdout is only for the data)."""
        return self._full and not self.json

    @full.setter
    def full(self, on):
        self._full = on

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
        sys.stdout.write(MOUSE_OFF + "\033[?25h\033[?1049l")
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
            sys.stdout.write(MOUSE_OFF + "\033[?25h\033[?1049l")
            sys.stdout.flush()

    def resume(self):
        self.suspended = False
        if self.opened and CBREAK["depth"] and not WIN and stdin_tty():
            import tty
            tty.setcbreak(sys.stdin.fileno())
        if self.opened:
            sys.stdout.write("\033[?1049h\033[?25l" + (MOUSE_ON if self.scrolling and self.mouse() else ""))
            self.size = None
            self.draw()

    def out(self, line=""):
        line = mask(line)
        if not self.full:
            print(line, file=sys.stderr if self.json else sys.stdout)  # --json: stdout only for the data
            return
        self.open()
        self.stay = False
        with self.lock:
            if self.over:  # the first thing an action of a full view says replaces that view
                self.body, self.over = [], False
            self.body += line.split("\n")
            del self.body[:-500]
            self.live_n, self.view = 0, None
        self.draw()

    def paint(self, line):
        """A line of a program's output in the color of its meaning (self.rules); as it is without one."""
        role = role_of(line, self.rules)
        return self.c(getattr(self.theme, role), line) if role else line

    def highlight(self, text, rules=None):
        """The text with only what each rule catches colored (rules = [(regex, Theme role)], the first wins; default
        self.rules); file names come before words. Without colors (a pipe, a log) the text as it is."""
        out = []
        for line in ANSI.sub("", str(text)).split("\n"):
            if not self.colors:
                out.append(line)
                continue
            parts, pos = [], 0
            for a, b, role in spans(line, self.rules if rules is None else rules):
                code = getattr(self.theme, role, None)
                parts += [line[pos:a], self.c(code, line[a:b]) if code else line[a:b]]
                pos = b
            out.append("".join(parts) + line[pos:])
        return "\n".join(out)

    def output(self, text, rules=None):
        """What a program printed, line by line, each colored by its meaning (files and logs stay plain); with
        rules, only what they catch (highlight())."""
        for r in str(text).split("\n"):
            self.out("    " + (self.paint(r) if rules is None else self.highlight(r, rules)) if r.strip() else "")

    def live(self, line, keep=10, rules=None, limit=500, draw=True):
        """A line of a program while it runs: in full screen it scrolls under the current step, colored by its
        meaning (with rules: only what they catch), and only the last `keep` stay in view; up to `limit` are kept to
        scroll back to (live_scroll). Returns False (nothing shown) elsewhere, where the output comes back to the
        caller at the end. draw=False: the caller draws once for many lines."""
        if not self.full or keep <= 0:
            return False
        self.open()
        with self.lock:
            if self.view is None:
                self.view = LiveView(keep, limit, rules)
            self.view.add(line)
            self._live_render()
        if draw:
            self.draw()
        return True

    def live_scroll(self, on):
        """While a program runs (run_live): its lines scroll with ↑↓ PgUp PgDn Home End and the wheel, the keys
        written under them. Wheel: the terminal reports it (mouse mode) on Mac and Linux; PCB_MOUSE=0 leaves the
        mouse to the terminal (selecting text). Off: back to following, the keys line goes away."""
        if not self.opened:
            return
        self.scrolling = on
        if self.mouse() and not self.suspended:
            sys.stdout.write(MOUSE_ON if on else MOUSE_OFF)
        with self.lock:
            if self.view:
                if not on:
                    self.view.offset, self.view.new, self.view.open = 0, 0, False
                self._live_render()
        self.draw()

    @staticmethod
    def mouse():
        """The wheel is asked to the terminal (mouse reports): Mac and Linux, unless PCB_MOUSE=0."""
        return not WIN and os.environ.get("PCB_MOUSE", "1") != "0"

    def live_key(self, k):
        """A key while a program runs: True when it moved its lines."""
        with self.lock:
            if not self.view or not self.view.key(k, self._live_room()):
                return False
            self._live_render()
        self.draw()
        return True

    def _live_room(self):
        """Rows for the lines of the program while you read back: the window under the box, minus the separator,
        the keys line, its own status line and the step line above."""
        w, h = shutil.get_terminal_size((80, 24))
        head = self.banner(w, h)
        return max(self.view.keep if self.view else 1, h - (len(head) if h >= len(head) + 8 else 0) - 4)

    def _live_render(self):
        v = self.view
        lines = [self.dim("  " + self.theme.attach + " ") + (self.paint(r) if v.rules is None else self.highlight(r, v.rules))
                 for r in v.window(self._live_room())]
        if self.scrolling:
            hint = self.keys(pairs(self.t["hint_live"]))
            if v.offset:
                which = ("new_below" if v.new else "below") + ("_1" if (v.new or v.offset) == 1 else "")
                hint = self.acc(self.t[which].format(n=v.new or v.offset)) + self.dim(" · ") + hint
            lines.append("    " + hint)
        start = len(self.body) - self.live_n
        self.body[start:] = lines
        self.live_n = len(lines)

    def draw(self):
        if not self.opened or self.suspended:
            return
        with self.lock:
            self.size = shutil.get_terminal_size((80, 24))
            sys.stdout.write("\033[H" + "\r\n".join(r + "\033[K" for r in self.layout(*self.size)) + "\033[J")
            sys.stdout.flush()

    @staticmethod
    def compact(w=None, h=None):
        """True below COMPACT (70 columns or 22 rows): the window of `w`×`h`, by default the terminal's."""
        if w is None or h is None:
            size = shutil.get_terminal_size((80, 24))
            w, h = size.columns if w is None else w, size.lines if h is None else h
        return w < COMPACT[0] or h < COMPACT[1]

    def layout(self, w, h):
        """The lines of a full screen: the box, the content, then the separator and the bottom line right under the
        content, like Claude Code: what you type, the keys and the wait line follow the text instead of staying at
        the bottom of the window, and go down only when the content fills it. Below COMPACT the compact view, decided
        again at every draw (a resize switches it either way)."""
        self.narrow = self.compact(w, h)
        if self.picking:  # the open menu's rows follow the mode: «[m] Mie» compact, the full text otherwise
            first, render = self.picking
            rows = render()
            self.body[first:first + len(rows)] = rows
        head = self.banner(w, h)
        head = ([clip(r, w) for r in head] if h >= len(head) + 8 else
                [clip(head[0], w)] if head and self.narrow and h >= 9 else [])
        foot = [self.c(self.theme.dim, "─" * w), clip(self.foot or "  " + self.hint_line(), w)]
        room = max(1, h - len(head) - len(foot))
        return (head + [clip(r, w) for r in self.visible(room)] + foot)[:h]

    def banner(self, w, h):
        """The box on top, always fixed: the logo beside the information when the window has room for it. Compact
        (below COMPACT): no box, the title on one line and the information (the tool's notices) right under it."""
        if self.head and self.rows and self.compact(w, h):
            sub = self.subtitle
            return [self.rows[0] + (self.dim(" · " + sub) if sub else "")] + self.rows[1 + bool(sub):]
        if not self.head or not self.logo or not self.rows:
            return self.head
        wide = max(visible_len(r) for r in self.logo)
        logo = [self.acc(r.ljust(wide)) if "\033" not in r else r + " " * (wide - visible_len(r)) for r in self.logo]
        rows = [(logo[i] if i < len(logo) else " " * wide) + "  " + (self.rows[i] if i < len(self.rows) else "")
                for i in range(max(len(logo), len(self.rows)))]
        return self.frame(rows)

    def visible(self, room):
        """The lines that fit: the last ones; during a question (focus = its line, the selected line) the question
        stays on top and the selected row stays in view, however low the window."""
        if not self.focus or len(self.body) <= room:
            return self.body[-room:]
        q, sel = self.focus
        top = q if sel - q < room else sel - room + 2
        return self.body[top:top + room] if top == q else [self.body[q]] + self.body[top:sel + 1]

    def fresh(self, crumbs=(), note=""):
        """In a menu or a screen that loops, the next question replaces the previous one instead of piling up: the
        box stays on top, under it where you are («Settings › Style») and the outcome of the last action. Without
        a real terminal only the note is said (the questions stay one under the other)."""
        if not self.full:
            if note:
                self.info(note)
            return
        self.clear()
        if crumbs:
            self.out("  " + self.dim(f" {self.theme.crumb} ".join(crumbs)))
        if note:
            self.out("    " + note)

    def clear(self):
        if self.full:
            with self.lock:
                self.body, self.live_n, self.view = [], 0, None
            self.draw()
        elif self.colors:
            sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()

    def hint(self):
        """Only the keys that work now (owner: «arrows» shown with nothing to choose was a bug), plus the open
        menu-session accesses («VPN aperta da 4 min»)."""
        from .access import status_line
        h = self._hint_text()
        st = status_line()
        return h + (f" · {st}" if st else "")

    def _hint_text(self):
        """The keys of this moment; in compact mode their short form (the same keys, fewer words)."""
        k = {"choose": "hint", "back": "hint_back", "type": "hint_type", "read": "hint_read"}.get(self.mode, "hint_idle")
        return self.t.get(k + "_short", self.t.get(k, "")) if self.narrow else self.t.get(k, "")

    def keys(self, items, context=False):
        """[(keys, what they do)] → «↑↓ scegli · Invio conferma»: keys in the accent, bold; what they do, muted.
        context=True: the keys of this screen's own operations, each a chip (theme.shortcut) so they stand out."""
        sep = self.dim(" · ")
        key = (lambda k: self.c(self.theme.shortcut, f" {k} ")) if context else (lambda k: self.c(f"{self.theme.accent};1", k))
        return sep.join((key(k) if k else "") + self.dim((" " if k else "") + label) for k, label in items)

    def shortcut_line(self, nav, actions):
        """The bottom line of a screen with its own operations: first those (chips), then the generic keys `nav`.
        actions = {key: (label, …)}."""
        ctx = self.keys([(k, a[0]) for k, a in actions.items()], context=True)
        return "  " + (ctx + self.dim(" · ") if ctx else "") + self.keys(pairs(nav))

    def hint_line(self):
        """The bottom line: the keys of this moment, then the open accesses (muted)."""
        from .access import status_line
        h = self._hint_text()
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
        """The opening box, like Claude Code's: fixed at the top for the whole session. logo = a few rows of blocks
        (App(banner=…)), about() = more lines of information (App(banner_info=…)); no logo in a narrow or low window."""
        lines = [self.acc(self.theme.mark + " ") + self.bold(self.title) + self.dim(f"  {self.name}")]
        self.subtitle = subtitle
        if subtitle:
            lines.append("  " + subtitle)
        try:
            lines += ["  " + str(r) for r in (self.about() if self.about else [])]
        except Exception:  # the tool's own line about itself must never stop the tool
            pass
        self.rows = lines
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
        count = f"  {n}/{total}" if total else ""  # total 0: steps not known in advance (steps.phase)
        self.out(self.acc(self.theme.step) + " " + self.bold(text) + self.dim(count + (f" · {why}" if why else "")))
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

    def action(self, fn, label, *args):
        """Runs a one-key action of a full view: it may ask (`choose`, `confirm`, `ask`) and wait (`wait`) — what it
        says replaces the view until it ends, then the view comes back. Returns the message; one that fails says why."""
        self.over = True
        try:
            return fn(*args) or label
        except Exception as e:  # the view stays open
            return f"{label}: {e}"
        finally:
            self.over = False

    def detail(self, d):
        """A Detail (pleiadi_cli_builder.detail): JSON with --json, plain text without a real terminal, otherwise
        the scrolling view until q/Esc/Enter."""
        from .detail import Pager
        if self.data(d.as_dict()):
            return
        size = shutil.get_terminal_size((80, 24))
        pager = Pager(d, min(size.columns - 1, 100) if not self.full else size.columns, size.lines - 2, self.c,
                      mark=self.theme.accent)
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
                self.foot = self.foot or self.shortcut_line(pager.nav(), d.actions)
                self.draw()
                what = pager.handle(key())
                self.foot = ""
                if isinstance(what, tuple):  # a one-key action: its message stays until the next key
                    label, fn = d.actions[what[1]]
                    msg = self.action(fn, label, self)
                    self.mode = "read"
                    self.foot = "  " + self.acc(self.theme.arrow + " ") + str(msg)
                    continue
                if what == "quit":
                    break
                if what == "search":
                    self.mode = "type"
                    q = self._type_line("/")
                    self.mode = "read"
                    if not q:  # an empty search ends the search: n/N back on the new lines
                        pager.search("")
                    elif not pager.search(q):
                        self.foot = self.dim(f"  «{q}»: {self.t['not_found']}")
                        self.draw()
                        key()
                        self.foot = ""
        finally:
            with self.lock:
                self.head, self.body = saved
            self.mode, self.stay = "idle", True  # closing it was the answer: no «press Enter» after
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

        acting = threading.Event()

        def paint():  # also from the background cells, as each one arrives
            if acting.is_set():
                return
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
                self.foot = self.foot or self.shortcut_line(view.nav(), b.actions)
                paint()
                k = key()
                self.foot = ""
                with self.lock:
                    what = view.handle(k)
                if isinstance(what, tuple):
                    rows = view.targets()
                    label, fn = b.actions[what[1]]
                    acting.set()  # the cells filling in the background must not draw over its question
                    try:
                        msg = self.action(fn, label, self, rows)
                    finally:
                        acting.clear()
                    self.mode = "read"
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
            self.mode, self.stay = "idle", True
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
        return stdin_tty() and not self.no_input

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
            took = f" · {duration(r.seconds)}" if getattr(r, "seconds", None) and r.seconds >= 1 else ""
            self.out(self._indent() + self.c(th.ok, th.yes) + f" {r.name}" + (self.dim(f" · {r.note}") if r.note else "")
                     + self.dim(took))
        else:
            self.out(self._indent() + self.c(th.error, th.no) + f" {r.name}")
            if r.fix:
                self.todo(r.fix)
            tries = 0  # never forever: at most 3, and none if nobody answers
            while (r.retry and stdin_tty() and not self.no_input and tries < 3
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

    def timing_table(self, before=None):
        """Every phase of this command with its time and, when known, the last run's and the change."""
        before = before or {}
        rows = [{"phase": k, "now": duration(v), "before": duration(before[k]) if k in before else "—",
                 "change": change(v, before.get(k))} for k, v in self.timings.items()]
        if len(rows) > 1:
            now, old = sum(self.timings.values()), [before.get(k) for k in self.timings]
            rows.append({"phase": self.t["total"], "now": duration(now),
                         "before": duration(sum(old)) if None not in old else "—",
                         "change": change(now, sum(old) if None not in old else None)})
        self.table(rows, ["phase", "now", "before", "change"], {k: self.t[k] for k in ("phase", "now", "before", "change")})

    def summary(self, minutes=None):
        """The closing box: n/total ok and what is still ✗; it stays on screen after exit. Returns True when nothing
        is ✗."""
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
        self.outcome = True
        # True when nothing is ✗: a dry run with steps still to do is not a failure (its exit code stays 0)
        return all(r.ok or r.skipped or r.planned for r in self.results)

    def done(self, text, ok=True):
        """How the command ended, the last line: ✓ in green or ✗ in red, and what."""
        th = self.theme
        self.out("")
        self.out(self.c(th.ok, th.yes) + " " + text if ok else self.c(th.error, th.no) + " " + text)
        self.outcome = True

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

    def choose(self, question, options, header=None, keys=None, start=0, esc=None, short=None):
        """options = [text]; the first is the recommended one. Returns the index. Arrows + Enter (or the number);
        without a real terminal: type the number. header = column titles shown above the options (a table).
        keys = one letter per option (None: none): shown as a chip on its row, that letter picks it at once.
        start = the option the cursor starts on (coming back from where you went in).
        esc = the option Esc picks (the «Back» or «Quit» one): the same key goes back everywhere.
        short = a short label per option, shown instead of the text in compact mode (Screen.compact); an option
        can also carry its own (Label)."""
        keys = list(keys or [])
        short = list(short) if short else [getattr(o, "short", None) for o in options]
        self.out("")
        self.out("  " + self.acc("?") + " " + self.bold(question))
        asked = len(self.body) - 1
        if header:
            self.out(self._menu_header(header, len(options)))
        if self.colors and stdin_tty():
            try:
                return self._menu(options, recommend=not header, keys=keys, start=start, asked=asked, esc=esc,
                                  short=short)
            except (OSError, ImportError):
                pass  # no single keys (odd console): fall back to the number
        for i, o in enumerate(options):
            self.out(self._menu_row(i, o, None, len(options), "" if header else "  " + self.t["recommended"],
                                    keys[i] if i < len(keys) else None))
        while True:
            r = self.ask(self.t["type_number"], "1")
            if r.isdigit() and 1 <= int(r) <= len(options):
                return int(r) - 1
            if r and r.lower() in keys:
                return keys.index(r.lower())

    def confirm(self, question, yes=None, no=None):
        return self.choose(question, [yes or self.t["yes"], no or self.t["no"]]) == 0

    def _menu_row(self, i, o, sel, n, rec, key=None):
        """One option, its number right-aligned (1..n) so that texts start in the same column as the header. The
        selected one is a bar across the width (accent on a dark background), like Claude Code's. key = its
        shortcut letter, a chip after the text (also inside the bar). Compact mode (self.narrow): an option with a
        letter is «[m] Mie», the letter in front and no number (the digits still pick it)."""
        if self.narrow and key:
            return self._compact_row(i, o, sel, key)
        nw = len(str(n))
        chip = self.c(self.theme.shortcut, f" {key} ") if key else ""
        w = self.text_width() - 6 - nw - (len(key) + 4 if key else 0)
        o = o if len(o) <= w else o[:w - 1] + "…"  # one line per option, even on a narrow screen
        has_note = rec and i == 0 and len(o) + len(rec) + 1 <= w
        num = f"{i + 1:>{nw}}."
        if i == sel:
            bar_style = f"{self.theme.accent};1;{self.theme.select}"
            bar = f"  {self.theme.prompt} {num} {o}" + (rec if has_note else "")
            if not key:
                return self.c(bar_style, bar.ljust(self.text_width()))
            rest = max(0, self.text_width() - len(bar) - len(key) - 4)
            return self.c(bar_style, bar + "  ") + chip + self.c(bar_style, " " * rest)
        return self.dim(f"    {num} ") + o + (self.dim(rec) if has_note else "") + ("  " + chip if key else "")

    def _compact_row(self, i, o, sel, key):
        full = max(20, min(shutil.get_terminal_size((80, 24)).columns - 1, 100))  # text_width() stops at 40
        w = full - 8 - len(key)
        o = o if len(o) <= w else o[:w - 1] + "…"
        if i == sel:
            return self.c(f"{self.theme.accent};1;{self.theme.select}", f"  {self.theme.prompt} [{key}] {o}".ljust(full))
        return "    " + self.dim("[") + self.c(f"{self.theme.accent};1", key) + self.dim("]") + " " + o

    def _menu_header(self, header, n):
        pad = " " * (4 + len(str(n)) + 2)
        return pad + self.bold(header) + "\n" + pad + self.dim("─" * visible_len(header))

    def _menu(self, options, recommend=True, keys=(), start=0, asked=0, esc=None, short=None):
        rec = "  " + self.t["recommended"] if recommend else ""
        letter = {k: i for i, k in enumerate(keys) if k}
        label = lambda i, o: short[i] if self.narrow and short and i < len(short) and short[i] else o
        row = lambda i, o: self._menu_row(i, label(i, o), sel, n, rec, keys[i] if i < len(keys) else None)
        sel, n = min(max(0, start), len(options) - 1), len(options)
        self.mode = "choose" if esc is None else "back"

        def move(k):
            return ((sel - 1) % n if k == "up" else (sel + 1) % n if k == "down" else
                    int(k) - 1 if k.isdigit() and 1 <= int(k) <= n else sel)
        if self.full:  # the options stay in place; afterwards one line with the answer
            with self.lock:
                first = len(self.body)
                self.body += [row(i, o) for i, o in enumerate(options)]
                self.focus = (asked, first + sel)
                self.picking = (first, lambda: [row(i, o) for i, o in enumerate(options)])  # redrawn on a resize
            self.draw()
            try:
                while True:
                    k = key()
                    if k == "enter":
                        break
                    if k in letter:  # a shortcut: picked at once
                        sel = letter[k]
                        break
                    if k == "esc" and esc is not None:
                        sel = esc
                        break
                    sel = move(k)
                    with self.lock:
                        self.body[first:first + n] = [row(i, o) for i, o in enumerate(options)]
                        self.focus = (asked, first + sel)
                    self.draw()
            finally:
                with self.lock:
                    self.picking = None
            with self.lock:
                self.body[first:] = ["    " + self.acc(self.theme.prompt + " ") + options[sel]]
                self.focus = None
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
                if k in letter:
                    return letter[k]
                if k == "esc" and esc is not None:
                    return esc
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
