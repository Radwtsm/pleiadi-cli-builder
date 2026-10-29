"""pm-kit against a fake Redmine with invented data (never a real tracker in tests)."""
import datetime, http.server, io, json, os, sys, tempfile, threading, unittest, urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PCB_GLYPHS"] = "full"  # the tests compare symbols: the same set in every terminal
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
from pleiadi_cli_builder import credentials, term
from pleiadi_cli_builder.contract import tests as contract_tests
from pm_kit import redmine
from pm_kit.__main__ import app

TODAY = datetime.date.today()
D = lambda days: (TODAY + datetime.timedelta(days=days)).isoformat()
KEY = "".join("0123456789abcdef"[i % 16] for i in range(40))  # invented: 40 hex, like a Redmine key
PROJECTS = [{"id": 1, "name": "Sito nuovo", "identifier": "sito", "status": 1, "updated_on": D(-1) + "T10:00:00Z"},
            {"id": 2, "name": "App interna", "identifier": "app", "status": 1, "updated_on": D(-20) + "T10:00:00Z"},
            {"id": 3, "name": "Archivio", "identifier": "archivio", "status": 1, "updated_on": D(-90) + "T10:00:00Z"}]
U = lambda i, n: {"id": i, "name": n}
ISSUES = [  # (project, status, assignee, due, done, closed_on)
    dict(id=101, project=U(1, "Sito nuovo"), status={"name": "In corso", "is_closed": False}, assigned_to=U(7, "Anna Prova"),
         subject="Home page", due_date=D(-3), done_ratio=50, updated_on=D(-1) + "T09:00:00Z"),
    dict(id=102, project=U(1, "Sito nuovo"), status={"name": "Nuova", "is_closed": False}, assigned_to=U(8, "Bruno Test"),
         subject="Contatti", due_date=D(5), done_ratio=0, updated_on=D(-2) + "T09:00:00Z"),
    dict(id=103, project=U(1, "Sito nuovo"), status={"name": "In corso", "is_closed": False}, assigned_to=U(7, "Anna Prova"),
         subject="Menu", due_date=D(-1), done_ratio=80, updated_on=D(-1) + "T08:00:00Z"),
    dict(id=201, project=U(2, "App interna"), status={"name": "Nuova", "is_closed": False}, subject="Login",
         due_date=None, done_ratio=0, updated_on=D(-20) + "T09:00:00Z"),
    dict(id=104, project=U(1, "Sito nuovo"), status={"name": "Chiusa", "is_closed": True}, assigned_to=U(8, "Bruno Test"),
         subject="Logo", due_date=D(-10), done_ratio=100, updated_on=D(-2) + "T09:00:00Z", closed_on=D(-2) + "T09:00:00Z"),
]


DETAIL = {"issue": dict(ISSUES[0], priority={"name": "Urgente"}, author=U(8, "Bruno Test"),
                         fixed_version={"name": "1.0"}, created_on=D(-40) + "T09:00:00Z", updated_on=D(-20) + "T09:00:00Z",
                         description='h2. Obiettivo\n\n* home veloce\n* menu chiaro\n\nVedi "la bozza":https://example.test/bozza\n'
                                     '<pre>\nnpm run build\n</pre>',
                         journals=[{"id": 1, "user": U(8, "Bruno Test"), "created_on": D(-30) + "T09:00:00Z",
                                    "notes": "", "details": [{"property": "attr", "name": "status_id", "old_value": "1",
                                                              "new_value": "2"}]},
                                   {"id": 2, "user": U(8, "Bruno Test"), "created_on": D(-21) + "T09:00:00Z",
                                    "notes": "@anna puoi guardare il menu?", "details": []}],
                         attachments=[{"filename": "bozza.png", "filesize": 123456}],
                         relations=[{"relation_type": "blocks", "issue_id": 101, "issue_to_id": 102}],
                         children=[{"id": 105, "subject": "Icone"}])}
STATUSES = {"issue_statuses": [{"id": 1, "name": "Nuova"}, {"id": 2, "name": "In corso"}]}


class FakeRedmine(http.server.BaseHTTPRequestHandler):
    down = False  # True: every request fails (proves a run used the snapshot)
    paths = []  # every request path (proves what a command did NOT download)

    def log_message(self, *a):
        pass

    def send(self, code, obj=None):
        self.send_response(code)
        self.end_headers()
        if obj is not None:
            self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        if FakeRedmine.down:
            return self.send(500)
        if self.headers.get("X-Redmine-API-Key") != KEY:
            return self.send(401)
        FakeRedmine.paths.append(self.path.split("?")[0])
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if url.path == "/issues/101.json":
            if "journals" not in q.get("include", ""):
                return self.send(400)
            d = json.loads(json.dumps(DETAIL))
            for a in d["issue"]["attachments"]:  # Redmine gives absolute links to its own host
                a["content_url"] = f"http://{self.headers['Host']}/attachments/download/1/{a['filename']}"
            return self.send(200, d)
        if url.path.startswith("/attachments/download/"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"PNG-fake" * 100)
            return
        if url.path == "/issue_statuses.json":
            return self.send(200, STATUSES)
        if url.path.startswith("/issues/") and url.path.endswith(".json"):
            return self.send(404)
        if url.path == "/users/current.json":
            return self.send(200, {"user": {"id": 7, "login": "anna", "firstname": "Anna", "lastname": "Prova"}})
        if url.path == "/projects.json":
            items, key = PROJECTS, "projects"
        elif url.path == "/issues.json":
            st = q.get("status_id", "open")
            items = [i for i in ISSUES if st == "*" or (st == "closed") == i["status"]["is_closed"]]
            if q.get("project_id"):
                p = next(x for x in PROJECTS if q["project_id"] in (x["identifier"], str(x["id"])))
                items = [i for i in items if i["project"]["id"] == p["id"]]
            if q.get("subject", "").startswith("~"):
                items = [i for i in items if q["subject"][1:].lower() in i["subject"].lower()]
            if q.get("due_date", "").startswith("<="):
                items = [i for i in items if i.get("due_date") and i["due_date"] <= q["due_date"][2:]]
            if q.get("assigned_to_id") == "me":
                items = [i for i in items if i.get("assigned_to", {}).get("id") == 7]
            if q.get("closed_on", "").startswith(">="):
                items = [i for i in items if (i.get("closed_on") or "")[:10] >= q["closed_on"][2:]]
            key = "issues"
        else:
            return self.send(404)
        off, lim = int(q.get("offset", 0)), int(q.get("limit", 25))
        self.send(200, {key: items[off:off + lim], "total_count": len(items), "offset": off, "limit": lim})


class Quiet(http.server.HTTPServer):
    def handle_error(self, *a):
        pass


def quiet(fn):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        r = fn()
    return r, out.getvalue(), err.getvalue()


class Calculations(unittest.TestCase):
    def test_projects_by_risk(self):
        rows = redmine.summarize(PROJECTS, [i for i in ISSUES if not i["status"]["is_closed"]],
                                 [i for i in ISSUES if i["status"]["is_closed"]], TODAY)
        self.assertEqual([r["progetto"] for r in rows], ["Sito nuovo", "App interna", "Archivio"])
        sito = rows[0]
        self.assertEqual((sito["aperte"], sito["in_ritardo"], sito["chiuse_7g"], sito["avanzamento"]), (3, 2, 1, "43%"))
        self.assertEqual(rows[1]["ultima_attivita"], D(-20))
        self.assertEqual(rows[2]["aperte"], 0)

    def test_project_status(self):
        st = redmine.project_status("sito", PROJECTS, [i for i in ISSUES if not i["status"]["is_closed"]], TODAY)
        self.assertEqual(st["per_stato"], [{"stato": "In corso", "task": 2}, {"stato": "Nuova", "task": 1}])
        self.assertEqual(st["per_persona"][0], {"persona": "Anna Prova", "aperte": 2, "in_ritardo": 2})
        self.assertEqual([t["id"] for t in st["in_ritardo"]], [101, 103])
        self.assertEqual([t["id"] for t in st["prossime_scadenze"]], [102])
        with self.assertRaises(KeyError):
            redmine.project_status("nessuno", PROJECTS, [], TODAY)


class IssueView(unittest.TestCase):
    def test_readable_text(self):
        lines = [t for t, _ in redmine.readable(DETAIL["issue"]["description"])]
        self.assertIn("▌ Obiettivo", lines)
        self.assertIn("• home veloce", lines)
        self.assertIn("Vedi la bozza (https://example.test/bozza)", lines)
        self.assertIn("  │ npm run build", lines)
        md = [t for t, _ in redmine.readable("## Titolo\n- uno\n[doc](https://example.test/d) e **forte**\n```\ncodice\n```")]
        self.assertEqual(md, ["▌ Titolo", "• uno", "doc (https://example.test/d) e forte", "  │ codice"])

    def test_detail_highlights(self):
        d = redmine.issue_detail(DETAIL["issue"], {"id": 7, "login": "anna", "firstname": "Anna", "lastname": "Prova"},
                                 TODAY, {1: "Nuova", 2: "In corso"})
        tones = {label: tone for label, _, tone in d.fields}
        self.assertEqual(tones["scadenza"], "alarm")  # 3 days late
        self.assertEqual(tones["priorità"], "alarm")
        self.assertEqual(tones["assegnata"], "ok")  # to me
        self.assertEqual(tones["aggiornata"], "warn")  # still for 20 days
        titles = [t for t, _, _ in d.sections]
        self.assertEqual(titles[0], "Descrizione")
        notes = [s for s in d.sections if s[0].startswith("Nota")]
        self.assertTrue(notes[0][0].endswith("Bruno Test") and D(-21) in notes[0][0])  # most recent first
        self.assertEqual(notes[0][1][0][1], "warn")  # mentions me
        self.assertIn(("stato: Nuova → In corso", None), notes[1][1])
        self.assertIn("Relazioni e sotto-task", titles)
        self.assertIn(("bozza.png · 121 KB", None), dict((t, i) for t, i, _ in d.sections)["Allegati"])


class Indicators(unittest.TestCase):
    def test_my_indicators(self):
        mine = lambda i, due, upd, prio, proj: {"id": i, "project": U(proj, f"P{proj}"), "status": {"name": "In corso"},
                                                "assigned_to": U(7, "Anna"), "due_date": due, "done_ratio": 0,
                                                "updated_on": D(upd) + "T09:00:00Z", "priority": {"name": prio}}
        data = {"user": {"id": 7}, "open": [mine(1, D(-2), -1, "Alta", 1), mine(2, D(3), -30, "Normale", 1),
                                            mine(3, None, -2, "Normale", 2), mine(4, D(10), -1, "Urgente", 2),
                                            dict(mine(5, D(-1), -1, "Normale", 1), assigned_to=U(8, "Bruno"))]}
        ind = redmine.my_indicators(data, TODAY)
        self.assertEqual((ind["aperte"], ind["in_ritardo"], ind["in_scadenza_7g"], ind["ferme_14g"]), (4, 1, 1, 1))
        self.assertEqual(ind["per_priorita"][0], {"priorità": "Normale", "task": 2})
        self.assertEqual(ind["per_progetto"], [{"progetto": "P1", "task": 2, "in_ritardo": 1},
                                               {"progetto": "P2", "task": 2, "in_ritardo": 0}])


class Commands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Quiet(("127.0.0.1", 0), FakeRedmine)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.home = tempfile.mkdtemp()
        cfg = os.path.join(self.home, "pm-kit.json")
        with open(cfg, "w") as f:
            json.dump({"url": f"http://127.0.0.1:{self.srv.server_port}", "user": "anna", "vpn": None, "cartella_download": os.path.join(self.home, "dl")}, f)
        credentials.KEYCHAIN = credentials.MemoryOnly()
        credentials.keychain().set("pm-kit.redmine", "anna", KEY)
        self.env = mock.patch.dict(os.environ, {"PM_KIT_CONFIG": cfg})
        self.env.start()
        app.cache_dir = os.path.join(self.home, "cache")
        app._memory.clear()  # each test starts with no in-memory copy

    def tearDown(self):
        self.env.stop()
        credentials.KEYCHAIN = credentials.MemoryOnly()
        term.SECRETS.clear()

    def test_progetti_json_and_snapshot(self):
        code, out, err = quiet(lambda: app.main(["progetti", "--tutti", "--json"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["progetto"], "Sito nuovo")
        self.assertNotIn(KEY, out + err)
        FakeRedmine.down = True  # second run: from the snapshot, no request
        try:
            code, out, err = quiet(lambda: app.main(["progetti", "--tutti"]))
            self.assertEqual(code, 0, err)
            self.assertIn("Sito nuovo", out)
            self.assertIn("istantanea del", out)
        finally:
            FakeRedmine.down = False

    def test_stato_and_mie(self):
        code, out, err = quiet(lambda: app.main(["stato", "sito", "--tutti", "--json", "--aggiorna"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["progetto"], "Sito nuovo")
        code, out, err = quiet(lambda: app.main(["mie", "--json"]))
        self.assertEqual(sorted(t["id"] for t in json.loads(out)), [101, 103])
        code, out, err = quiet(lambda: app.main(["stato", "nessuno", "--tutti"]))
        self.assertEqual(code, 1)

    def test_default_is_only_my_tasks(self):
        FakeRedmine.paths.clear()
        code, out, err = quiet(lambda: app.main(["mie", "--json"]))
        self.assertEqual(sorted(t["id"] for t in json.loads(out)), [101, 103])
        self.assertNotIn("/projects.json", FakeRedmine.paths)  # nothing beyond my own tasks
        code, out, err = quiet(lambda: app.main(["progetti", "--json"]))
        self.assertEqual((code, json.loads(out)), (1, []))
        self.assertIn("--tutti", err)
        self.assertNotIn("/projects.json", FakeRedmine.paths)

    def test_pm_role_needs_no_flag(self):
        self.set_config(ruolo="pm")
        code, out, err = quiet(lambda: app.main(["progetti", "--json"]))
        self.assertEqual(code, 0, err)

    def test_task_filters(self):
        code, out, err = quiet(lambda: app.main(["task", "--progetto", "sito", "--persona", "me", "--json"]))
        self.assertEqual(sorted(t["id"] for t in json.loads(out)), [101, 103])
        code, out, err = quiet(lambda: app.main(["task", "--testo", "menu", "--json"]))
        self.assertEqual([t["id"] for t in json.loads(out)], [103])
        code, out, err = quiet(lambda: app.main(["task", "--scadenza", "0", "--json"]))  # due by today: late ones
        self.assertEqual(sorted(t["id"] for t in json.loads(out)), [101, 103])
        code, out, err = quiet(lambda: app.main(["task", "--colore", "blu"]))
        self.assertEqual(code, 2)

    def test_refresh_not_too_often(self):
        quiet(lambda: app.main(["progetti", "--tutti"]))
        FakeRedmine.paths.clear()
        code, out, err = quiet(lambda: app.main(["progetti", "--tutti", "--aggiorna"]))
        self.assertIn("al massimo ogni", " ".join(out.split()))
        self.assertEqual(FakeRedmine.paths, [])

    def test_issue_command(self):
        code, out, err = quiet(lambda: app.main(["issue", "101", "--json"]))
        self.assertEqual(code, 0, err)
        d = json.loads(out)
        self.assertEqual(d["fields"]["stato"], "In corso")
        self.assertIn("Allegati", d["sections"])
        code, out, err = quiet(lambda: app.main(["issue", "999"]))
        self.assertEqual(code, 1)
        code, out, err = quiet(lambda: app.main(["issue", "abc"]))
        self.assertEqual(code, 2)

    def test_setup_keeps_hand_written_entries(self):
        cfg = os.environ["PM_KIT_CONFIG"]
        with open(cfg, "w") as f:
            json.dump({"vpn": {"up": ["vpn-cli", "up"]}, "pin_sha256": "ab" * 32, "pin_expires": "2099-01-01"}, f)
        answers = iter(["https://redmine.example", "anna"])
        confirms = iter([True, True])  # keep a local copy; not a PM
        with mock.patch("pleiadi_cli_builder.term.Screen.ask", lambda self, q, d="": next(answers)), \
             mock.patch("pleiadi_cli_builder.term.Screen.confirm", lambda self, q, y=None, n=None: next(confirms)):
            from pm_kit.__main__ import steps
            from pleiadi_cli_builder import Screen
            steps(Screen("t"))[0].apply()
        with open(cfg) as f:
            c = json.load(f)
        self.assertEqual(c["url"], "https://redmine.example")
        self.assertEqual(c["vpn"], {"up": ["vpn-cli", "up"]})  # kept
        self.assertEqual(c["pin_expires"], "2099-01-01")

    def test_setup_asks_for_the_vpn_before_trying(self):
        from pm_kit.__main__ import steps
        from pleiadi_cli_builder import Screen
        names = [s.name for s in steps(Screen("t"))]
        self.assertLess(names.index("VPN"), names.index("Redmine risponde"))
        self.set_config(vpn={"up": ["a"], "down": ["b"], "status": ["c"]})
        self.assertTrue(steps(Screen("t"))[names.index("VPN")].check()[0])

    def test_mie_shows_indicators_and_riepilogo_json(self):
        code, out, err = quiet(lambda: app.main(["mie"]))
        flat = " ".join(out.split())
        self.assertIn("2 aperte", flat)
        self.assertIn("2 in ritardo", flat)
        code, out, err = quiet(lambda: app.main(["riepilogo", "--json"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["aperte"], 2)

    def test_wrong_key_is_asked_again_on_the_spot(self):
        credentials.keychain().set("pm-kit.redmine", "anna", "f" * 40)  # stored but refused (401)
        with mock.patch("pleiadi_cli_builder.term.Screen.interactive", new=True), \
             mock.patch("pleiadi_cli_builder.term.Screen.confirm", lambda self, q, y=None, n=None: True), \
             mock.patch("pleiadi_cli_builder.term.Screen.secret_input", lambda self, q: KEY):
            code, out, err = quiet(lambda: app.main(["mie"]))
        self.assertEqual(code, 0, out + err)
        self.assertIn("Home page", out)
        self.assertEqual(credentials.keychain().get("pm-kit.redmine", "anna"), KEY)

    def test_wrong_key_without_terminal_says_how(self):
        credentials.keychain().set("pm-kit.redmine", "anna", "f" * 40)
        code, out, err = quiet(lambda: app.main(["mie"]))
        self.assertEqual(code, 1)
        self.assertIn("pm-kit setup", out + err)

    def test_attachments_into_issue_folder(self):
        dl = os.path.join(self.home, "scaricati")
        self.set_config(cartella_download=dl)
        code, out, err = quiet(lambda: app.main(["allegati", "101", "--prova"]))
        self.assertEqual(code, 0, err)
        self.assertIn("bozza.png", out)
        self.assertFalse(os.path.exists(dl))
        code, out, err = quiet(lambda: app.main(["allegati", "101"]))
        self.assertEqual(code, 0, out + err)
        with open(os.path.join(dl, "101", "bozza.png"), "rb") as f:
            self.assertEqual(f.read(8), b"PNG-fake")
        self.assertIn(os.path.join(dl, "101"), out)

    def test_issue_view_actions(self):
        from pm_kit.__main__ import issue_actions
        from pleiadi_cli_builder import credentials as cr
        got = []
        cr.CLIPBOARD = {"read": lambda: "", "clear": lambda: None, "write": got.append}
        try:
            acts = issue_actions(DETAIL["issue"])
            self.assertEqual(sorted(acts), ["c", "d"])
            acts["c"][1](None)
            self.assertEqual(got, ["#101"])
        finally:
            cr.CLIPBOARD = None

    def test_setup_asks_for_download_folder(self):
        from pm_kit.__main__ import steps
        from pleiadi_cli_builder import Screen
        names = [s.name for s in steps(Screen("t"))]
        self.assertIn("cartella per gli allegati", names)

    def set_config(self, **kv):
        cfg = os.environ["PM_KIT_CONFIG"]
        with open(cfg) as f:
            c = json.load(f)
        c.update(kv)
        with open(cfg, "w") as f:
            json.dump(c, f)

    def test_only_some_projects(self):
        self.set_config(progetti=["app"])
        code, out, err = quiet(lambda: app.main(["progetti", "--tutti", "--json", "--aggiorna"]))
        self.assertEqual([r["progetto"] for r in json.loads(out)], ["App interna"])

    def test_local_copy_off_writes_nothing(self):
        self.set_config(copia_locale=False)
        code, out, err = quiet(lambda: app.main(["progetti", "--tutti"]))
        self.assertEqual(code, 0, err)
        self.assertIn("ogni avvio riscarica", " ".join(out.split()))
        self.assertFalse(os.path.exists(app.cache_dir))

    def test_local_copy_on_info_and_delete(self):
        self.set_config(copia_locale=True)
        quiet(lambda: app.main(["progetti", "--tutti"]))
        code, out, err = quiet(lambda: app.main(["doctor"]))
        self.assertIn("redmine.json", out)
        self.assertIn("presa il", out)
        code, out, err = quiet(lambda: app.main(["copia", "cancella", "--prova"]))
        self.assertTrue(os.path.exists(os.path.join(app.cache_dir, "redmine.json")))
        code, out, err = quiet(lambda: app.main(["copia", "cancella"]))
        self.assertFalse(os.path.exists(os.path.join(app.cache_dir, "redmine.json")))
        quiet(lambda: app.main(["copia", "no"]))
        with open(os.environ["PM_KIT_CONFIG"]) as f:
            self.assertIs(json.load(f)["copia_locale"], False)

    def test_doctor(self):
        code, out, err = quiet(lambda: app.main(["doctor"]))
        self.assertEqual(code, 0, out + err)
        credentials.keychain().set("pm-kit.redmine", "anna", "wrong-key-000000000000")
        code, out, err = quiet(lambda: app.main(["doctor"]))
        self.assertEqual(code, 1)
        self.assertIn("401", out + err)


credentials.KEYCHAIN = credentials.MemoryOnly()  # never the real keychain in tests
Contract = contract_tests(app)

if __name__ == "__main__":
    unittest.main()
