"""pm-kit against a fake Redmine with invented data (never a real tracker in tests)."""
import datetime, http.server, io, json, os, sys, tempfile, threading, unittest, urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
from pleiadi_cli_builder import credentials, term
from pleiadi_cli_builder.contract import tests as contract_tests
from pm_kit import redmine
from pm_kit.__main__ import app

TODAY = datetime.date.today()
D = lambda days: (TODAY + datetime.timedelta(days=days)).isoformat()
KEY = "fake-api-key-for-tests-0001"
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


class FakeRedmine(http.server.BaseHTTPRequestHandler):
    down = False  # True: every request fails (proves a run used the snapshot)

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
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if url.path == "/users/current.json":
            return self.send(200, {"user": {"id": 7, "login": "anna", "firstname": "Anna", "lastname": "Prova"}})
        if url.path == "/projects.json":
            items, key = PROJECTS, "projects"
        elif url.path == "/issues.json":
            st = q.get("status_id", "open")
            items = [i for i in ISSUES if st == "*" or (st == "closed") == i["status"]["is_closed"]]
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
            json.dump({"url": f"http://127.0.0.1:{self.srv.server_port}", "user": "anna"}, f)
        credentials.KEYCHAIN = credentials.MemoryOnly()
        credentials.keychain().set("pm-kit.redmine", "anna", KEY)
        self.env = mock.patch.dict(os.environ, {"PM_KIT_CONFIG": cfg})
        self.env.start()
        app.cache_dir = os.path.join(self.home, "cache")

    def tearDown(self):
        self.env.stop()
        credentials.KEYCHAIN = credentials.MemoryOnly()
        term.SECRETS.clear()

    def test_progetti_json_and_snapshot(self):
        code, out, err = quiet(lambda: app.main(["progetti", "--json"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["progetto"], "Sito nuovo")
        self.assertNotIn(KEY, out + err)
        FakeRedmine.down = True  # second run: from the snapshot, no request
        try:
            code, out, err = quiet(lambda: app.main(["progetti"]))
            self.assertEqual(code, 0, err)
            self.assertIn("Sito nuovo", out)
            self.assertIn("istantanea del", out)
        finally:
            FakeRedmine.down = False

    def test_stato_and_mie(self):
        code, out, err = quiet(lambda: app.main(["stato", "sito", "--json", "--aggiorna"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["progetto"], "Sito nuovo")
        code, out, err = quiet(lambda: app.main(["mie", "--json"]))
        self.assertEqual(sorted(t["id"] for t in json.loads(out)), [101, 103])
        code, out, err = quiet(lambda: app.main(["stato", "nessuno"]))
        self.assertEqual(code, 1)

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
