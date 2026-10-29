"""Redmine for project managers: one read-only fetch (standard REST API) and pure calculations on it, so the same
numbers come out of the snapshot, the tests and any other interface."""
import datetime


def fetch_all(client, today, days=7):
    """Everything the commands need, in one go (inside one VPN window): who I am, active projects, open issues,
    issues closed in the last `days`."""
    since = (today - datetime.timedelta(days=days)).isoformat()
    return {
        "user": (client.get("/users/current.json") or {}).get("user") or {},
        "projects": list(client.pages("/projects.json", {"status": 1}, items="projects")),
        "open": list(client.pages("/issues.json", {"status_id": "open", "sort": "updated_on:desc"}, items="issues")),
        "closed": list(client.pages("/issues.json", {"status_id": "closed", "closed_on": ">=" + since}, items="issues")),
    }


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


def my_tasks(data):
    me = (data.get("user") or {}).get("id")
    mine = [i for i in data.get("open", []) if (i.get("assigned_to") or {}).get("id") == me]
    return [task(i) for i in sorted(mine, key=lambda i: (i.get("due_date") or "9999", i["id"]))]
