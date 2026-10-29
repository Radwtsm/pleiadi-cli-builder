"""pm-kit: i progetti in lavorazione su Redmine, per chi li segue (sola lettura).

Configurazione (dato, JSON): $PM_KIT_CONFIG oppure ~/.config/pm-kit/config.json
    {"url": "https://redmine.example", "user": "nome",                    obbligatori
     "ca_file": "...", oppure "pin_sha256": "...", "pin_expires": "AAAA-MM-GG",   certificato interno
     "vpn": {"up": [...], "down": [...], "status": [...]}}                 la VPN, aperta solo per scaricare
La chiave API sta nel portachiavi del sistema (chiesta una volta), mai nel file."""
import datetime, os, urllib.error

from pleiadi_cli_builder import (App, HTTPError, ReadOnlyClient, Step, credentials, pin_step, run, run_steps, secret,
                                 temporary, write_json)
from pm_kit import redmine

app = App("pm-kit", title="PM kit", accent="#4a6cf7", menu_subtitle="i progetti in lavorazione")
SERVICE = "pm-kit.redmine"
ASK_KEY = "Chiave API di Redmine (in Redmine: Il mio account → Chiave API, a destra):"
ERRORS = (HTTPError, urllib.error.URLError, OSError, RuntimeError)


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


def snapshot(screen):
    """(data, when) from the snapshot — downloaded once with the VPN open only meanwhile, again with --aggiorna —
    or (None, reason)."""
    cfg = config()
    if not cfg:
        return None, f"Prima `pm-kit setup`: manca {config_path()}"
    token = secret(SERVICE, cfg.get("user", "default"), screen, ASK_KEY)
    if not token:
        return None, "Manca la chiave API: `pm-kit setup`"

    def fetch():
        with vpn(cfg, screen), screen.wait("scarico da Redmine"):
            return redmine.fetch_all(client(cfg, token), datetime.date.today())
    try:
        return app.snapshot("redmine", fetch, refresh=screen.refresh)
    except ERRORS as e:
        return None, why(e)


def failed(screen, reason, empty):
    """✗ with the reason; with --json the empty value on stdout, so a pipe still gets valid JSON."""
    screen.out(screen.c(screen.theme.error, "✗") + f" {reason}")
    screen.data(empty)
    return 1


@app.command("progetti", help="tutti i progetti attivi, i più a rischio prima", menu="I progetti in lavorazione",
             effects=False, json=True)
def progetti(screen, args):
    data, when = snapshot(screen)
    if data is None:
        return failed(screen, when, [])
    rows = redmine.summarize(data["projects"], data["open"], data["closed"], datetime.date.today())
    screen.table(rows, ["progetto", "aperte", "in_ritardo", "chiuse_7g", "avanzamento", "ultima_attivita"],
                 {"in_ritardo": "in ritardo", "chiuse_7g": "chiuse 7 gg", "ultima_attivita": "ultima attività"})
    screen.info(screen.dim(app.snapshot_note(when)))
    return 0


@app.command("stato", args="PROGETTO", help="un progetto: per stato, per persona, ritardi, scadenze",
             effects=False, json=True, example=["sito"])
def stato(screen, args):
    if not args:
        return failed(screen, "Uso: pm-kit stato PROGETTO (l'identificativo è in `pm-kit progetti --json`)", {})
    data, when = snapshot(screen)
    if data is None:
        return failed(screen, when, {})
    try:
        st = redmine.project_status(args[0], data["projects"], data["open"], datetime.date.today())
    except KeyError:
        return failed(screen, f"Nessun progetto attivo «{args[0]}»: gli identificativi sono in `pm-kit progetti --json`", {})
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


@app.command("mie", help="le task aperte assegnate a te", menu="Le mie task", effects=False, json=True)
def mie(screen, args):
    data, when = snapshot(screen)
    if data is None:
        return failed(screen, when, [])
    screen.table(redmine.my_tasks(data), ["id", "progetto", "titolo", "stato", "scadenza", "fatto"])
    screen.info(screen.dim(app.snapshot_note(when)))
    return 0


def steps(screen):
    path = config_path()

    def write_config():
        url = screen.ask("Indirizzo di Redmine (es. https://redmine.example):")
        user = screen.ask("Il tuo utente Redmine:")
        if not url.startswith("https://"):
            return False, "l'indirizzo deve iniziare con https://"
        write_json(path, {"url": url.rstrip("/"), "user": user or "default"})
        return True

    def ask_key():
        cfg = config()
        return bool(cfg and secret(SERVICE, cfg.get("user", "default"), screen, ASK_KEY))

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
    return out


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
    app.run()


if __name__ == "__main__":
    main()
