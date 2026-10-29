"""A table in groups with check marks: the rows arrive at once, the slow columns (a last build, a check over the
VPN) are filled in the background while the table is already on screen, Space checks a row or a whole group, and
one-key actions run on the checked rows (none checked: the row under the cursor). After an action its rows are
filled again, so what changed shows up by itself. Outside a real terminal: the groups as plain tables, every
cell waited for; with --json: the rows, each with its group.

The view logic (BoardView) has no terminal in it, so it is tested without one."""
import threading, time

from .term import TEXTS

PENDING = object()  # a background cell not filled yet


class Board:
    """groups = [(title, [row dict])]; columns = keys to show; titles = {key: header};
    fill = {key: fn(row) → value}: computed in the background (an error becomes «✗ reason» in that cell);
    actions = {key: (label, fn(screen, rows) → message)}: one-key operations on the checked rows. The keys
    ↑↓ j k Space a q Enter are the view's own: give the actions other letters."""
    def __init__(self, title, columns, groups, titles=None, fill=None, actions=None, workers=4):
        self.title, self.columns, self.titles = title, list(columns), dict(titles or {})
        self.groups = [(g, list(rows)) for g, rows in groups]
        self.fill, self.actions = dict(fill or {}), dict(actions or {})
        self._slots, self._threads = threading.Semaphore(workers), []

    def rows(self):
        return [r for _, rows in self.groups for r in rows]

    def start(self, on_change=None, rows=None):
        """Fills the background columns of `rows` (default: all), `workers` at a time; on_change() after each cell
        (from another thread: the screen redraws). Returns at once."""
        jobs = [(r, k) for r in (self.rows() if rows is None else rows) for k in self.fill]
        for r, k in jobs:
            r[k] = PENDING

        def work(row, k):
            with self._slots:
                try:
                    value = self.fill[k](row)
                except Exception as e:  # one cell that fails says why; the others still arrive
                    value = f"✗ {e}"
                row[k] = value
            if on_change:
                try:
                    on_change()
                except Exception:
                    pass
        for r, k in jobs:
            t = threading.Thread(target=work, args=(r, k), daemon=True)  # daemon: a slow check never holds the exit
            self._threads.append(t)
            t.start()

    def wait(self, timeout=None):
        """Until every started cell is filled (or `timeout` seconds). True when all arrived."""
        end = None if timeout is None else time.monotonic() + timeout
        for t in list(self._threads):
            t.join(None if end is None else max(0, end - time.monotonic()))
        self._threads = [t for t in self._threads if t.is_alive()]
        return not self._threads

    def as_rows(self):
        value = lambda v: None if v is PENDING else v
        return [{"gruppo": g, **{k: value(r.get(k)) for k in self.columns}} for g, rows in self.groups for r in rows]


class BoardView:
    def __init__(self, board, width=80, height=24, color=None, select="38;5;153;1;48;5;237", error="31", dim="2",
                 check="✓", texts=None):
        self.b, self.width, self.height = board, width, height
        self.color = color or (lambda code, text: text)
        self.select, self.error, self.dim, self.mark = select, error, dim, check
        self.t = texts or TEXTS["it"]
        self.items = [x for g, (_, rows) in enumerate(board.groups) for x in [(g, None)] + [(g, i) for i in range(len(rows))]]
        self.cur, self.top, self.ticked = 0, 0, set()

    def resize(self, width, height):
        self.width, self.height = width, height

    # ── what is checked ──
    def checked(self):
        return [r for g, i in self.items if i is not None and (g, i) in self.ticked for r in [self.b.groups[g][1][i]]]

    def targets(self):
        """What an action acts on: the checked rows, otherwise the row (or the group) under the cursor."""
        if self.ticked:
            return self.checked()
        g, i = self.items[self.cur] if self.items else (None, None)
        if g is None:
            return []
        return list(self.b.groups[g][1]) if i is None else [self.b.groups[g][1][i]]

    def _group(self, g):
        return {(g, i) for i in range(len(self.b.groups[g][1]))}

    def toggle(self):
        g, i = self.items[self.cur]
        cells = self._group(g) if i is None else {(g, i)}
        self.ticked = self.ticked - cells if cells <= self.ticked else self.ticked | cells

    def toggle_all(self):
        every = {(g, i) for g, i in self.items if i is not None}
        self.ticked = set() if every and every <= self.ticked else every

    # ── what is on screen ──
    def _cell(self, v):
        return "…" if v is PENDING else "" if v is None else " ".join(str(v).split())

    def _widths(self, room):
        head = [str(self.b.titles.get(k, k)) for k in self.b.columns]
        body = [[self._cell(r.get(k)) for k in self.b.columns] for r in self.b.rows()]
        widths = [max([len(h)] + [len(x[n]) for x in body]) for n, h in enumerate(head)]
        room -= 2 * (len(widths) - 1)
        while sum(widths) > room and max(widths) > 6:
            widths[widths.index(max(widths))] -= 1
        return head, widths

    def _box(self, state):
        return {"all": f"[{self.mark}]", "some": "[–]", "none": "[ ]"}[state]

    def rows_room(self):
        return max(1, self.height - 3)

    def render(self):
        """Title with the count, column titles and a rule, then the groups and rows that fit (the cursor always
        among them): exactly `height` lines."""
        pad = 8  # «    [✓] » before the first column of a row
        head, widths = self._widths(self.width - pad)
        fit = lambda v, w: v if len(v) <= w else v[:w - 1] + "…"
        n, tot = len(self.ticked), sum(len(r) for _, r in self.b.groups)
        out = [self.color("1", self.b.title) + self.color(self.dim, "  " + self.t["checked"].format(n=n, tot=tot)),
               " " * pad + self.color("1", "  ".join(fit(h, w).ljust(w) for h, w in zip(head, widths)).rstrip()),
               " " * pad + self.color(self.dim, "─" * min(self.width - pad, sum(widths) + 2 * (len(widths) - 1)))]
        room = self.rows_room()
        self.top = min(max(self.top, self.cur - room + 1), self.cur, max(0, len(self.items) - room))
        for at in range(self.top, min(len(self.items), self.top + room)):
            g, i = self.items[at]
            title, rows = self.b.groups[g]
            if i is None:
                mine = self._group(g) & self.ticked
                state = "all" if rows and len(mine) == len(rows) else "some" if mine else "none"
                text = f"  {self._box(state)} {title} ({len(rows)})"
                line = self.color("1", text)
            else:
                row = rows[i]
                cells = [fit(self._cell(row.get(k)), w).ljust(w) for k, w in zip(self.b.columns, widths)]
                text = f"    {self._box('all' if (g, i) in self.ticked else 'none')} " + "  ".join(cells).rstrip()
                shown = [self.color(self.dim, c) if row.get(k) is PENDING else
                         self.color(self.error, c) if isinstance(row.get(k), str) and row.get(k).startswith("✗") else c
                         for k, c in zip(self.b.columns, cells)]
                line = f"    {self._box('all' if (g, i) in self.ticked else 'none')} " + "  ".join(shown).rstrip()
            out.append(self.color(self.select, text.ljust(self.width)) if at == self.cur else line)
        return out + [""] * (self.height - len(out))

    def hint(self):
        acts = " · ".join(f"{k} {label}" for k, (label, _) in self.b.actions.items())
        return self.t["hint_board"].format(actions=f" · {acts}" if acts else "")

    # ── keys ──
    def handle(self, k):
        """One key → ("action", key), "done" (Enter: the checked rows), "quit" (q/Esc) or None."""
        if k in self.b.actions:
            return ("action", k)
        page = max(1, self.rows_room() - 1)
        moves = {"up": -1, "down": 1, "k": -1, "j": 1, "pgup": -page, "pgdn": page}
        if k in moves and self.items:
            self.cur = max(0, min(len(self.items) - 1, self.cur + moves[k]))
        elif k == "home":
            self.cur = 0
        elif k == "end":
            self.cur = max(0, len(self.items) - 1)
        elif k == " " and self.items:
            self.toggle()
        elif k == "a":
            self.toggle_all()
        elif k == "enter":
            return "done"
        elif k in ("q", "esc"):
            return "quit"
        return None
