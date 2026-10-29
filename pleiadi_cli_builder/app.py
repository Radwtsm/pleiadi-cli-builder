"""An App = name + look + commands. No arguments: the interactive menu (or the first-run command); `help`: the
usage generated from the commands; state kept per computer in ~/.config/<name>/state.json (never secrets)."""
import json, os, re, sys, time

from . import proc
from .term import MAC, WIN, Screen, Theme

HELP = {"it": ("comandi", "senza argomenti: il menu", "Cosa vuoi fare?", "Esci", "Invio per tornare al menu",
               "comando sconosciuto", "solo lettura", "--prova", "istantanea del {when} · --aggiorna per riscaricarla"),
        "en": ("commands", "no arguments: the menu", "What do you want to do?", "Quit", "Enter to go back to the menu",
               "unknown command", "read-only", "--dry-run", "snapshot of {when} · --refresh to download it again")}
DRY_FLAGS = ("--prova", "--dry-run")
REFRESH_FLAGS = ("--aggiorna", "--refresh")
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
    def __init__(self, name, fn, help="", menu=None, args="", effects=True, json=False, example=()):
        self.name, self.fn, self.help, self.menu, self.args, self.effects = name, fn, help, menu, args, effects
        self.json, self.example = json, list(example)


class App:
    """
        app = App("deploy-kit", title="Deploy kit", accent="#4a6cf7")

        @app.command("check", help="what is ok and what is missing", menu="Check everything")
        def check(screen, args): ...

        app.main()
    """
    def __init__(self, name, title="", accent=None, theme=None, lang="it", first_run=None, menu_subtitle="",
                 write_commands=()):
        """write_commands = the programs that change something, as the start of their command line
        (e.g. [["git", "push"], ["rm"]]): run() refuses them inside read-only commands and dry runs."""
        self.name, self.title, self.lang = name, title or name, lang
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
    def snapshot(self, name, fetch, refresh=False):
        """(data, "YYYY-MM-DD HH:MM"): data fetched once (e.g. while temporary() keeps a VPN open) and kept in the
        user's cache, readable by that user only; later calls read it back until refresh=True (--aggiorna/--refresh
        sets screen.refresh). Filter it locally: the remote service is asked once. It is a copy of the data on this
        disk: for data under a company's policy, check that the policy allows it."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError(f"snapshot name {name!r}: letters, digits, - and _ only")
        path = os.path.join(self.cache_dir, name + ".json")
        if not refresh:
            old = read_json(path)
            if isinstance(old, dict) and "taken" in old:
                return old.get("data"), old["taken"]
        data, taken = fetch(), time.strftime("%Y-%m-%d %H:%M")
        os.makedirs(self.cache_dir, exist_ok=True)
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # created private, not chmod later
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"taken": taken, "data": data}, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        return data, taken

    def snapshot_note(self, when):
        return HELP.get(self.lang, HELP["en"])[8].format(when=when)

    # ── commands ──
    def command(self, name, help="", menu=None, args="", effects=True, json=False, example=()):
        """menu = the text in the interactive menu (None = not in the menu); args = usage shown in help.
        effects=False declares a read-only command: its steps can only check (enforced in run_steps). A command
        with effects gets --prova/--dry-run: screen.dry is True and run_steps only says what it would do.
        json=True: the command prints its data with screen.table and supports --json; example = sample arguments
        for the contract tests (pleiadi_cli_builder.contract)."""
        def add(fn):
            self.commands[name] = Command(name, fn, help, menu, args, effects, json, example)
            return fn
        return add

    def screen(self):
        return Screen(self.name, self.title, self.theme, self.lang)

    def usage(self):
        t = HELP.get(self.lang, HELP["en"])
        rows = [(f"{self.name} {c.name}" + (f" {c.args}" if c.args else "") + (f" [{t[7]}]" if c.effects else ""),
                 c.help + (f" ({t[6]})" if not c.effects else "")) for c in self.commands.values()]
        w = max([len(r[0]) for r in rows] + [10]) + 2
        return "\n".join([f"{self.title} — {t[0]} ({t[1]})", ""] + [f"  {a:<{w}}{b}" for a, b in rows])

    def menu(self, screen):
        t = HELP.get(self.lang, HELP["en"])
        items = [c for c in self.commands.values() if c.menu]
        code = 0
        screen.clear()
        screen.header(self.menu_subtitle)
        while True:  # back to the menu after each item, until «Quit»
            i = screen.choose(t[2], [c.menu for c in items] + [t[3]])
            if i == len(items):
                return code
            code = self.call(items[i], screen, [])
            screen.results = []  # each item's summary counts only its own steps
            if not sys.stdin.isatty():
                return code
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
                    return code
                return self.menu(screen)
            c = self.commands.get(argv[0])
            if not c:
                print(f"{t[5]}: {argv[0]}\n\n{self.usage()}", file=sys.stderr)
                return 2
            return self.call(c, screen, argv[1:])
        except KeyboardInterrupt:
            return 130
        except proc.PolicyError as e:  # the rules stopped it: a clear line, not a traceback
            screen.out(screen.c(screen.theme.error, "✗") + f" {e}")
            return 3
        finally:
            screen.close()

    def call(self, c, screen, args):
        screen.read_only = not c.effects
        screen.dry = c.effects and any(a in DRY_FLAGS for a in args)
        screen.json = JSON_FLAG in args
        screen.refresh = any(a in REFRESH_FLAGS for a in args)
        if screen.json:
            screen.full = False  # data for another program: plain lines on stderr, JSON on stdout
        proc.POLICY.update(write_commands=self.write_commands, read_only=screen.read_only, dry=screen.dry)
        try:
            return c.fn(screen, [a for a in args if a not in DRY_FLAGS + REFRESH_FLAGS and a != JSON_FLAG]) or 0
        finally:
            screen.read_only = screen.dry = screen.json = screen.refresh = False
            proc.POLICY.update(read_only=False, dry=False)

    def run(self):
        sys.exit(self.main())
