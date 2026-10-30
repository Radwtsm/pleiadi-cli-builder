"""A scrolling detail view (one record: a task, a ticket, a build): key fields fixed at the top, long text below
that scrolls (arrows, PgUp/PgDn, Home/End), / to search with n to jump to the next hit, sections that fold, colors
with a meaning declared by the tool plus a legend. Lines new since the last look are marked ● and n/N jump between
them (with «2/7» in the bottom line) when no search is on; the view opens on the first one. Text wraps to the window and rewraps when it changes.
Outside a real terminal: plain text with everything open; with --json: the data.

The paging logic (Pager) has no terminal in it, so it is tested without one."""
import textwrap

from .term import ANSI

TONES = {"alarm": "31;1", "warn": "33", "ok": "32", "dim": "2"}


class Detail:
    """fields = [(label, value, tone)]; sections = [(title, [(text, tone)], folded=False, new=0)]; legend = {tone:
    meaning}. tone: "alarm", "warn", "ok", "dim" or None. new = how many of the section's first lines are new since
    the last look (True: all of them); a section with new lines never starts folded."""
    def __init__(self, title, fields=(), sections=(), legend=None, actions=None):
        """actions = {key: (label, fn(screen) → message)}: one-key operations on this record (shown in the
        bottom line), e.g. {"d": ("scarica allegati", …), "c": ("copia il numero", …)}."""
        self.title, self.fields, self.legend, self.actions = title, list(fields), dict(legend or {}), dict(actions or {})
        self.sections = [(s[0], list(s[1]), bool(s[2]) if len(s) > 2 else False) for s in sections]
        new = [(s[3] if len(s) > 3 else 0) for s in sections]
        self.new = {n: len(self.sections[n][1]) if k is True else min(int(k), len(self.sections[n][1]))
                    for n, k in enumerate(new) if k}  # {section index: how many first lines are new}

    def as_dict(self):
        out = {"title": self.title, "fields": {label: value for label, value, _ in self.fields},
               "sections": {t: [text for text, _ in items] for t, items, _ in self.sections}}
        if self.new:
            out["new"] = {self.sections[n][0]: [t for t, _ in self.sections[n][1][:k]] for n, k in self.new.items()}
        return out


class Pager:
    def __init__(self, detail, width=80, height=24, color=None, select="38;5;153;1;48;5;237", mark="38;5;153"):
        self.d, self.width, self.height, self.select, self.mark = detail, width, height, select, mark
        self.color = color or (lambda code, text: text)
        self.folded = {t for n, (t, _, f) in enumerate(detail.sections) if f and n not in detail.new}
        self.top, self.hits, self.hit, self.query = 0, [], 0, ""
        self.cur = 0  # the section Space opens/closes: marked ▶ (owner 29/10: «deve essere chiaro»)
        self.news, self.new_at = [], -1  # the first body line of each new line; the one n/N last went to
        if detail.new:  # opens on the first new line
            self._next_new(1)

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
        out, self.owner, self.heads, self.news = [], [], [], []
        for n, (title, items, _) in enumerate(self.d.sections):
            if out:
                out.append("")
                self.owner.append(None)
            self.heads.append(len(out))
            text = f"▸ {title}" + f" ({len(items)} righe)" if title in self.folded else f"▾ {title}"
            if n == self.cur:  # the section Space acts on: a bar across the width, like a selected row
                out.append(self.color(self.select, ("▶ " + text).ljust(self.width)))
            elif title in self.folded:
                out.append("  " + self.color("1", f"▸ {title}") + self.color("2", f" ({len(items)} righe)"))
            else:
                out.append("  " + self.color("1", f"▾ {title}"))
            self.owner.append(title)
            if title in self.folded:
                continue
            new = self.d.new.get(n, 0)
            for k, (text, tone) in enumerate(items):
                gutter = self.color(self.mark, "● ") if k < new else "  "  # new since the last look
                if k < new:
                    self.news.append(len(out))
                for raw in str(text).split("\n"):
                    for w in textwrap.wrap(raw, max(10, self.width - 2), break_long_words=True,
                                           replace_whitespace=False) or [""]:
                        out.append(gutter + self.paint(w, tone))
                        self.owner.append(title)
                        gutter = "  "
        return out

    def rows(self):
        return max(1, self.height - len(self.header()) - len(self.legend_lines()))

    def max_top(self):
        return max(0, len(self.lines()) - self.rows())

    def render(self):
        lines = self.lines()
        body = lines[self.top:self.top + self.rows()]
        at = self.hits[self.hit] if self.hits else self.news[self.new_at] if 0 <= self.new_at < len(self.news) else None
        if at is not None:  # the current hit, or the new line n/N went to, stands out
            cur = at - self.top
            if 0 <= cur < len(body):
                body[cur] = self.color("7", ANSI.sub("", body[cur]))
        return self.header() + body + [""] * (self.rows() - len(body)) + self.legend_lines()

    # ── keys ──
    def toggle(self, title=None):
        """Fold/unfold `title`, or the marked section."""
        if title is None and self.d.sections:
            title = self.d.sections[self.cur][0]
        if title:
            self.folded ^= {title}
            self.top = min(self.top, self.max_top())

    def _jump(self, step):
        """Tab / Shift+Tab: the mark to the next/previous section, and the view to its title."""
        if self.d.sections:
            self.cur = (self.cur + step) % len(self.d.sections)
            self.lines()
            self.top = min(self.heads[self.cur], self.max_top())

    def _follow(self):
        """After scrolling: if the marked title left the screen, mark the first title on screen (or below it)."""
        self.lines()
        if not self.heads or self.top <= self.heads[self.cur] < self.top + self.rows():
            return
        after = [n for n, h in enumerate(self.heads) if h >= self.top]
        self.cur = after[0] if after else len(self.heads) - 1

    def _next_new(self, step):
        """n/N without a search: to the next/previous new line (round), with its section title in view."""
        self.lines()
        if self.news:
            self.new_at = (self.new_at + step) % len(self.news) if self.new_at >= 0 or step > 0 else len(self.news) - 1
            self.top = max(0, min(self.news[self.new_at] - 1, self.max_top()))
            self._follow()

    def nav(self):
        """The generic keys (the record's own operations are shown apart, highlighted: Screen.shortcut_line)."""
        self.lines()
        if self.news and not self.hits:  # NBSP: «nuove 2/7» stays one label (term.pairs splits on spaces)
            at = f"{self.new_at + 1}/{len(self.news)}" if self.new_at >= 0 else str(len(self.news))
            n = f"n/N nuove\u00a0{at}"
        else:
            n = "n successiva"
        return f"↑↓ PgSu PgGiù scorri · Tab sezione · Spazio apre/chiude · / cerca · {n} · q chiudi"

    def hint(self):
        acts = " · ".join(f"{k} {label}" for k, (label, _) in self.d.actions.items())
        return (acts + " · " if acts else "") + self.nav()

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
        if k in self.d.actions:
            return ("action", k)
        if k in moves:
            self.top = max(0, min(self.max_top(), self.top + moves[k]))
            self._follow()
        elif k in ("home", "g"):
            self.top = 0
            self._follow()
        elif k in ("end", "G"):
            self.top = self.max_top()
            self._follow()
        elif k in ("tab", "backtab"):
            self._jump(1 if k == "tab" else -1)
        elif k == " ":
            self.toggle()
        elif k in ("n", "N") and self.hits:
            self.hit = (self.hit + (1 if k == "n" else -1)) % len(self.hits)
            self._show_hit()
        elif k in ("n", "N"):  # no search on: the new lines
            self._next_new(1 if k == "n" else -1)
        elif k == "/":
            return "search"
        elif k in ("q", "esc", "enter"):
            return "quit"
        return None

    def plain(self):
        """Everything open, for a pipe or a log."""
        self.folded = set()
        return [ANSI.sub("", l) for l in self.header() + self.lines() + self.legend_lines()]
