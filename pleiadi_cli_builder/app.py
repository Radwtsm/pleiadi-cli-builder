"""An App = name + look + commands. No arguments: the interactive menu (or the first-run command); `help`: the
usage generated from the commands; state kept per computer in ~/.config/<name>/state.json (never secrets)."""
import json, os, re, sys, textwrap, time

from . import access, proc
from .term import MAC, WIN, Label, Screen, Theme, stdin_tty

HELP = {"it": ("comandi", "senza argomenti: il menu", "Cosa vuoi fare?", "Esci", "Invio per tornare al menu",
               "comando sconosciuto", "solo lettura", "--prova", "istantanea del {when} · --aggiorna per riscaricarla"),
        "en": ("commands", "no arguments: the menu", "What do you want to do?", "Quit", "Enter to go back to the menu",
               "unknown command", "read-only", "--dry-run", "snapshot of {when} · --refresh to download it again")}
DRY_FLAGS = ("--prova", "--dry-run")
REFRESH_FLAGS = ("--aggiorna", "--refresh")
NOTES = {"it": {"first": "Primo download: ci vuole di più (minuti, se i dati sono tanti); poi i comandi leggono la copia "
                         "locale e rispondono subito. --aggiorna riscarica.",
                "again": "Riscarico i dati.", "last": "l'ultima volta: {m}",
                "memory": "Copia locale disattivata: i dati restano solo in memoria, ogni avvio riscarica tutto.",
                "done": "scaricati {n} elementi in {m}, da ora la copia locale.",
                "done_memory": "scaricati {n} elementi in {m}.",
                "cooldown": "Dati scaricati {ago} fa: si riscaricano al massimo ogni {limit} min, uso questi."},
         "en": {"first": "First download: it takes longer (minutes, with a lot of data); then commands read the local copy "
                         "and answer at once. --refresh downloads again.",
                "again": "Downloading the data again.", "last": "last time: {m}",
                "memory": "Local copy off: data stays in memory only, every start downloads everything.",
                "done": "downloaded {n} items in {m}, from now on the local copy.",
                "done_memory": "downloaded {n} items in {m}.",
                "cooldown": "Data downloaded {ago} ago: refreshed at most every {limit} min, using it."}}


def _minutes(sec):
    return f"{sec / 60:.0f} min" if sec >= 90 else f"{sec:.0f} s"


def _count(data):
    if isinstance(data, dict):
        return sum(len(v) for v in data.values() if isinstance(v, list)) or len(data)
    return len(data) if isinstance(data, list) else 1
JSON_FLAG = "--json"


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(path + ".tmp", path)  # never a half-written file


class Command:
    def __init__(self, name, fn, help="", menu=None, args="", effects=True, json=False, example=(), dry=True, key=None,
                 short=None):
        self.name, self.fn, self.help, self.menu, self.args, self.effects = name, fn, help, menu, args, effects
        self.key, self.short = key, short
        self.json, self.example, self.dry = json, list(example), dry and effects


class App:
    """
        app = App("deploy-kit", title="Deploy kit", accent="#4a6cf7")

        @app.command("check", help="what is ok and what is missing", menu="Check everything")
        def check(screen, args): ...

        app.main()
    """
    def __init__(self, name, title="", accent=None, theme=None, lang="it", first_run=None, menu_subtitle="",
                 write_commands=(), session_idle_minutes=5, banner=None, banner_info=None, timings=False):
        """write_commands = the programs that change something, as the start of their command line
        (e.g. [["git", "push"], ["rm"]]): run() refuses them inside read-only commands and dry runs.
        session_idle_minutes = in the interactive menu, an access (VPN) stays open between actions and closes
        after this many minutes without actions (always on exit).
        banner = the logo in the box on top, a few rows of blocks (colored with the accent unless they already have
        their colors; None: the library's; (): none); banner_info() → more lines beside it: version, folder, context.
        timings = after a command with timed phases (run_steps, steps.phase) a table of every phase now, in the last
        run of the same command and the change; the times are kept in the state."""
        self.timings = timings
        self.banner, self.banner_info = banner, banner_info
        self.session_idle_minutes, self._memory = session_idle_minutes, {}
        self.sections, self.prog, self.renamed = {}, name, {}  # prog/renamed: how the host calls this App
        self.name, self.title, self.lang = name, title or name, lang
        self.crumbs = [self.title]  # where a screen is: «Tool › Section › Action» (include() extends it)
        self.write_commands = [list(w) for w in write_commands]
        self.theme = theme or Theme(**({"accent": Theme.rgb(accent) if accent.startswith("#") else accent} if accent else {}))
        self.commands, self.first_run, self.menu_subtitle = {}, first_run, menu_subtitle
        self.state_path = os.path.join(os.path.expanduser("~"), ".config", name, "state.json")
        home = os.path.expanduser("~")
        base = (os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")) if WIN else \
            os.path.join(home, "Library", "Caches") if MAC else os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache")
        self.cache_dir = os.path.join(base, name, "snapshots")

    # ── state ──
    def state(self):
        return read_json(self.state_path, {}) or {}

    def save_state(self, **kv):
        s = self.state()
        s.update(kv)
        write_json(self.state_path, s)

    def config(self, path, default=None):
        """A tool's or project's configuration: JSON only, so a file someone else provides stays data and never
        runs as code. Missing file → default; anything that isn't JSON → ValueError."""
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            raise ValueError(f"{path}: not valid JSON (configuration is data, never code)") from None

    # ── snapshots ──
    def _snap_path(self, name):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError(f"snapshot name {name!r}: letters, digits, - and _ only")
        return os.path.join(self.cache_dir, name + ".json")

    def snapshot(self, name, fetch, refresh=False, keep=True, screen=None, min_refresh_minutes=0):
        """(data, "YYYY-MM-DD HH:MM"): data fetched once (e.g. while temporary() keeps a VPN open), then read back
        until refresh=True (--aggiorna/--refresh sets screen.refresh). keep=True: a copy in the user's cache,
        readable by that user only, kept between runs; keep=False: in memory for this run only, nothing on disk.
        With `screen`: before a download a line says how long it may take (and how long it took last time),
        after it how many items came. It is a copy of the data: for data under a company's policy, check it.
        min_refresh_minutes: a refresh asked sooner than this after the last download uses the copy and says so
        (repeated --aggiorna don't hammer the server)."""
        path, n = self._snap_path(name), NOTES.get(self.lang, NOTES["en"])
        old = read_json(path) if keep else self._memory.get(name)  # keep=True: the disk copy is the truth
        if isinstance(old, dict) and "taken" in old:
            ago = time.time() - old.get("at", 0)
            if not refresh:
                return old.get("data"), old["taken"]
            if ago < min_refresh_minutes * 60:
                if screen:
                    screen.info(n["cooldown"].format(ago=_minutes(ago), limit=min_refresh_minutes))
                return old.get("data"), old["taken"]
        if screen:
            lines = [n["again"] if old else n["first"] if keep else ""] + ([] if keep else [n["memory"]])
            if isinstance(old, dict) and "seconds" in old:
                lines.append(n["last"].format(m=_minutes(old["seconds"])))
            screen.info(" ".join(x for x in lines if x))
        start = time.time()
        data, taken = fetch(), time.strftime("%Y-%m-%d %H:%M")
        snap = {"taken": taken, "at": time.time(), "seconds": round(time.time() - start, 1), "data": data}
        if screen:
            screen.info(n["done" if keep else "done_memory"].format(n=_count(data), m=_minutes(snap["seconds"])))
        if not keep:
            self._memory[name] = snap
            return data, taken
        self._memory.pop(name, None)
        os.makedirs(self.cache_dir, exist_ok=True)
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # created private, not chmod later
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        return data, taken

    def snapshot_info(self, name):
        """(path, bytes, taken) of the local copy, or None (no copy on disk)."""
        path = self._snap_path(name)
        old = read_json(path)
        if not isinstance(old, dict):
            return None
        return path, os.path.getsize(path), old.get("taken", "")

    def forget_snapshot(self, name):
        """Deletes the local copy (and the in-memory one): True if there was one."""
        path, had = self._snap_path(name), self._memory.pop(name, None) is not None
        if os.path.exists(path):
            os.remove(path)
            return True
        return had

    def snapshot_note(self, when):
        return HELP.get(self.lang, HELP["en"])[8].format(when=when)

    # ── commands ──
    def include(self, other, name, title=None, rename=None):
        """Another App as a section of this one: `tool NAME COMMAND`, a sub-menu in the menu, its commands in help.
        rename = {its command: name here} (e.g. setup → configure, so they don't clash with this tool's). Its
        snapshots and state stay its own (other.cache_dir, other.state_path): set them if the host wants them."""
        other.prog, other.renamed, other.section_title = f"{self.prog} {name}", dict(rename or {}), title or name
        other.crumbs = self.crumbs + [other.section_title]
        self.sections[name] = other
        return other

    def cmd(self, command):
        """How the person types `command` here: "tool task configure" inside a host, "tracker setup" alone —
        for messages like «first run `…`»."""
        return f"{self.prog} {self.renamed.get(command, command)}"

    def local(self, typed):
        """The Command the person typed (a renamed one by its new name), or None."""
        back = {v: k for k, v in self.renamed.items()}
        if typed in self.renamed:  # renamed away: the old name no longer exists here
            return None
        return self.commands.get(back.get(typed, typed))

    def command(self, name, help="", menu=None, args="", effects=True, json=False, example=(), dry=True, key=None,
                short=None):
        """menu = the text in the interactive menu (None = not in the menu); args = usage shown in help.
        effects=False declares a read-only command: its steps can only check (enforced in run_steps). A command
        with effects gets --prova/--dry-run: screen.dry is True and run_steps only says what it would do.
        json=True: the command prints its data with screen.table and supports --json; example = sample arguments
        for the contract tests (pleiadi_cli_builder.contract). dry=False: no --prova here (the command forwards to a
        program with its own dry run): the flag is passed through untouched. key = its letter in the menu (a
        shortcut: picks it at once); without one it gets the first free letter of its menu text. short = its label in
        the compact menu (a narrow or low window, term.COMPACT), one or two words: «Mie» for «Le mie task»."""
        def add(fn):
            self.commands[name] = Command(name, fn, help, menu, args, effects, json, example, dry, key, short)
            return fn
        return add

    def screen(self):
        s = Screen(self.name, self.title, self.theme, self.lang)
        s.about = self.banner_info
        if self.banner is not None:
            s.logo = self.banner
        return s

    def _rows(self):
        t = HELP.get(self.lang, HELP["en"])
        rows = [(self.cmd(c.name) + (f" {c.args}" if c.args else "") + (f" [{t[7]}]" if c.dry else ""),
                 c.help + (f" ({t[6]})" if not c.effects else "")) for c in self.commands.values()]
        for name, sub in self.sections.items():
            rows.append(("", ""))
            rows.append((f"{self.prog} {name} …", sub.section_title))
            rows += sub._rows()
        return rows

    def usage(self):
        """Commands and their help; a command whose arguments are long gets its help on the line below, so the
        short ones stay readable and nothing goes off screen."""
        t = HELP.get(self.lang, HELP["en"])
        rows = self._rows()
        w = min(34, max([len(a) for a, _ in rows] + [10])) + 2
        out = [f"{self.title} — {t[0]} ({t[1]})", ""]
        for a, b in rows:
            if not a:
                out.append("")
            elif len(a) <= w - 2:
                out.append(f"  {a:<{w}}{b}")
            else:
                out += [f"  {line}" for line in textwrap.wrap(a, 96, subsequent_indent="    ")] + [" " * (w + 2) + b]
        return "\n".join(out)

    def _menu_items(self):
        items = [c for c in self.commands.values() if c.menu]
        for name, sub in self.sections.items():  # a section = one item that opens its own menu
            items.append(Command(name, lambda s, a, sub=sub: sub.menu(s), menu=f"{sub.section_title} ›", effects=False))
        return items

    def menu_short(self, items=None):
        """The labels of the compact menu, «Quit» included: short= of each command, otherwise its menu text."""
        items = self._menu_items() if items is None else items
        return [c.short or c.menu for c in items] + [HELP.get(self.lang, HELP["en"])[3]]

    def menu_keys(self, items=None):
        """One letter per menu item, then «q» for Quit: the chosen ones (key=) first, the others the first free
        letter of their text. j k q are the menu's own (and digits pick by number)."""
        items = self._menu_items() if items is None else items
        taken = {"q", "j", "k"} | {c.key for c in items if c.key}
        out = []
        for c in items:
            k = c.key or next((ch for ch in c.menu.lower() if "a" <= ch <= "z" and ch not in taken), None)
            taken.add(k)
            out.append(k)
        return out + ["q"]

    def menu(self, screen):
        t = HELP.get(self.lang, HELP["en"])
        items = self._menu_items()
        letters = self.menu_keys(items)
        code = i = 0
        screen.clear()
        screen.header(self.menu_subtitle)
        with access.session(self.session_idle_minutes):  # a VPN opened for one action serves the next ones
            while True:  # back to the menu after each item, until «Quit»: on the item you came from
                if len(self.crumbs) > 1:
                    screen.out("  " + screen.dim(f" {screen.theme.crumb} ".join(self.crumbs)))
                options = [Label(o, sh) for o, sh in zip([c.menu for c in items] + [t[3]], self.menu_short(items))]
                i = screen.choose(t[2], options, keys=letters, start=i, esc=len(items))
                if i == len(items):
                    return code
                screen.fresh(self.crumbs + [items[i].menu.rstrip(" ›")])
                code = self.call(items[i], screen, [])
                screen.results = []  # each item's summary counts only its own steps
                if not stdin_tty():
                    return code
                if not screen.stay:  # a screen closed by a key has nothing left to read
                    screen.ask(screen.dim(t[4]))
                screen.clear()
                screen.header(self.menu_subtitle)

    def main(self, argv=None):
        argv = sys.argv[1:] if argv is None else argv
        t = HELP.get(self.lang, HELP["en"])
        if argv and argv[0] in ("help", "-h", "--help"):
            print(self.usage())
            return 0
        screen = self.screen()
        try:
            if not argv:
                if self.first_run and not self.state().get("first_run_done"):
                    code = self.call(self.commands[self.first_run], screen, [])
                    self.save_state(first_run_done=True)
                    if not stdin_tty():
                        return code
                    screen.results = []  # owner 29/10: after the first setup, straight into the menu
                    screen.ask(screen.dim(HELP.get(self.lang, HELP["en"])[4]))
                    return self.menu(screen)
                return self.menu(screen)
            if argv[0] in self.sections:
                sub = self.sections[argv[0]]
                if len(argv) == 1:
                    return sub.menu(screen)
                c = sub.local(argv[1])
                if not c:
                    print(f"{t[5]}: {' '.join(argv[:2])}\n\n{sub.usage()}", file=sys.stderr)
                    return 2
                return sub.call(c, screen, argv[2:])
            c = self.local(argv[0])
            if not c:
                print(f"{t[5]}: {argv[0]}\n\n{self.usage()}", file=sys.stderr)
                return 2
            return self.call(c, screen, argv[1:])
        except KeyboardInterrupt:
            return 130
        except proc.PolicyError as e:  # the rules stopped it: a clear line, not a traceback
            screen.out(screen.c(screen.theme.error, screen.theme.no) + f" {e}")
            return 3
        finally:
            screen.close()

    def call(self, c, screen, args):
        screen.read_only = not c.effects
        screen.dry = c.dry and any(a in DRY_FLAGS for a in args)
        screen.json = JSON_FLAG in args
        screen.refresh = any(a in REFRESH_FLAGS for a in args)
        if screen.json:
            screen.full = False  # data for another program: plain lines on stderr, JSON on stdout
        proc.POLICY.update(write_commands=self.write_commands, read_only=screen.read_only, dry=screen.dry)
        screen.timings, screen.outcome = {}, False
        section = c.fn.__defaults__ and isinstance(c.fn.__defaults__[-1], App)  # a section's menu, not an action
        try:
            drop = (DRY_FLAGS if c.dry else ()) + REFRESH_FLAGS + (JSON_FLAG,)
            try:
                code = c.fn(screen, [a for a in args if a not in drop]) or 0
            except (KeyboardInterrupt, proc.PolicyError):
                raise
            except Exception as e:  # a clear ✗ line, never a traceback (PCB_DEBUG=1: the traceback)
                if os.environ.get("PCB_DEBUG"):
                    raise
                if not screen.json:
                    screen.done(f"{c.menu or c.name}: {type(e).__name__}: {e}", ok=False)
                    screen.info(screen.dim(screen.t["debug"].format(env="PCB_DEBUG")))
                return 1
            if not (screen.outcome or screen.json or section):
                label, stay = (c.menu or c.name).rstrip(" ›"), screen.stay
                screen.done(f"{label}: {screen.t['done']}" if code == 0 else
                            f"{label}: {screen.t['failed'].format(code=code)}", ok=code == 0)
                screen.stay = stay  # a screen closed with a key: back to the menu without a pause, as before
            if self.timings and screen.timings and not screen.json and not screen.dry:
                every = self.state().get("timings", {})
                screen.timing_table(every.get(c.name))
                every[c.name] = {k: round(v, 1) for k, v in screen.timings.items()}
                self.save_state(timings=every)
            return code
        finally:
            screen.read_only = screen.dry = screen.json = screen.refresh = False
            proc.POLICY.update(read_only=False, dry=False)

    def run(self):
        sys.exit(self.main())
