"""pm-kit: i progetti in lavorazione su Redmine, per chi li segue (sola lettura).

Configurazione (dato, JSON): $PM_KIT_CONFIG oppure ~/.config/pm-kit/config.json
    {"url": "https://redmine.example", "user": "nome",                    obbligatori
     "copia_locale": true,                  dati tenuti sul computer tra un avvio e l'altro (false: solo in memoria)
     "progetti": ["sito", "app"],           scarica solo questi (identificativi); assente = tutti
     "vpn_minuti": 5,                       nel menu la VPN resta aperta fra le azioni, chiusa dopo questi minuti fermi
     "ruolo": "pm",                         segue i progetti: `progetti` e `stato` scaricano tutto senza --tutti
     "aggiorna_ogni_minuti": 10,            --aggiorna più ravvicinati usano la copia (meno carico su Redmine)
     "cartella_download": "~/Downloads/pm-kit",   gli allegati di una task vanno in <cartella>/<numero>/
     "stati": {"in corso": ["In Progress"], "in attesa": ["Pending"], "risolte": ["Resolved"]},
                                            negli indicatori gli stati di Redmine raggruppati così (il resto: «altro»)
     "ca_file": "...", oppure "pin_sha256": "...", "pin_expires": "AAAA-MM-GG",   certificato interno
     "vpn": {"up": [...], "down": [...], "status": [...]}}                 la VPN, aperta solo per scaricare
La chiave API sta nel portachiavi del sistema (chiesta una volta), mai nel file. Tutto si cambia da «Impostazioni»
(o `pm-kit impostazioni NOME VALORE`), senza toccare il file; «Rifai da capo» riparte da una preparazione pulita.
Novità: cosa ho visto di ogni mia task (ora di aggiornamento, stato, scadenza, fatto, priorità, assegnatario; niente
titoli né testi) sta in viste.json accanto alle copie locali: ● nella lista finché non la apro."""
import datetime, os, shlex, shutil, urllib.error, zipfile

from pleiadi_cli_builder import (KEEP, App, HTTPError, ReadOnlyClient, Setting, Step, copy_to_clipboard, credentials,
                                 edit_settings, install_launcher, pin_step, read_json, run, run_steps, secret,
                                 self_update, temporary, write_json)
from pleiadi_cli_builder import install
from pm_kit import redmine

app = App("pm-kit", title="PM kit", accent="#4a6cf7", menu_subtitle="i progetti in lavorazione")
SERVICE = "pm-kit.redmine"
ASK_KEY = "Chiave API di Redmine (Il mio account → Chiave API; Invio vuoto = dagli appunti):"
KEY_FORMAT = r"[0-9a-fA-F]{40}"  # Redmine API keys: 40 hex characters
ERRORS = (HTTPError, urllib.error.URLError, OSError, RuntimeError)
COPIES = ("redmine", "mie")  # the two local copies: everything (PM) and my tasks


def config_path():
    return os.environ.get("PM_KIT_CONFIG") or os.path.join(os.path.expanduser("~"), ".config", "pm-kit", "config.json")


def config():
    c = app.config(config_path()) or {}
    return c if c.get("url") else None


def client(cfg, token):
    return ReadOnlyClient(cfg["url"], token=token, header="X-Redmine-API-Key", scheme="", ca_file=cfg.get("ca_file"),
                          pin_sha256=cfg.get("pin_sha256"), pin_expires=cfg.get("pin_expires"))


def vpn(cfg, screen):
    """The VPN from the config (three command lines), open only around the download; none = no VPN."""
    v = cfg.get("vpn") or {}
    if not v.get("up"):
        return temporary(lambda: True, lambda: None, is_open=lambda: True)
    ok = lambda key: bool(v.get(key)) and run(*v[key], timeout=120)[0] == 0
    return temporary(lambda: ok("up"), lambda: ok("down"), is_open=lambda: ok("status"), screen=screen, label="VPN")


def why(e):
    if isinstance(e, HTTPError):
        return {401: f"HTTP 401: chiave API sbagliata o scaduta (rifai `{app.cmd('setup')}`)",
                403: "HTTP 403: la tua utenza non vede questi dati"}.get(e.status, str(e))
    return (f"Redmine non risponde ({getattr(e, 'reason', e)}): VPN accesa? indirizzo giusto? "
            f"(`{app.cmd('impostazioni')}`)")


def stored_key(cfg):
    return cfg and credentials.keychain().get(SERVICE, cfg.get("user", "default"))


def connect(screen):
    """(cfg, token) or (None, reason)."""
    cfg = config()
    if not cfg:
        return None, f"Prima `{app.cmd('setup')}`: manca {config_path()}"
    token = secret(SERVICE, cfg.get("user", "default"), screen, ASK_KEY, validate=KEY_FORMAT)
    return (cfg, token) if token else (None, f"Manca la chiave API: `{app.cmd('setup')}`")


def with_key(screen, cfg, action):
    """action(token) with the stored key; a key Redmine refuses (401) is asked again on the spot — in the menu
    the tool never closes or gets stuck on a wrong key. Without someone at the terminal: the error, as before."""
    user = cfg.get("user", "default")
    token = secret(SERVICE, user, screen, ASK_KEY, validate=KEY_FORMAT)
    for attempt in range(3):
        try:
            return action(token)
        except HTTPError as e:
            if e.status != 401 or attempt == 2 or not screen.interactive or screen.json or not screen.confirm(
                    "Redmine ha rifiutato la chiave API (sbagliata o scaduta). La reimposto adesso?",
                    "Sì, inserisco la chiave", "No, torna indietro"):
                raise
            credentials.forget(SERVICE, user)
            token = secret(SERVICE, user, screen, ASK_KEY, validate=KEY_FORMAT)
            if not token:
                raise


def download(screen, name, cfg, fetch, refresh_minutes):
    try:
        return app.snapshot(name, fetch, refresh=screen.refresh, keep=bool(cfg.get("copia_locale")), screen=screen,
                            min_refresh_minutes=cfg.get("aggiorna_ogni_minuti", refresh_minutes))
    except ERRORS as e:
        return None, why(e)


def everything(screen, args):
    """All projects and everyone's tasks (for whoever follows the projects): only when wanted — --tutti, the "pm"
    role in the config, a confirmation in the menu, or a copy already here. (data, when) or (None, reason)."""
    cfg, token = connect(screen)
    if not cfg:
        return None, token
    have = app.snapshot_info("redmine") or "redmine" in app._memory
    wanted = "--tutti" in args or cfg.get("ruolo") == "pm" or (have and not screen.refresh)
    if not wanted and screen.interactive and not screen.json:
        wanted = not screen.confirm("Questo scarica tutti i progetti e le task di tutti: è pesante e serve a chi "
                                    "segue i progetti. Cosa faccio?", f"Niente: mi bastano le mie task ({app.cmd('mie')})",
                                    "Scarica tutto")
    if not wanted:
        return None, ("Scaricare tutto Redmine serve a chi segue i progetti: aggiungi --tutti (o "
                      f"`{app.cmd('impostazioni')} ruolo pm`). Per le tue task: {app.cmd('mie')}; per cercarne altre: {app.cmd('task')} --progetto …")

    def fetch():
        with vpn(cfg, screen), screen.wait("scarico tutto da Redmine"):
            return with_key(screen, cfg, lambda t: redmine.fetch_all(client(cfg, t), datetime.date.today(),
                                                                    only=cfg.get("progetti")))
    return download(screen, "redmine", cfg, fetch, 10)


def mine(screen):
    cfg, token = connect(screen)
    if not cfg:
        return None, token

    def fetch():
        with vpn(cfg, screen), screen.wait("scarico le mie task"):
            return with_key(screen, cfg, lambda t: redmine.fetch_mine(client(cfg, t)))
    return download(screen, "mie", cfg, fetch, 2)


def seen_path():
    return os.path.join(os.path.dirname(app.cache_dir), "viste.json")


def seen():
    """What I saw of my tasks at my last look ({id: …}), None if never looked."""
    return read_json(seen_path())


def mark_seen(issues, replace=False):
    """issues looked at now; replace=True: the whole list (the first look, «tutte viste»): what is gone is dropped."""
    write_json(seen_path(), {**({} if replace else seen() or {}), **redmine.seen_entries(issues)})


def my_open(data):
    me = (data.get("user") or {}).get("id")
    return [i for i in data.get("open", []) if (i.get("assigned_to") or {}).get("id") == me]


def failed(screen, reason, empty):
    """✗ with the reason; with --json the empty value on stdout, so a pipe still gets valid JSON."""
    screen.out(screen.c(screen.theme.error, "✗") + f" {reason}")
    screen.data(empty)
    return 1


@app.command("mie", help="le task aperte assegnate a te (scarica solo quelle)", menu="Le mie task", short="Mie", effects=False,
             json=True, key="m")
def mie(screen, args):
    data, when = mine(screen)
    if data is None:
        return failed(screen, when, [])
    was = seen()
    if was is None:  # the first look is the baseline: from now on ● = changed since
        mark_seen(my_open(data), replace=True)
    rows = redmine.my_tasks(data, was)
    show_indicators(screen, indicators(data))
    if any(r["novità"] for r in rows) and not screen.json:
        screen.info(f"● = cambiata da quando l'hai vista: `{app.cmd('novita')}` dice cosa")
    i = screen.table(rows, ["novità", "id", "progetto", "titolo", "stato", "scadenza", "fatto"], {"novità": "●"}, pick=True)
    screen.info(screen.dim(app.snapshot_note(when)))
    return issue_cmd(screen, [str(rows[i]["id"])]) if i is not None else 0


def indicators(data):
    return redmine.my_indicators(data, datetime.date.today(), (config() or {}).get("stati"))


def show_indicators(screen, ind):
    tone = lambda n, code: screen.c(code, str(n)) if n else str(n)
    screen.out("    " + "   ".join([screen.bold(f"{ind['aperte']} aperte"),
                                    tone(ind["in_ritardo"], "31;1") + " in ritardo",
                                    tone(ind["in_scadenza_7g"], "33") + " in scadenza (7 gg)",
                                    tone(ind["ferme_14g"], "33") + " ferme (14+ gg)"]))
    if ind["per_progetto"]:
        screen.out("    " + screen.dim(" · ".join(f"{p['progetto']} {p['task']}" + (f" ({p['in_ritardo']} in ritardo)"
                                                                                   if p["in_ritardo"] else "")
                                              for p in ind["per_progetto"])))
    if ind.get("per_stato"):
        screen.out("    " + screen.dim("stato: " + " · ".join(f"{p['stato']} {p['task']}" for p in ind["per_stato"])))
    if ind["per_priorita"]:
        screen.out("    " + screen.dim("priorità: " + " · ".join(f"{p['priorità']} {p['task']}" for p in ind["per_priorita"])))
    screen.out("")


@app.command("novita", args="[--visto]", help="cosa è cambiato sulle tue task da quando le hai viste (--visto: segnale "
             "tutte come viste)", menu="Novità sulle mie task", short="Novità", effects=False, json=True, key="n")
def novita(screen, args):
    data, when = mine(screen)
    if data is None:
        return failed(screen, when, [])
    issues, was = my_open(data), seen()
    if was is None or "--visto" in args:
        mark_seen(issues, replace=True)
        if was is None:
            screen.info("prima volta: da adesso segno cosa cambia")
            screen.data([])
            return 0
        screen.info(f"{len(redmine.changes(was, issues))} task segnate come viste")
        return 0
    news = redmine.changes(was, issues)
    if not news and not screen.json:
        screen.info(f"{screen.theme.yes} niente di nuovo dall'ultima volta")
        return 0
    i = screen.table(news, ["id", "progetto", "titolo", "cosa", "aggiornata"], pick=True)
    screen.info(screen.dim(app.snapshot_note(when)))
    return issue_cmd(screen, [str(news[i]["id"])]) if i is not None else 0


@app.command("riepilogo", help="i numeri delle tue task aperte: in ritardo, in scadenza, ferme, per progetto",
             menu=None, effects=False, json=True)
def riepilogo(screen, args):
    data, when = mine(screen)
    if data is None:
        return failed(screen, when, {})
    try:
        ind = indicators(data)
    except ValueError as e:
        return failed(screen, f"{config_path()}: {e}", {})
    if not screen.data(ind):
        show_indicators(screen, ind)
        screen.info(screen.dim(app.snapshot_note(when)))
    return 0


@app.command("task", args="[--progetto ID] [--stato aperte|chiuse|tutte] [--persona me|ID] [--scadenza GIORNI] [--testo PAROLA]",
             help="cerca task sul server con dei filtri (nessun filtro = le mie aperte)", menu=None, effects=False,
             json=True, example=["--persona", "me"])
def task_cmd(screen, args):
    try:
        query = redmine.parse_filters(args)
    except ValueError as e:
        failed(screen, str(e), [])
        return 2
    cfg, token = connect(screen)
    if not cfg:
        return failed(screen, token, [])
    try:
        with vpn(cfg, screen), screen.wait("cerco su Redmine"):
            found, cut = with_key(screen, cfg, lambda t: redmine.search(client(cfg, t), query))
    except ERRORS as e:
        return failed(screen, why(e), [])
    if cut:
        screen.todo("Mostro le prime 200: restringi con --progetto, --stato o --testo.")
    i = screen.table(found, ["id", "progetto", "titolo", "stato", "persona", "scadenza", "fatto"], pick=True)
    return issue_cmd(screen, [str(found[i]["id"])]) if i is not None else 0


def download_dir(cfg):
    home = os.path.expanduser("~")
    return os.path.expanduser((cfg or {}).get("cartella_download") or os.path.join(home, "Downloads", "pm-kit"))


def save_attachments(screen, cfg, issue, token=None):
    """Every attachment of `issue` into <download folder>/<number>/ (read-only on the server, same host only).
    With --prova: the list of what would be written. Returns the message for the screen."""
    folder = os.path.join(download_dir(cfg), str(issue["id"]))
    files = [(a, os.path.join(folder, os.path.basename(a.get("filename") or f"allegato-{a.get('id')}")))
             for a in issue.get("attachments") or []]
    if not files:
        return "nessun allegato"
    if screen is not None and screen.dry:
        for _, dest in files:
            screen.info(f"farei: {dest}")
        return f"farei: {len(files)} file in {folder}"

    def fetch(t):
        api = client(cfg, t)
        return sum(api.download(a["content_url"], dest) for a, dest in files)
    with vpn(cfg, screen), screen.wait(f"scarico {len(files)} allegati"):
        total = with_key(screen, cfg, fetch)
    return f"{len(files)} file ({total // 1024 + 1} KB) in {folder}"


def issue_actions(issue):
    """The one-key operations of the task view."""
    def download(screen):
        return save_attachments(screen, config(), issue)
    return {"d": ("scarica gli allegati", download),
            "c": ("copia il numero", lambda screen: "copiato #%s" % issue["id"] if copy_to_clipboard(f"#{issue['id']}")
                  else "appunti non disponibili su questo computer")}


@app.command("allegati", args="NUMERO", help="scarica gli allegati di una task in <cartella_download>/<numero>/",
             menu=None, example=["101"])
def allegati(screen, args):
    if not args or not args[0].lstrip("#").isdigit():
        failed(screen, f"Uso: {app.cmd('allegati')} NUMERO", {})
        return 2
    cfg, token = connect(screen)
    if not cfg:
        return failed(screen, token, {})
    try:
        with vpn(cfg, screen):
            issue, _ = with_key(screen, cfg, lambda t: redmine.fetch_issue(client(cfg, t), args[0].lstrip("#")))
            screen.info(save_attachments(screen, cfg, issue))
    except HTTPError as e:
        return failed(screen, f"Task {args[0]} non trovata" if e.status == 404 else why(e), {})
    except (ERRORS + (ValueError,)) as e:
        return failed(screen, why(e) if not isinstance(e, ValueError) else str(e), {})
    return 0


@app.command("issue", args="NUMERO", help="una task nel dettaglio: campi, descrizione, note, relazioni, allegati",
             menu=None, effects=False, json=True, example=["101"])
def issue_cmd(screen, args):
    if not args or not args[0].lstrip("#").isdigit():
        failed(screen, f"Uso: {app.cmd('issue')} NUMERO", {})
        return 2
    number = args[0].lstrip("#")
    cfg, token = connect(screen)
    if not cfg:
        return failed(screen, token, {})
    me = (app._memory.get("mie") or read_json(os.path.join(app.cache_dir, "mie.json")) or {}).get("data", {}).get("user")
    try:
        with vpn(cfg, screen), screen.wait(f"apro la task {number}"):
            def read(t):
                api = client(cfg, t)
                return redmine.fetch_issue(api, number) + ((me or (api.get("/users/current.json") or {}).get("user")),)
            issue, statuses, me = with_key(screen, cfg, read)
    except HTTPError as e:
        return failed(screen, f"Task {number} non trovata (o non visibile per te)" if e.status == 404 else why(e), {})
    except ERRORS as e:
        return failed(screen, why(e), {})
    was = seen()
    d = redmine.issue_detail(issue, me, datetime.date.today(), statuses, (was or {}).get(str(issue["id"])))
    d.actions = issue_actions(issue)
    screen.detail(d)
    if was is not None and str(issue["id"]) in was or (issue.get("assigned_to") or {}).get("id") == (me or {}).get("id"):
        mark_seen([issue])  # opened = seen: its ● goes away
    return 0


@app.command("progetti", args="[--tutti]", help="tutti i progetti attivi, i più a rischio prima (per chi li segue: "
             "scarica tutto)", menu="Tutti i progetti (per chi li segue)", short="Progetti", effects=False, json=True, key="p")
def progetti(screen, args):
    data, when = everything(screen, args)
    if data is None:
        return failed(screen, when, [])
    rows = redmine.summarize(data["projects"], data["open"], data["closed"], datetime.date.today())
    screen.table(rows, ["progetto", "aperte", "in_ritardo", "chiuse_7g", "avanzamento", "ultima_attivita"],
                 {"in_ritardo": "in ritardo", "chiuse_7g": "chiuse 7 gg", "ultima_attivita": "ultima attività"})
    screen.info(screen.dim(app.snapshot_note(when)))
    return 0


@app.command("stato", args="PROGETTO [--tutti]", help="un progetto: per stato, per persona, ritardi, scadenze",
             effects=False, json=True, example=["sito"])
def stato(screen, args):
    if not [a for a in args if a != "--tutti"]:
        return failed(screen, f"Uso: {app.cmd('stato')} PROGETTO (l'identificativo è in `{app.cmd('progetti')} --json`)", {})
    data, when = everything(screen, args)
    if data is None:
        return failed(screen, when, {})
    try:
        st = redmine.project_status([a for a in args if a != "--tutti"][0], data["projects"], data["open"],
                                    datetime.date.today())
    except KeyError:
        return failed(screen, f"Nessun progetto attivo «{[a for a in args if a != '--tutti'][0]}»: gli identificativi sono in `{app.cmd('progetti')} --json`", {})
    if screen.data(st):
        return 0
    screen.section(st["progetto"])
    for key, title in (("per_stato", "Per stato"), ("per_persona", "Per persona"), ("in_ritardo", "In ritardo"),
                       ("prossime_scadenze", "Scadenze nei prossimi 14 giorni")):
        screen.out("")
        screen.out("  " + screen.bold(title))
        cols = ["id", "titolo", "persona", "scadenza", "fatto"] if key in ("in_ritardo", "prossime_scadenze") else None
        screen.table(st[key], cols, {"in_ritardo": "in ritardo"})
    screen.info(screen.dim(app.snapshot_note(when)))
    return 0


# ── settings: everything a person may get wrong at setup, changeable from the tool ──
def edit_vpn(screen, current):
    """{} = no VPN; otherwise the three command lines (status optional). ValueError without up and down."""
    if screen.confirm("Per arrivare a Redmine serve una VPN?", "No", "Sì"):
        return {}
    now = (current or {})
    lines = {k: screen.ask(f"Comando che {what} la VPN:", " ".join(shlex.quote(w) for w in now.get(k) or []))
             for k, what in (("up", "accende"), ("down", "spegne"), ("status", "dice se è accesa (esce con 0 se sì)"))}
    if not lines["up"] or not lines["down"]:
        raise ValueError("servono almeno i comandi per accenderla e spegnerla")
    return {k: shlex.split(v) for k, v in lines.items() if v}


def show_vpn(v):
    if v is None:
        return "— (non ancora detto)"
    return f"sì: {' '.join(v['up'])}" if v.get("up") else "non serve"


def vpn_problem(v):
    """The programs named by the VPN commands must exist (checked without running them)."""
    for k in ("up", "down", "status"):
        if (v or {}).get(k) and not (shutil.which(v[k][0]) or os.path.isfile(v[k][0])):
            return f"«{v[k][0]}» non trovato (comando che {'accende' if k == 'up' else 'spegne' if k == 'down' else 'controlla'} la VPN)"
    return None


def show_states(states):
    return "; ".join(f"{k}={', '.join([v] if isinstance(v, str) else v)}" for k, v in (states or {}).items()) or "—"


def parse_states(text):
    """«in corso=In Progress; risolte=Resolved, Closed» → {"in corso": ["In Progress"], "risolte": [...]}."""
    out = {}
    for part in filter(None, (p.strip() for p in text.split(";"))):
        label, eq, names = part.partition("=")
        if not eq or not label.strip():
            raise ValueError("scrivi etichetta=Stato Redmine, separate da ; (es. in corso=In Progress; risolte=Resolved)")
        out[label.strip()] = [n.strip() for n in names.split(",") if n.strip()]
    return out


def states_problem(states):
    try:
        redmine.by_state([], states)
    except ValueError as e:
        return str(e)
    return None


SETTINGS = [
    Setting("url", "Indirizzo di Redmine", check=lambda v: v.startswith("https://") or "deve iniziare con https://",
            parse=lambda t: t.rstrip("/")),
    Setting("user", "Utente Redmine", note="la chiave API è legata all'utente"),
    Setting("ruolo", "Ruolo", kind="choice", choices=[("io", "le mie task"), ("pm", "PM: seguo i progetti")],
            default="io", note="PM: progetti e stato scaricano tutto"),
    Setting("progetti", "Progetti da scaricare", kind="list", note="identificativi separati da virgola; - = tutti"),
    Setting("copia_locale", "Copia locale dei dati", kind="yesno", default=False,
            note="sì: i comandi rispondono subito"),
    Setting("aggiorna_ogni_minuti", "Minuti fra due download", kind="number", default=10,
            note="aggiornamenti più ravvicinati usano la copia"),
    Setting("cartella_download", "Cartella degli allegati", kind="folder",
            default=os.path.join("~", "Downloads", "pm-kit")),
    Setting("vpn", "VPN", show=show_vpn, edit=edit_vpn, check=lambda v: vpn_problem(v) or True),
    Setting("vpn_minuti", "Minuti di VPN aperta nel menu", kind="number", default=5,
            note="chiusa dopo questi minuti fermi"),
    Setting("stati", "Stati negli indicatori", show=show_states, parse=parse_states,
            check=lambda v: states_problem(v) or True, note="etichetta=Stato Redmine; …"),
]


def change_key(screen):
    cfg = config()
    if not cfg:
        return f"prima `{app.cmd('setup')}`"
    credentials.forget(SERVICE, cfg.get("user", "default"))
    ok = secret(SERVICE, cfg.get("user", "default"), screen, ASK_KEY, validate=KEY_FORMAT)
    return "chiave API salvata nel portachiavi" if ok else "chiave API non cambiata"


def start_over(screen):
    """After «Rifai da capo»: the API key goes too, then the setup from the start."""
    credentials.forget(SERVICE, (app.config(config_path()) or {}).get("user", "default"))
    return setup(screen, [])


@app.command("impostazioni", args="[NOME [VALORE]] [--reset]",
             help="vedi e cambia le impostazioni (indirizzo, utente, ruolo, VPN, cartelle…); «-» = predefinito",
             menu="Impostazioni", key="i", json=True, example=["vpn_minuti", "10"])
def impostazioni(screen, args):
    if not screen.json:
        screen.header("impostazioni")
    return edit_settings(screen, config_path(), SETTINGS, args, actions=[("Cambia la chiave API", change_key)],
                         on_reset=start_over)


def steps(screen):
    path = config_path()

    def write_config():
        url = screen.ask("Indirizzo di Redmine (es. https://redmine.example):")
        user = screen.ask("Il tuo utente Redmine:")
        if not url.startswith("https://"):
            return False, "l'indirizzo deve iniziare con https://"
        keep = screen.confirm("Tengo i dati scaricati sul computer? (i comandi poi rispondono subito)",
                              "Sì, tieni una copia locale", "No, solo in memoria: ogni avvio riscarica")
        pm = not screen.confirm("Segui i progetti di altri (sei un PM)?", "No, mi bastano le mie task", "Sì, sono un PM")
        old = app.config(path) or {}  # what was written by hand (vpn, pin…) stays
        write_json(path, {**old, "url": url.rstrip("/"), "user": user or "default", "copia_locale": keep,
                          **({"ruolo": "pm"} if pm else {})})
        return True

    def ask_folder():
        cfg = app.config(path) or {}
        default = download_dir(cfg)
        chosen = os.path.expanduser(screen.ask("Dove salvo gli allegati delle task? (Invio = la proposta)", default))
        os.makedirs(chosen, exist_ok=True)
        write_json(path, {**cfg, "cartella_download": chosen})
        return True, chosen

    def vpn_known():
        cfg = config()
        if not cfg or "vpn" not in cfg:
            return False, "non ancora detto se serve"
        return True, "comandi configurati" if (cfg["vpn"] or {}).get("up") else "non serve"

    def ask_vpn():
        try:
            v = edit_vpn(screen, None)
        except ValueError as e:
            return False, str(e)
        why = vpn_problem(v)
        if why:
            return False, why
        write_json(path, {**(app.config(path) or {}), "vpn": v})
        return True, show_vpn(v)

    def ask_key():
        cfg = config()
        return bool(cfg and secret(SERVICE, cfg.get("user", "default"), screen, ASK_KEY, validate=KEY_FORMAT))

    def reaches():
        cfg = config()
        token = stored_key(cfg)
        if not token:
            return False, "prima la configurazione e la chiave"
        credentials.SECRETS.add(token)  # masked in every output from here on
        try:
            with vpn(cfg, screen):
                me = client(cfg, token).get("/users/current.json")["user"]
            return True, f"sei {me.get('login', '?')}"
        except ERRORS + (KeyError, TypeError) as e:
            return False, why(e)
    out = [Step("configurazione", lambda: config() is not None, apply=write_config,
                fix=f"`{app.cmd('setup')}` chiede indirizzo e utente", plan=f"scrivo {path}"),
           Step("chiave API nel portachiavi", lambda: bool(stored_key(config())), apply=ask_key,
                fix=f"`{app.cmd('setup')}` la chiede una volta", plan="chiedo la chiave e la salvo nel portachiavi"),
           Step("cartella per gli allegati", lambda: bool(config() and config().get("cartella_download")),
                apply=lambda: ask_folder(), plan="chiedo dove salvare gli allegati (proposta: ~/Downloads/pm-kit)",
                fix=f"`{app.cmd('impostazioni')}` → Cartella degli allegati"),
           Step("VPN", vpn_known, apply=ask_vpn, plan=f"chiedo se serve la VPN e la scrivo in {path}",
                fix=f"`{app.cmd('impostazioni')}` → VPN"),
           Step("Redmine risponde", reaches)]
    cfg = config()
    if cfg and "stati" in cfg:
        def states_ok():
            try:
                redmine.by_state([], cfg["stati"])
                return True, " · ".join(cfg["stati"])
            except ValueError as e:
                return False, str(e)
        out.append(Step("mappa degli stati", states_ok, fix=f"`{app.cmd('impostazioni')}` → Stati negli indicatori"))
    if cfg and cfg.get("pin_sha256"):
        out.append(pin_step(client(cfg, None)))

    def copy():
        if not cfg or not cfg.get("copia_locale"):
            return True, "solo in memoria (copia locale disattivata)"
        infos = [i for i in (app.snapshot_info(n) for n in COPIES) if i]
        if not infos:
            return True, "attiva, ancora vuota"
        return True, " · ".join(f"{path}, {size // 1024 + 1} KB, presa il {taken}" for path, size, taken in infos)
    out.append(Step("copia locale", copy))
    return out


@app.command("copia", args="si | no | cancella", help="copia locale dei dati: attiva, disattiva o cancella",
             menu=None, example=["cancella"])
def copia(screen, args):
    cfg = config()
    if not cfg or not args or args[0] not in ("si", "sì", "no", "cancella"):
        screen.todo(f"Uso: {app.cmd('copia')} si | no | cancella (prima `{app.cmd('setup')}`)")
        return 2
    if args[0] == "cancella":
        infos = [i for i in (app.snapshot_info(n) for n in COPIES) if i]
        if screen.dry:
            screen.info("farei: cancello " + ", ".join(i[0] for i in infos) if infos else "farei: niente, non c'è una copia locale")
            return 0
        gone = [n for n in COPIES if app.forget_snapshot(n)]
        screen.info("copia locale cancellata" if gone else "non c'era una copia locale")
        return 0
    keep = args[0] != "no"
    if screen.dry:
        screen.info(f"farei: copia_locale = {keep} in {config_path()}")
        return 0
    write_json(config_path(), {**cfg, "copia_locale": keep})
    screen.info("copia locale attiva" if keep else f"copia locale disattivata: `{app.cmd('copia')} cancella` toglie quella vecchia")
    return 0


RELEASE = "https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pm-kit.pyz"


def running_pyz():
    """The .pyz this code runs from (`python3 pm-kit.pyz`), or None when it runs from a clone."""
    archive = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return archive if os.path.isfile(archive) and zipfile.is_zipfile(archive) else None


def installed_pyz():
    return os.path.join(install.home_of(app.name), "pm-kit.pyz")


@app.command("installa", help="il comando pm-kit in ~/.local/bin, dal file pm-kit.pyz che stai lanciando", menu=None)
def installa(screen, args):
    pyz = running_pyz()
    if not pyz:
        screen.todo("Si installa dal file: scarica pm-kit.pyz dalla release, poi `python3 pm-kit.pyz installa`")
        return 1
    if screen.dry:
        screen.info(f"farei: copio {pyz} in {installed_pyz()} e scrivo il comando {app.name} in {install.BIN}")
        return 0
    command = install_launcher(app.name, pyz)
    screen.done(f"installato: {command} (apri un terminale nuovo se `{app.name}` non si trova)")
    return 0


@app.command("nuova-versione", help="scarica l'ultima versione di pm-kit, solo se il suo sha256 corrisponde",
             menu=None)
def nuova_versione(screen, args):
    dest = installed_pyz()
    if not os.path.exists(dest):
        screen.todo(f"pm-kit non è installato in {dest}: prima `python3 pm-kit.pyz installa`")
        return 1
    if screen.dry:
        screen.info(f"farei: scarico pm-kit.pyz dall'ultima release, controllo il suo sha256 e sostituisco {dest}")
        return 0
    with screen.wait("scarico l'ultima versione"):
        ok, why = self_update(RELEASE, dest, RELEASE + ".sha256")
    if not ok:
        screen.todo(f"non aggiornato ({why}): riprova più tardi o scarica a mano dalla release")
        return 1
    screen.done("già l'ultima versione" if why == "up to date" else "aggiornato: vale dal prossimo avvio")
    return 0


@app.command("setup", help="configurazione e chiave API, una volta (si può rilanciare)", menu="Prepara pm-kit", short="Prepara", key="s")
def setup(screen, args):
    screen.header("preparazione")
    return 0 if run_steps(screen, steps(screen)) else 1


@app.command("doctor", help="controlla configurazione, chiave e collegamento", menu="Controlla che sia tutto a posto", short="Controlla",
             effects=False, key="c")
def doctor(screen, args):
    screen.header("controlli")
    return 0 if run_steps(screen, steps(screen), check_only=True) else 1


def main():
    cfg = config()
    if cfg and isinstance(cfg.get("vpn_minuti"), (int, float)):
        app.session_idle_minutes = cfg["vpn_minuti"]
    app.run()


if __name__ == "__main__":
    main()
