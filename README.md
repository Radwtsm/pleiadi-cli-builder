# pleiadi-cli-builder

Per costruire tool da riga di comando che guidano le persone: setup di un computer nuovo, controlli, flussi
ripetitivi (operativi, PM), senza perdere tempo in installazioni. Solo libreria standard di Python (3.8+), Mac,
Linux e Windows: sul computer serve solo Python.

Cosa c'è:

| Pezzo | Modulo | Cosa fa |
|---|---|---|
| `App` | `app.py` | nome, colore, comandi con `@app.command`; senza argomenti il menu a frecce; `help` generato; stato per computer in `~/.config/<nome>/state.json` |
| `Screen` | `term.py` | schermo intero come Claude Code (riquadro fermo in alto, riga di stato ferma in basso, contenuto che scorre, si ridisegna quando la finestra cambia misura); domande a frecce, testo, sì/no; righe semplici fuori da un terminale vero |
| `screen.wait()` / `progress()` | `term.py` | rotellina, luce che scorre sul testo, barra con percentuale e tempo che manca, ultima riga del programma che lavora |
| `run` / `run_live` | `proc.py` | lancia programmi: catturati, interattivi (lo schermo si sospende) o dal vivo nella riga di stato |
| `Step` / `run_steps` | `steps.py` | passi che si possono rilanciare: ognuno controlla prima e salta il fatto; ✗ con cosa fare e «Riprova adesso»; con `check_only` è un `doctor` |
| `Scene` / `play` | `intro.py` | l'intro animata: volo fra le stelle, costellazione, due forme 3D che ruotano e si trasformano, titolo in pixel |
| `screen.table()` / `--json` | `term.py`, `app.py` | risultati in una tabella che sta nella finestra; con `--json` gli stessi dati su stdout per altri programmi (i messaggi vanno su stderr) |
| `secret` / `forget` | `credentials.py` | token e chiavi nel portachiavi del sistema (Keychain, Credential Manager, secret-tool): chiesti una volta senza mostrarli, mai in un file o in un argomento |
| `secret(..., source=)` | `credentials.py` | un segreto già tenuto da un altro strumento, in sola lettura: `CommandSource([...])` (il programma che lo stampa, es. il CLI di un gestore di password) o `ProtectedFile(path)` (file cifrato per l'utente Windows, DPAPI). Mai chiesto né salvato; stesse garanzie: mai negli argomenti, mascherato |
| `run_live(..., log=)` | `proc.py` | programmi lunghi: tutto l'output nel file di log, indietro solo le righe di errore, l'ultima riga e dov'è il log (meno righe a schermo e nel contesto di Claude) |
| `app.snapshot()` / `--aggiorna` | `app.py` | dati letti una volta (per esempio mentre `temporary()` tiene aperta la VPN), salvati nella cache dell'utente (file leggibile solo da lui) con l'ora; poi si filtrano in locale e si riscaricano solo con `--aggiorna`. È una copia su disco: per dati aziendali vale la policy dell'azienda |
| `impronta HOST[:PORTA]` / `server_certificate()` | `webapi.py` | sha256 e scadenza del certificato di un server, da confrontare con il suo proprietario prima di fissarli in `pin_sha256`/`pin_expires`; non salva niente |
| `temporary` | `access.py` | un accesso riservato (VPN, tunnel, credenziale elevata) aperto solo per l'operazione e chiuso sempre, anche se fallisce; lascia aperto ciò che era già aperto |
| `ReadOnlyClient` | `webapi.py` | client JSON per API web (tracker, CI, wiki) che ha solo GET: non può cambiare niente, qualunque permesso abbia il token. Pagine, nuovi tentativi, token in un'intestazione, CA interna (`ca_file`) o impronta del certificato fissata con scadenza (`pin_sha256` + `pin_expires`), mai la verifica spenta |
| `write_commands` / `PolicyError` | `app.py`, `proc.py` | i programmi che cambiano qualcosa (`App(write_commands=[["git", "push"], ["rm"]])`): `run()` li rifiuta nei comandi di sola lettura e con `--prova`. Un segreto letto con `secret()` non può finire negli argomenti di un programma (si passa con `env=`) ed è mascherato `••••` in ogni output |
| `contract.tests(app)` | `contract.py` | i test che ogni tool riceve gratis: `--prova` in una HOME vuota non scrive niente, non applica passi e non lancia comandi di scrittura; `--json` dà JSON valido (comandi con `json=True`); il codice non carica codice a runtime (`exec`, `eval`, `importlib`, `runpy`): la configurazione si legge solo come JSON con `app.config()` |
| `segreti` / `scan` | `scan.py` | ricerca di segreti nei file in stage con la sola libreria standard: il pre-commit la usa quando gitleaks manca |
| `pin_step(client)` | `webapi.py` | passo del doctor: ✗ 30 giorni prima che scada l'impronta fissata |
| `bundle` / `install_launcher` / `self_update` | `install.py` | un file unico `.pyz` con dentro la libreria, il comando in `~/.local/bin`, l'aggiornamento che sostituisce il file solo se è valido e il suo sha256 corrisponde |

## Provalo su un altro computer (serve solo Python 3.8+)

Un file solo, dalla release su GitHub; prima di aprirlo controlla che l'impronta sia quella pubblicata accanto.

Mac o Linux, nel Terminale:

```bash
curl -fLO https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pleiadi-cli-builder.pyz
```

```bash
curl -fsL https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pleiadi-cli-builder.pyz.sha256 | shasum -a 256 -c
```

```bash
python3 pleiadi-cli-builder.pyz
```

Windows, in PowerShell:

```powershell
$u = "https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pleiadi-cli-builder.pyz"
Invoke-WebRequest $u -OutFile pleiadi-cli-builder.pyz
(Get-FileHash pleiadi-cli-builder.pyz -Algorithm SHA256).Hash.ToLower() -eq (Invoke-WebRequest "$u.sha256").Content.Split(" ")[0]
py pleiadi-cli-builder.pyz
```

L'ultima riga prima di `py` deve dire `True`. Senza argomenti si apre il menu; `demo`, `intro`, `new` per provare.

## Prova (da questa cartella)

```bash
python3 -m pleiadi_cli_builder demo
```

```bash
python3 -m pleiadi_cli_builder intro "MIO TOOL" --resta
```

## Un tool nuovo

```bash
python3 -m pleiadi_cli_builder new deploy-kit
```

Crea `deploy-kit/deploy_kit/__main__.py` con `setup` (prepara tutto, si rilancia) e `doctor` (solo controlli),
`tests/test_contract.py` (i test di contratto) e `.githooks/pre-commit` (test + ricerca di segreti).
Mentre lo sviluppi: `PYTHONPATH=<questa cartella> python3 -m deploy_kit`. Per distribuirlo:

```bash
python3 -m pleiadi_cli_builder bundle deploy-kit deploy_kit.__main__:main dist/deploy-kit.pyz
```

`dist/deploy-kit.pyz` gira con `python3 deploy-kit.pyz`; accanto c'è `deploy-kit.pyz.sha256` da pubblicare
insieme: `self_update(url, dest, url + ".sha256")` aggiorna solo se l'impronta corrisponde (obbligatoria: il tuo
codice che si aggiorna da solo è codice di terzi per chi lo riceve).

```python
import shutil

from pleiadi_cli_builder import App, Step, run_steps

app = App("deploy-kit", title="Deploy kit", accent="#4a6cf7", lang="it")

@app.command("doctor", help="solo i controlli", menu="Controlla che sia tutto a posto")
def doctor(screen, args):
    screen.header("controlli")
    return 0 if run_steps(screen, [Step("git", lambda: shutil.which("git") is not None,
                                        fix="Installa git: https://git-scm.com")], check_only=True) else 1

app.run()
```

Un comando che legge da un tracker, per esempio, mette insieme i pezzi così:

```python
from pleiadi_cli_builder import App, ReadOnlyClient, secret, temporary, run

app = App("team-kit", title="Team kit")

@app.command("aperte", help="le task aperte di un progetto", args="PROGETTO", effects=False)
def aperte(screen, args):
    token = secret("team-kit.tracker", "io", screen, "Chiave API del tracker:")
    vpn = lambda *a: run("vpn-cli", *a)[0] == 0  # il comando della tua VPN
    with temporary(lambda: vpn("up"), lambda: vpn("down"), is_open=lambda: vpn("status"), screen=screen, label="VPN"):
        api = ReadOnlyClient("https://tracker.example", token=token, header="X-Api-Key", scheme="")
        rows = [{"id": t["id"], "titolo": t["subject"], "stato": t["status"]["name"]}
                for t in api.pages("/issues.json", {"project_id": args[0], "status_id": "open"}, items="issues")]
    screen.table(rows)
```

`team-kit aperte web` mostra la tabella, `team-kit aperte web --json | jq …` passa i dati a un altro programma.

Un esempio completo: [`examples/pm-kit`](examples/pm-kit) — i progetti in lavorazione su Redmine, per i PM.

## Regole del design

- Le funzioni non stampano: restituiscono valori e `Result`; stampa solo lo `Screen`. Così la stessa logica
  si può usare da un'altra interfaccia (una finestra, i test).
- Ogni passo si può rilanciare: prima controlla, poi fa. Un setup interrotto riparte da dove si era fermato.
- Ogni ✗ dice cosa fare, con il nome esatto di pulsanti e menu.
- Fuori da un terminale vero (script, CI, Claude) tutto diventa righe semplici e le domande prendono la scelta
  consigliata; `<NOME>_PLAIN=1` o `NO_COLOR` fanno lo stesso a mano.
- Niente dipendenze: un computer appena acceso deve poter lanciare il tool.
- Ogni comando dichiara se cambia qualcosa. `effects=False` = solo lettura, imposta dal codice: i suoi passi
  possono solo controllare. Chi ha effetti riceve `--prova` (`--dry-run`): `run_steps` dice cosa farebbe (`plan`)
  senza farlo, e nel tuo codice `screen.dry` è vero.
- La configurazione di un progetto resta dato (JSON): la libreria non importa né esegue file forniti da altri.

Non incluso (per ora): un terminale con Claude dentro il tool.

Variabili per l'intro: `PCB_COLORS=256|24` forza i colori, `PCB_PIXEL=2` usa i mezzi blocchi (più leggero).

## Test

```bash
for t in tests/test_*.py examples/*/tests/test_*.py; do python3 "$t" || break; done
```

Pre-commit (test + gitleaks se c'è): `git config core.hooksPath .githooks`.

Licenza MIT.
