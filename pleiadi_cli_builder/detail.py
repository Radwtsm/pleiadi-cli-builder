"""A scrolling detail view (one record: a task, a ticket, a build): key fields fixed at the top, long text below
that scrolls (arrows, PgUp/PgDn, Home/End), / to search with n to jump to the next hit, sections that fold, colors
with a meaning declared by the tool plus a legend. Text wraps to the window and rewraps when it changes.
Outside a real terminal: plain text with everything open; with --json: the data.

The paging logic (Pager) has no terminal in it, so it is tested without one."""
import textwrap

from .term import ANSI

TONES = {"alarm": "31;1", "warn": "33", "ok": "32", "dim": "2"}


class Detail:
    """fields = [(label, value, tone)]; sections = [(title, [(text, tone)], folded=False)]; legend = {tone: meaning}.
    tone: "alarm", "warn", "ok", "dim" or None."""
    def __init__(self, title, fields=(), sections=(), legend=None):
        self.title, self.fields, self.legend = title, list(fields), dict(legend or {})
        self.sections = [(s[0], list(s[1]), bool(s[2]) if len(s) > 2 else False) for s in sections]

    def as_dict(self):
        return {"title": self.title, "fields": {label: value for label, value, _ in self.fields},
                "sections": {t: [text for text, _ in items] for t, items, _ in self.sections}}


class Pager:
    def __init__(self, detail, width=80, height=24, color=None):
        self.d, self.width, self.height = detail, width, height
        self.color = color or (lambda code, text: text)
        self.folded = {t for t, _, f in detail.sections if f}
        self.top, self.hits, self.hit, self.query = 0, [], 0, ""

    def resize(self, width, height):
        self.width, self.height = width, height
        self.top = min(self.top, self.max_top())

    def paint(self, text, tone):
        return self.color(TONES[tone], text) if tone in TONES else text

    # ── what is on screen ──
    def header(self):
        out = [self.color("1", self.d.title)]
        parts = [self.paint(f"{label} {value}", tone) for label, value, tone in self.d.fields if value not in (None, "")]
        line, n = [], 0
        for p in parts:
            w = len(ANSI.sub("", p))
            if line and n + 3 + w > self.width:
                out.append("   ".join(line))
                line, n = [], 0
            line.append(p)
            n += w + (3 if n else 0)
        if line:
            out.append("   ".join(line))
        return out + [self.color("2", "─" * self.width)]

    def legend_lines(self):
        if not self.d.legend:
            return []
        return [self.color("2", "legenda: ") + "  ".join(self.paint("■ " + m, t) for t, m in self.d.legend.items())]

    def lines(self):
        """The body, wrapped to the width; self.owner[i] = the section of line i."""
        out, self.owner = [], []
        for title, items, _ in self.d.sections:
            if out:
                out.append("")
                self.owner.append(None)
            if title in self.folded:
                out.append(self.color("1", f"▸ {title}") + self.color("2", f" ({len(items)} righe)"))
                self.owner.append(title)
                continue
            out.append(self.color("1", f"▾ {title}"))
            self.owner.append(title)
            for text, tone in items:
                for raw in str(text).split("\n"):
                    for w in textwrap.wrap(raw, max(10, self.width - 2), break_long_words=True,
                                           replace_whitespace=False) or [""]:
                        out.append("  " + self.paint(w, tone))
                        self.owner.append(title)
        return out

    def rows(self):
        return max(1, self.height - len(self.header()) - len(self.legend_lines()))

    def max_top(self):
        return max(0, len(self.lines()) - self.rows())

    def render(self):
        body = self.lines()[self.top:self.top + self.rows()]
        if self.hits:  # the current hit stands out
            cur = self.hits[self.hit] - self.top
            if 0 <= cur < len(body):
                body[cur] = self.color("7", ANSI.sub("", body[cur]))
        return self.header() + body + [""] * (self.rows() - len(body)) + self.legend_lines()

    # ── keys ──
    def toggle(self, title=None):
        """Fold/unfold `title`, or the section of the first line on screen."""
        if title is None:
            self.lines()
            title = next((self.owner[i] for i in range(self.top, len(self.owner)) if self.owner[i]), None)
        if title:
            self.folded ^= {title}
            self.top = min(self.top, self.max_top())

    def search(self, query):
        """Jumps to the first line with `query` (any case), opening the folded sections where it is. Returns the
        number of hits; n goes to the next one."""
        self.query, q = query, query.lower()
        for title, items, _ in self.d.sections:
            if any(q in str(t).lower() for t, _ in items):
                self.folded.discard(title)
        self.hits = [i for i, l in enumerate(self.lines()) if q and q in ANSI.sub("", l).lower()]
        self.hit = 0
        self._show_hit()
        return len(self.hits)

    def _show_hit(self):
        if self.hits:
            self.top = min(self.hits[self.hit], self.max_top())

    def handle(self, k):
        """One key → "quit", "search" (the caller asks the text, then search()), or None."""
        page = max(1, self.rows() - 1)
        moves = {"up": -1, "down": 1, "pgup": -page, "pgdn": page, "k": -1, "j": 1}
        if k in moves:
            self.top = max(0, min(self.max_top(), self.top + moves[k]))
        elif k in ("home", "g"):
            self.top = 0
        elif k in ("end", "G"):
            self.top = self.max_top()
        elif k == " ":
            self.toggle()
        elif k in ("n", "N") and self.hits:
            self.hit = (self.hit + (1 if k == "n" else -1)) % len(self.hits)
            self._show_hit()
        elif k == "/":
            return "search"
        elif k in ("q", "esc", "enter"):
            return "quit"
        return None

    def plain(self):
        """Everything open, for a pipe or a log."""
        self.folded = set()
        return [ANSI.sub("", l) for l in self.header() + self.lines() + self.legend_lines()]
