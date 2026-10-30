"""Redmine for project managers: one read-only fetch (standard REST API) and pure calculations on it, so the same
numbers come out of the snapshot, the tests and any other interface."""
import datetime


def fetch_all(client, today, days=7, only=None):
    """Everything the commands need, in one go (inside one VPN window): who I am, active projects, open issues,
    issues closed in the last `days`. only = identifiers (or ids) of the projects to download, the rest is skipped
    (a big tracker: minutes less)."""
    since = (today - datetime.timedelta(days=days)).isoformat()
    projects = list(client.pages("/projects.json", {"status": 1}, items="projects"))
    if only:
        wanted = {str(x) for x in only}
        projects = [p for p in projects if str(p.get("identifier")) in wanted or str(p["id"]) in wanted]
    scopes = [{"project_id": p.get("identifier") or p["id"]} for p in projects] if only else [{}]
    issues = lambda q: [i for s in scopes for i in client.pages("/issues.json", {**q, **s}, items="issues")]
    return {
        "user": (client.get("/users/current.json") or {}).get("user") or {},
        "projects": projects,
        "open": issues({"status_id": "open", "sort": "updated_on:desc"}),
        "closed": issues({"status_id": "closed", "closed_on": ">=" + since}),
    }


def fetch_mine(client):
    """The light download everyone does: who I am and my open tasks (no projects, no other people's tasks)."""
    return {"user": (client.get("/users/current.json") or {}).get("user") or {},
            "open": list(client.pages("/issues.json", {"status_id": "open", "assigned_to_id": "me"}, items="issues"))}


FILTERS = {"--progetto": "project_id", "--stato": "status_id", "--persona": "assigned_to_id", "--scadenza": "due_date",
           "--testo": "subject"}
STATES = {"aperte": "open", "chiuse": "closed", "tutte": "*"}


def parse_filters(args):
    """`--progetto sito --persona me …` → Redmine query parameters. ValueError on an unknown filter or value.
    No filters = my open tasks."""
    q, it = {"status_id": "open"}, iter(args)
    for a in it:
        if a not in FILTERS:
            raise ValueError(f"filtro sconosciuto {a!r}: {', '.join(FILTERS)}")
        v = next(it, None)
        if v is None:
            raise ValueError(f"{a} vuole un valore")
        if a == "--stato":
            if v not in STATES:
                raise ValueError(f"--stato {', '.join(STATES)}")
            v = STATES[v]
        elif a == "--scadenza":
            if not v.isdigit():
                raise ValueError("--scadenza vuole i giorni da oggi (0 = scadute o in scadenza oggi)")
            v = "<=" + (datetime.date.today() + datetime.timedelta(days=int(v))).isoformat()
        elif a == "--testo":
            v = "~" + v
        q[FILTERS[a]] = v
    if len(q) == 1:
        q["assigned_to_id"] = "me"
    return q


def search(client, query, limit=200):
    """(tasks, truncated): a filtered query on the server, at most `limit` results."""
    found = list(client.pages("/issues.json", {**query, "sort": "due_date"}, items="issues", max_items=limit + 1))
    return [task(i) for i in found[:limit]], len(found) > limit


def _day(ts):
    return (ts or "")[:10]


def _late(issue, today):
    return bool(issue.get("due_date")) and issue["due_date"] < today.isoformat()


def task(issue):
    return {"id": issue["id"], "progetto": (issue.get("project") or {}).get("name", ""), "titolo": issue.get("subject", ""),
            "stato": (issue.get("status") or {}).get("name", ""), "persona": (issue.get("assigned_to") or {}).get("name", "—"),
            "scadenza": issue.get("due_date") or "", "fatto": f"{issue.get('done_ratio') or 0}%"}


def summarize(projects, open_issues, closed_recent, today):
    """One row per active project, most at risk first: late tasks, then open tasks."""
    rows = []
    for p in projects:
        mine = [i for i in open_issues if (i.get("project") or {}).get("id") == p["id"]]
        done = [i.get("done_ratio") or 0 for i in mine]
        last = max([_day(p.get("updated_on"))] + [_day(i.get("updated_on")) for i in mine])
        rows.append({"progetto": p["name"], "id": p.get("identifier", p["id"]), "aperte": len(mine),
                     "in_ritardo": sum(_late(i, today) for i in mine),
                     "chiuse_7g": sum((i.get("project") or {}).get("id") == p["id"] for i in closed_recent),
                     "avanzamento": f"{round(sum(done) / len(done))}%" if done else "—", "ultima_attivita": last})
    return sorted(rows, key=lambda r: (-r["in_ritardo"], -r["aperte"], r["progetto"].lower()))


def project_status(identifier, projects, open_issues, today, horizon=14):
    """One project in detail: open tasks by status and by person, late tasks, deadlines in the next `horizon` days.
    KeyError when no active project has that identifier (or id)."""
    p = next((x for x in projects if str(x.get("identifier")) == str(identifier) or str(x["id"]) == str(identifier)), None)
    if p is None:
        raise KeyError(identifier)
    mine = [i for i in open_issues if (i.get("project") or {}).get("id") == p["id"]]
    by_status, by_person = {}, {}
    for i in mine:
        s = (i.get("status") or {}).get("name", "")
        by_status[s] = by_status.get(s, 0) + 1
        who = (i.get("assigned_to") or {}).get("name", "—")
        a = by_person.setdefault(who, {"persona": who, "aperte": 0, "in_ritardo": 0})
        a["aperte"] += 1
        a["in_ritardo"] += _late(i, today)
    end = (today + datetime.timedelta(days=horizon)).isoformat()
    return {
        "progetto": p["name"],
        "per_stato": [{"stato": k, "task": v} for k, v in sorted(by_status.items(), key=lambda kv: (-kv[1], kv[0]))],
        "per_persona": sorted(by_person.values(), key=lambda a: (-a["aperte"], -a["in_ritardo"], a["persona"])),
        "in_ritardo": [task(i) for i in sorted((i for i in mine if _late(i, today)), key=lambda i: i["due_date"])],
        "prossime_scadenze": [task(i) for i in sorted((i for i in mine if i.get("due_date") and
                                                       today.isoformat() <= i["due_date"] <= end), key=lambda i: i["due_date"])],
    }


def my_tasks(data, seen=None):
    """My open tasks, soonest due first; with `seen` (seen_entries of my last look) a «novità» column: ● = changed
    or new since then."""
    me = (data.get("user") or {}).get("id")
    mine = [i for i in data.get("open", []) if (i.get("assigned_to") or {}).get("id") == me]
    changed = {c["id"] for c in changes(seen, mine)}
    return [{"novità": "●" if i["id"] in changed else "", **task(i)}
            for i in sorted(mine, key=lambda i: (i.get("due_date") or "9999", i["id"]))]


# ── what changed since I last looked ──
WATCHED = (("stato", lambda i: (i.get("status") or {}).get("name", "")),
           ("scadenza", lambda i: i.get("due_date") or ""),
           ("fatto", lambda i: f"{i.get('done_ratio') or 0}%"),
           ("priorità", lambda i: (i.get("priority") or {}).get("name", "")),
           ("assegnata", lambda i: (i.get("assigned_to") or {}).get("name", "—")))


def seen_entries(issues):
    """{id: what I saw}: the update time and the few fields whose change is worth saying (no titles, no text)."""
    return {str(i["id"]): {"aggiornata": i.get("updated_on") or "", **{k: get(i) for k, get in WATCHED}}
            for i in issues}


def field_changes(seen, issue):
    return [f"{k}: {seen[k] or '—'} → {get(issue) or '—'}" for k, get in WATCHED
            if k in seen and seen[k] != get(issue) and not (k == "priorità" and not get(issue))]


def changes(seen, issues):
    """The tasks changed or new since `seen`; None (never looked) = nothing: that look is the baseline."""
    if seen is None:
        return []
    out = []
    for i in issues:
        was = seen.get(str(i["id"]))
        if was is not None and was.get("aggiornata") == (i.get("updated_on") or ""):
            continue
        what = "nuova per te" if was is None else "; ".join(field_changes(was, i)) or "aggiornata (note o altri campi)"
        out.append({"id": i["id"], "progetto": (i.get("project") or {}).get("name", ""), "titolo": i.get("subject", ""),
                    "cosa": what, "aggiornata": _day(i.get("updated_on"))})
    return sorted(out, key=lambda c: (c["aggiornata"], c["id"]), reverse=True)


# ── one issue in detail ──
URGENT, HIGH = {"urgente", "immediata", "urgent", "immediate"}, {"alta", "high"}
RELATIONS = {"relates": "collegata a", "duplicates": "duplica", "duplicated": "duplicata da", "blocks": "blocca",
             "blocked": "bloccata da", "precedes": "precede", "follows": "segue", "copied_to": "copiata in",
             "copied_from": "copiata da"}


def fetch_issue(client, number):
    """(issue with notes, attachments, relations and sub-tasks; {status id: name}) — standard REST API."""
    issue = client.get(f"/issues/{number}.json", {"include": "journals,attachments,relations,children"})["issue"]
    try:
        statuses = {s["id"]: s["name"] for s in client.get("/issue_statuses.json").get("issue_statuses", [])}
    except Exception:  # only used to name status changes: ids are fine without it
        statuses = {}
    return issue, statuses


def readable(text):
    """Redmine text (Textile or Markdown) as plain readable lines [(line, tone)]: headings ▌, lists •, code │,
    links «text (url)», emphasis markers dropped."""
    import re
    text = (text or "").replace("\r\n", "\n")
    textile = bool(re.search(r'^h[1-6]\.\s|"[^"]+":https?://|<pre>', text, re.M))
    out, code = [], False
    for line in text.split("\n"):
        s = line.rstrip()
        if s.strip() in ("<pre>", "</pre>", "```") or s.strip().startswith("```") or s.strip().startswith("<pre"):
            code = not code if not s.strip().startswith("</") else False
            continue
        if code:
            out.append(("  │ " + s, "dim"))
            continue
        m = re.match(r"h[1-6]\.\s+(.*)", s) if textile else re.match(r"#{1,6}\s+(.*)", s)
        if m:
            out.append(("▌ " + m.group(1).strip(), None))
            continue
        m = re.match(r"(\*+|#+)\s+(.*)", s) if textile else re.match(r"(\s*)[-*+]\s+(.*)", s)
        if m:
            depth = len(m.group(1)) - 1 if textile else len(m.group(1)) // 2
            s = "  " * depth + ("• " if not textile or m.group(1)[0] == "*" else "– ") + m.group(2)
        s = re.sub(r'"([^"]+)":(\S+)', r"\1 (\2)", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"(?<![\w*])\*(\S(?:.*?\S)?)\*(?![\w*])", r"\1", s) if textile else s
        s = re.sub(r"@([^@\s][^@]*)@", r"\1", s) if textile else re.sub(r"`([^`]+)`", r"\1", s)
        if s or (out and out[-1][0]):
            out.append((s, None))
    while out and not out[-1][0]:
        out.pop()
    return out


def _size(n):
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{round(n / 1024)} KB"


def _journal(j, statuses, names):
    """One note or change as lines [(text, tone)]: the text (warn when it mentions me), then the changed fields."""
    items = [(t, "warn" if any(n.lower() in (j.get("notes") or "").lower() for n in names) else tone)
             for t, tone in readable(j.get("notes"))]
    for d in j.get("details") or []:
        old, new = d.get("old_value"), d.get("new_value")
        if d.get("name") == "status_id":
            name = lambda v: statuses.get(int(v), v) if v and str(v).isdigit() else v
            items.append((f"stato: {name(old)} → {name(new)}", None))
        elif d.get("name") == "done_ratio":
            items.append((f"fatto: {old or 0}% → {new or 0}%", None))
        elif d.get("name") == "assigned_to_id":
            items.append(("assegnatario cambiato", None))
        else:
            items.append((f"{d.get('name')}: {old or '—'} → {new or '—'}", "dim"))
    return items


def issue_detail(issue, me, today, statuses=None, seen=None):
    """A Detail for one issue: key fields with meaning colors (late, urgent, mine, still, mentions me), the
    description, notes and changes most recent first (older ones folded), relations and sub-tasks, attachments.
    seen = what I saw last time (seen_entries): if it changed since, «Cosa è cambiato» comes first (the changed
    fields) and the notes after it are marked new (●, n/N jump between them)."""
    from pleiadi_cli_builder import Detail
    statuses, me = statuses or {}, me or {}
    is_open = not (issue.get("status") or {}).get("is_closed", False)
    due, prio = issue.get("due_date") or "", (issue.get("priority") or {}).get("name", "")
    soon = (today + datetime.timedelta(days=3)).isoformat()
    still = (today - datetime.date.fromisoformat(_day(issue.get("updated_on")) or today.isoformat())).days
    who = issue.get("assigned_to") or {}
    fields = [("stato", (issue.get("status") or {}).get("name", ""), None),
              ("priorità", prio, "alarm" if prio.lower() in URGENT else "warn" if prio.lower() in HIGH else None),
              ("assegnata", who.get("name", "—"), "ok" if who.get("id") and who.get("id") == me.get("id") else None),
              ("scadenza", due or "—", ("alarm" if due < today.isoformat() else "warn" if due <= soon else None)
               if due and is_open else None),
              ("fatto", f"{issue.get('done_ratio') or 0}%", None)]
    if issue.get("fixed_version"):
        fields.append(("versione", issue["fixed_version"].get("name", ""), None))
    fields += [("autore", (issue.get("author") or {}).get("name", ""), None),
               ("creata", _day(issue.get("created_on")), "dim"),
               ("aggiornata", _day(issue.get("updated_on")) + (f" · ferma da {still} giorni" if is_open and still > 14 else ""),
                "warn" if is_open and still > 14 else None)]
    names = [f"@{me['login']}"] if me.get("login") else []
    if me.get("firstname"):
        names.append(f"{me['firstname']} {me.get('lastname', '')}".strip())
    sections = [("Descrizione", readable(issue.get("description")) or [("—", "dim")])]
    changed = seen and seen.get("aggiornata") != (issue.get("updated_on") or "")
    shown = fresh = 0
    for j in reversed(issue.get("journals") or []):
        items = _journal(j, statuses, names)
        if items:  # a note after my last look: its lines are new (●, n/N), never folded
            new = bool(changed and (j.get("created_on") or "") > seen.get("aggiornata", ""))
            fresh += new
            sections.append((f"Nota · {_day(j.get('created_on'))} · {(j.get('user') or {}).get('name', '')}", items,
                             shown >= 3 and not new, new))
            shown += 1
    if changed:
        news = [(t, None) for t in field_changes(seen, issue)]
        notes = [(f"{fresh} note nuove più sotto: n le scorre", "dim")] if fresh else []
        sections.insert(0, ("Cosa è cambiato", news + notes or [("aggiornata (campi non mostrati qui)", "dim")], False,
                            len(news)))
    rel = [(f"{RELATIONS.get(r.get('relation_type'), r.get('relation_type'))} "
            f"#{r['issue_to_id'] if r.get('issue_id') == issue['id'] else r.get('issue_id')}", None)
           for r in issue.get("relations") or []]
    rel += [(f"sotto-task #{c['id']} {c.get('subject', '')}", None) for c in issue.get("children") or []]
    if rel:
        sections.append(("Relazioni e sotto-task", rel))
    if issue.get("attachments"):
        sections.append(("Allegati", [(f"{a.get('filename')} · {_size(a.get('filesize') or 0)}", None)
                                      for a in issue["attachments"]]))
    return Detail(f"#{issue['id']} · {issue.get('subject', '')} · {(issue.get('project') or {}).get('name', '')}",
                  fields, sections, legend={"alarm": "in ritardo o urgente", "warn": "attenzione (vicina, ferma, ti cita)",
                                            "ok": "assegnata a te"})


def by_state(issues, states=None):
    """[{stato, task}]: with `states` ({label: [tracker status names]} from the config, e.g. {"in corso":
    ["In Progress"], "in attesa": ["Pending"], "risolte": ["Resolved"]}) the labels in that order, then «altro» for
    the rest; without, the tracker's names, most first. Names match in any case; empty labels are left out.
    ValueError when the map isn't {label: name or [names]}."""
    names = lambda i: (i.get("status") or {}).get("name", "—")
    if not states:
        counts = {}
        for i in issues:
            counts[names(i)] = counts.get(names(i), 0) + 1
        return [{"stato": k, "task": n} for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    if not isinstance(states, dict) or not all(isinstance(v, (str, list)) for v in states.values()):
        raise ValueError('"stati" va scritto {"etichetta": ["Nome stato", …]}')
    label = {n.lower(): k for k, v in states.items() for n in ([v] if isinstance(v, str) else v)}
    counts = dict.fromkeys(list(states) + ["altro"], 0)
    for i in issues:
        counts[label.get(names(i).lower(), "altro")] += 1
    return [{"stato": k, "task": n} for k, n in counts.items() if n]


def my_indicators(data, today, states=None):
    """The few numbers everyone wants above their own open tasks: how many, late, due within 7 days, still for
    more than 14 days, by status (grouped by `states`, see by_state), by priority and by project."""
    me = (data.get("user") or {}).get("id")
    mine = [i for i in data.get("open", []) if (i.get("assigned_to") or {}).get("id") == me]
    week = (today + datetime.timedelta(days=7)).isoformat()
    still = (today - datetime.timedelta(days=14)).isoformat()
    count = lambda key: sorted(({k: sum(key(i) == k for i in mine)} for k in {key(i) for i in mine}),
                               key=lambda d: (-list(d.values())[0], list(d)[0]))
    by_prio = [{"priorità": k, "task": n} for d in count(lambda i: (i.get("priority") or {}).get("name", "—"))
               for k, n in d.items()]
    projects = {}
    for i in mine:
        p = projects.setdefault((i.get("project") or {}).get("name", "—"), {"task": 0, "in_ritardo": 0})
        p["task"] += 1
        p["in_ritardo"] += _late(i, today)
    return {"aperte": len(mine), "in_ritardo": sum(_late(i, today) for i in mine),
            "in_scadenza_7g": sum(bool(i.get("due_date")) and today.isoformat() <= i["due_date"] <= week for i in mine),
            "ferme_14g": sum(_day(i.get("updated_on")) < still for i in mine),
            "per_stato": by_state(mine, states),
            "per_priorita": by_prio,
            "per_progetto": [{"progetto": k, **v} for k, v in sorted(projects.items(), key=lambda kv: (-kv[1]["task"], kv[0]))]}
