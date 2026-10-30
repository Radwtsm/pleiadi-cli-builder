"""Settings a person can see and change from the tool itself — never by editing the JSON by hand: a screen with
every setting and its value (Enter changes one, checked before it is saved), «Start over» for a setup gone wrong,
and the same from the command line (`tool settings KEY VALUE`, `--json`) for scripts and for Claude.

    SETTINGS = [Setting("url", "Redmine address", check=lambda v: v.startswith("https://") or "must start with https://"),
                Setting("keep", "Local copy", kind="yesno"),
                Setting("refresh", "Minutes between downloads", kind="number", default=10)]
    edit_settings(screen, config_path, SETTINGS, args)

The logic (show, parse, set_value, reset) has no terminal in it, so it is tested without one."""
import os, shlex

from .app import read_json, write_json

KEEP = object()  # what a custom edit returns when nothing changes


class Setting:
    """key = its name in the config JSON; label = what a person reads; kind = "text", "yesno", "choice" (choices =
    [(value, label)]), "number", "list" (comma-separated), "folder" or "command" (a command line). default = the
    value when it is not set. note = one line on what it changes. check(value) → True, or the reason it is refused.
    show(value) → text and parse(text) → value replace the kind's own; edit(screen, current) → value (or KEEP)
    replaces the question (e.g. several answers for one setting)."""
    def __init__(self, key, label, kind="text", choices=(), default=None, note="", check=None, show=None, parse=None,
                 edit=None):
        self.key, self.label, self.kind, self.choices, self.default = key, label, kind, list(choices), default
        self.note, self._check, self._show, self._parse, self.edit = note, check, show, parse, edit

    def show(self, value, t):
        """The value as a person reads it; «—» when it is not set."""
        if self._show:
            return self._show(value)
        if value is None:
            return t["unset"] if self.default is None else f"{self.show(self.default, t)} {t['default']}"
        if self.kind == "yesno":
            return t["yes"] if value else t["no"]
        if self.kind == "choice":
            return next((label for v, label in self.choices if v == value), str(value))
        if self.kind == "list":
            return ", ".join(map(str, value)) or t["unset"]
        if self.kind == "command":
            return " ".join(shlex.quote(str(w)) for w in value)
        return str(value)

    def parse(self, text, t):
        """Typed text → value. ValueError with the reason when it doesn't fit. «-» = not set (back to default)."""
        text = text.strip()
        if text == "-":
            return None
        if self._parse:
            return self._parse(text)
        if self.kind == "yesno":
            low = text.lower()
            if low in ("si", "sì", "s", "yes", "y", "true", "1", t["yes"].lower()):
                return True
            if low in ("no", "n", "false", "0", t["no"].lower()):
                return False
            raise ValueError(t["bad_yesno"])
        if self.kind == "choice":
            for v, label in self.choices:
                if text.lower() in (str(v).lower(), label.lower()):
                    return v
            raise ValueError(t["bad_choice"].format(options=", ".join(str(v) for v, _ in self.choices)))
        if self.kind == "number":
            try:
                n = float(text.replace(",", "."))
            except ValueError:
                raise ValueError(t["bad_number"]) from None
            if n < 0:
                raise ValueError(t["bad_number"])
            return int(n) if n == int(n) else n
        if self.kind == "list":
            return [w.strip() for w in text.split(",") if w.strip()]
        if self.kind == "folder":
            return os.path.expanduser(text)
        if self.kind == "command":
            return shlex.split(text)
        return text

    def check(self, value):
        """None when it may be saved, otherwise the reason. Not set is always allowed (the default applies)."""
        if value is None or not self._check:
            return None
        r = self._check(value)
        return None if r is True or r is None else (str(r) if r else "?")


def values(path, settings):
    cfg = read_json(path, {}) or {}
    return {s.key: cfg.get(s.key) for s in settings}


def rows(path, settings, t):
    """[{key, label, value, shown}]: what the screen and the plain list show."""
    v = values(path, settings)
    return [{"key": s.key, "label": s.label, "value": v[s.key], "shown": s.show(v[s.key], t)} for s in settings]


def set_value(path, setting, value, dry=False):
    """Saves one setting (None = removes it: the default applies again); the others stay as they are. Returns
    None or the reason it was refused (nothing written then)."""
    why = setting.check(value)
    if why or dry:
        return why
    if setting.kind == "folder" and value:
        os.makedirs(value, exist_ok=True)
    cfg = read_json(path, {}) or {}
    if value is None:
        cfg.pop(setting.key, None)
    else:
        cfg[setting.key] = value
    write_json(path, cfg)
    return None


def reset(path, settings, dry=False):
    """Start over: removes every setting listed here; what the tool doesn't list (e.g. a certificate given by IT)
    stays. Returns the keys removed."""
    cfg = read_json(path, {}) or {}
    gone = [s.key for s in settings if s.key in cfg]
    if gone and not dry:
        write_json(path, {k: v for k, v in cfg.items() if k not in gone})
    return gone


def ask_value(screen, setting, current):
    """The question for one setting: a choice for yesno/choice, a typed answer for the others (the current value
    proposed; «-» = not set). KEEP when nothing changes."""
    t = screen.t
    if setting.edit:
        return setting.edit(screen, current)
    if setting.kind in ("yesno", "choice"):
        opts = [(True, t["yes"]), (False, t["no"])] if setting.kind == "yesno" else setting.choices
        now = current if current is not None else setting.default
        labels = [label + (f"  {t['current']}" if v == now else "") for v, label in opts] + [t["back"]]
        i = screen.choose(setting.label + (f" · {setting.note}" if setting.note else ""), labels)
        return KEEP if i == len(opts) else opts[i][0]
    shown = "" if current is None else setting.show(current, t)
    text = screen.ask(f"{setting.label}" + (f" ({setting.note})" if setting.note else "") + f" · {t['dash_unset']}",
                      shown)
    return KEEP if text == shown else setting.parse(text, t)


def edit_settings(screen, path, settings, args=(), actions=(), on_reset=None):
    """The settings command. args: none → in a real terminal the screen (Enter changes one, «Start over», extra
    `actions` = [(label, fn(screen) → message)] such as «change the API key»), otherwise the list (--json: the
    data); [KEY] → its value; [KEY, VALUE…] → sets it («-» = back to default); ["--reset"] → start over.
    on_reset(screen) runs after «Start over» (e.g. the setup again). Returns the exit code."""
    t, args = screen.t, list(args)
    by_key = {s.key: s for s in settings}
    if args and args[0] == "--reset":
        gone = reset(path, settings, dry=screen.dry)
        screen.info((f"{t['would']}: " if screen.dry else "") + t["reset_done"].format(n=len(gone)))
        return 0 if screen.dry or not on_reset else (on_reset(screen) or 0)
    if args:
        s = by_key.get(args[0])
        if not s:
            screen.todo(t["unknown_setting"].format(key=args[0], keys=", ".join(by_key)))
            return 2
        if len(args) == 1:
            v = values(path, settings)[s.key]
            if not screen.data({"key": s.key, "value": v}):
                screen.info(f"{s.label}: {s.show(v, t)}")
            return 0
        try:
            value = s.parse(" ".join(args[1:]), t)
        except ValueError as e:
            screen.todo(f"{s.label}: {e}")
            return 2
        why = set_value(path, s, value, dry=screen.dry)
        if why:
            screen.todo(f"{s.label}: {why}")
            return 1
        if not screen.data({"key": s.key, "value": value, "saved": not screen.dry}):
            screen.info((f"{t['would']}: " if screen.dry else "") + f"{s.label} = {s.show(value, t)}")
        return 0
    if screen.json or not (screen.full and screen.interactive):
        rs = rows(path, settings, t)
        if not screen.data({r["key"]: r["value"] for r in rs}):
            screen.table(rs, ["label", "shown", "key"], {"label": t["setting"], "shown": t["value"], "key": t["key"]})
            screen.info(screen.dim(t["settings_cli"].format(path=path)))
        return 0
    actions, msg = list(actions), ""
    while True:
        rs = rows(path, settings, t)
        w = max(len(r["label"]) for r in rs)
        labels = [f"{r['label']:<{w}}  {r['shown']}" for r in rs] + [label for label, _ in actions] + \
                 [t["reset"], t["back"]]
        if msg:
            screen.info(msg)
        i = screen.choose(t["settings_q"], labels, header=f"{t['setting']:<{w}}  {t['value']}")
        msg = ""
        if i < len(rs):
            s = settings[i]
            try:
                value = ask_value(screen, s, rs[i]["value"])
            except ValueError as e:
                msg = screen.c(screen.theme.error, screen.theme.no) + f" {s.label}: {e}"
                continue
            if value is KEEP:
                continue
            why = set_value(path, s, value, dry=screen.dry)
            msg = (screen.c(screen.theme.error, screen.theme.no) + f" {s.label}: {why}" if why else
                   screen.c(screen.theme.ok, screen.theme.yes) + f" {s.label} = {s.show(value, t)}")
        elif i < len(rs) + len(actions):
            label, fn = actions[i - len(rs)]
            try:
                msg = fn(screen) or label
            except Exception as e:  # an action that fails says why, the screen stays open
                msg = f"{label}: {e}"
        elif i == len(rs) + len(actions):
            if screen.confirm(t["reset_q"], t["reset_yes"], t["back"]):
                gone = reset(path, settings, dry=screen.dry)
                screen.info(t["reset_done"].format(n=len(gone)))
                return (on_reset(screen) or 0) if on_reset and not screen.dry else 0
        else:
            return 0
