"""An App = name + look + commands. No arguments: the interactive menu (or the first-run command); `help`: the
usage generated from the commands; state kept per computer in ~/.config/<name>/state.json (never secrets)."""
import json, os, sys

from .term import Screen, Theme

HELP = {"it": ("comandi", "senza argomenti: il menu", "Cosa vuoi fare?", "Esci", "Invio per tornare al menu",
               "comando sconosciuto", "solo lettura", "--prova"),
        "en": ("commands", "no arguments: the menu", "What do you want to do?", "Quit", "Enter to go back to the menu",
               "unknown command", "read-only", "--dry-run")}
DRY_FLAGS = ("--prova", "--dry-run")


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
    def __init__(self, name, fn, help="", menu=None, args="", effects=True):
        self.name, self.fn, self.help, self.menu, self.args, self.effects = name, fn, help, menu, args, effects


class App:
    """
        app = App("deploy-kit", title="Deploy kit", accent="#4a6cf7")

        @app.command("check", help="what is ok and what is missing", menu="Check everything")
        def check(screen, args): ...

        app.main()
    """
    def __init__(self, name, title="", accent=None, theme=None, lang="it", first_run=None, menu_subtitle=""):
        self.name, self.title, self.lang = name, title or name, lang
        self.theme = theme or Theme(**({"accent": Theme.rgb(accent) if accent.startswith("#") else accent} if accent else {}))
        self.commands, self.first_run, self.menu_subtitle = {}, first_run, menu_subtitle
        self.state_path = os.path.join(os.path.expanduser("~"), ".config", name, "state.json")

    # ── state ──
    def state(self):
        return read_json(self.state_path, {}) or {}

    def save_state(self, **kv):
        s = self.state()
        s.update(kv)
        write_json(self.state_path, s)

    # ── commands ──
    def command(self, name, help="", menu=None, args="", effects=True):
        """menu = the text in the interactive menu (None = not in the menu); args = usage shown in help.
        effects=False declares a read-only command: its steps can only check (enforced in run_steps). A command
        with effects gets --prova/--dry-run: screen.dry is True and run_steps only says what it would do."""
        def add(fn):
            self.commands[name] = Command(name, fn, help, menu, args, effects)
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
        finally:
            screen.close()

    @staticmethod
    def call(c, screen, args):
        screen.read_only = not c.effects
        screen.dry = c.effects and any(a in DRY_FLAGS for a in args)
        try:
            return c.fn(screen, [a for a in args if a not in DRY_FLAGS]) or 0
        finally:
            screen.read_only = screen.dry = False

    def run(self):
        sys.exit(self.main())
