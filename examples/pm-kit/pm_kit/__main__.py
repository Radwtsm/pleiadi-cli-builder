"""pm-kit: i progetti in lavorazione su Redmine, per chi li segue (sola lettura).

Configurazione (dato, JSON): $PM_KIT_CONFIG oppure ~/.config/pm-kit/config.json
    {"url": "https://redmine.example", "user": "nome",                    obbligatori
     "copia_locale": true,                  dati tenuti sul computer tra un avvio e l'altro (false: solo in memoria)
     "progetti": ["sito", "app"],           scarica solo questi (identificativi); assente = tutti
     "vpn_minuti": 5,                       nel menu la VPN resta aperta fra le azioni, chiusa dopo questi minuti fermi
     "ruolo": "pm",                         segue i progetti: `progetti` e `stato` scaricano tutto senza --tutti
     "aggiorna_ogni_minuti": 10,            --aggiorna più ravvicinati usano la copia (meno carico su Redmine)
     "ca_file": "...", oppure "pin_sha256": "...", "pin_expires": "AAAA-MM-GG",   certificato interno
     "vpn": {"up": [...], "down": [...], "status": [...]}}                 la VPN, aperta solo per scaricare
La chiave API sta nel portachiavi del sistema (chiesta una volta), mai nel file."""
import datetime, os, urllib.error

from pleiadi_cli_builder import (App, HTTPError, ReadOnlyClient, Step, credentials, pin_step, run, run_steps, secret,
                                 temporary, write_json)
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
        return {401: "HTTP 401: chiave API sbagliata o scaduta (rifai `pm-kit setup`)",
                403: "HTTP 403: la tua utenza non vede questi dati"}.get(e.status, str(e))
    return f"Redmine non risponde ({getattr(e, 'reason', e)}): VPN accesa? indirizzo giusto?"


def stored_key(cfg):
    return cfg and credentials.keychain().get(SERVICE, cfg.get("user", "default"))


def connect(screen):
    """(cfg, token) or (None, reason)."""
    cfg = config()
    if not cfg:
        return None, f"Prima `pm-kit setup`: manca {config_path()}"
    token = secret(SERVICE, cfg.get("user", "default"), screen, ASK_KEY, validate=KEY_FORMAT)
    return (cfg, token) if token else (None, "Manca la chiave API: `pm-kit setup`")


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
                                    "segue i progetti. Cosa faccio?", "Niente: mi bastano le mie task (pm-kit mie)",
                                    "Scarica tutto")
    if not wanted:
        return None, ("Scaricare tutto Redmine serve a chi segue i progetti: aggiungi --tutti (o \"ruolo\": \"pm\" nella "
                      "configurazione). Per le tue task: pm-kit mie; per cercarne altre: pm-kit task --progetto …")

    def fetch():
        with vpn(cfg, screen), screen.wait("scarico tutto da Redmine"):
            return redmine.fetch_all(client(cfg, token), datetime.date.today(), only=cfg.get("progetti"))
    return download(screen, "redmine", cfg, fetch, 10)


def mine(screen):
    cfg, token = connect(screen)
    if not cfg:
        return None, token

    def fetch():
        with vpn(cfg, screen), screen.wait("scarico le mie task"):
            return redmine.fetch_mine(client(cfg, token))
    return download(screen, "mie", cfg, fetch, 2)


def failed(screen, reason, empty):
    """✗ with the reason; with --json the empty value on stdout, so a pipe still gets valid JSON."""
    screen.out(screen.c(screen.theme.error, "✗") + f" {reason}")
    screen.data(empty)
    return 1


@app.command("mie", help="le task aperte assegnate a te (scarica solo quelle)", menu="Le mie task", effects=False,
             json=True)
def mie(screen, args):
    data, when = mine(screen)
    if data is None:
        return failed(screen, when, [])
    screen.table(redmine.my_tasks(data), ["id", "progetto", "titolo", "stato", "scadenza", "fatto"])
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
            found, cut = redmine.search(client(cfg, token), query)
    except ERRORS as e:
        return failed(screen, why(e), [])
    screen.table(found, ["id", "progetto", "titolo", "stato", "persona", "scadenza", "fatto"])
    if cut:
        screen.todo("Mostro le prime 200: restringi con --progetto, --stato o --testo.")
    return 0


@app.command("progetti", args="[--tutti]", help="tutti i progetti attivi, i più a rischio prima (per chi li segue: "
             "scarica tutto)", menu="Tutti i progetti (per chi li segue)", effects=False, json=True)
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
        return failed(screen, "Uso: pm-kit stato PROGETTO (l'identificativo è in `pm-kit progetti --json`)", {})
    data, when = everything(screen, args)
    if data is None:
        return failed(screen, when, {})
    try:
        st = redmine.project_status([a for a in args if a != "--tutti"][0], data["projects"], data["open"],
                                    datetime.date.today())
    except KeyError:
        return failed(screen, f"Nessun progetto attivo «{[a for a in args if a != '--tutti'][0]}»: gli identificativi sono in `pm-kit progetti --json`", {})
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
        write_json(path, {"url": url.rstrip("/"), "user": user or "default", "copia_locale": keep,
                          **({"ruolo": "pm"} if pm else {})})
        return True

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
                fix=f"Scrivi {path} con url e user (vedi `pm-kit help`)", plan=f"scrivo {path}"),
           Step("chiave API nel portachiavi", lambda: bool(stored_key(config())), apply=ask_key,
                fix="`pm-kit setup` la chiede una volta", plan="chiedo la chiave e la salvo nel portachiavi"),
           Step("Redmine risponde", reaches)]
    cfg = config()
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
        screen.todo("Uso: pm-kit copia si | no | cancella (prima `pm-kit setup`)")
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
    screen.info("copia locale attiva" if keep else "copia locale disattivata: `pm-kit copia cancella` toglie quella vecchia")
    return 0


@app.command("setup", help="configurazione e chiave API, una volta (si può rilanciare)", menu="Prepara pm-kit")
def setup(screen, args):
    screen.header("preparazione")
    return 0 if run_steps(screen, steps(screen)) else 1


@app.command("doctor", help="controlla configurazione, chiave e collegamento", menu="Controlla che sia tutto a posto",
             effects=False)
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
