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
| `secret(..., validate=)` | `credentials.py` | il valore si controlla **prima** di salvarlo: niente caratteri di controllo (un Ctrl+V preso alla lettera) né spazi, e il formato che il tool dichiara; Invio vuoto = dagli appunti, che poi vengono svuotati |
| `access.session()` | `access.py` | nel menu un accesso (VPN) aperto per un'azione resta aperto per le successive; si chiude all'uscita, anche con Ctrl+C, e dopo `App(session_idle_minutes=5)` minuti fermi; la riga in basso dice «VPN aperta da N min» |
| `ReadOnlyClient(rate=)` | `webapi.py` | al massimo N richieste in una finestra di tempo (60 al minuto di base): oltre aspetta e lo dice; le letture a pagine mostrano «1200/4800» con la barra |
| `app.snapshot(keep=, min_refresh_minutes=, screen=)` | `app.py` | copia locale sì/no (no = solo in memoria, niente su disco), riscaricamenti non più spessi di N minuti, avvisi sul primo download, la stima dall'ultima volta e quanti elementi sono arrivati; `snapshot_info`, `forget_snapshot` |
| `Detail` / `screen.detail()` | `detail.py` | un record nel dettaglio: campi chiave fissi in alto, testo che scorre (frecce, PgSu/PgGiù, Inizio/Fine), `/` cerca e `n` va alla prossima, sezioni che si aprono e chiudono con Spazio, colori con un significato (`alarm`, `warn`, `ok`, `dim`) e la legenda; va a capo sulla finestra. Senza terminale: testo semplice; `--json`: i dati |
| `Detail(..., actions={tasto: (etichetta, fn)})` | `detail.py` | nella vista di dettaglio la sezione su cui agisce Spazio è segnata ▶, Tab/Shift+Tab passano alla successiva/precedente; le azioni a un tasto (es. `d` scarica allegati, `c` copia il numero) sono scritte nella riga in basso |
| `copy_to_clipboard()` / `client.download()` | `credentials.py`, `webapi.py` | copia negli appunti (mai segreti); download di un file solo dallo stesso server del client (la chiave non va mai altrove), scritto prima in `.tmp` |
| `screen.table(..., pick=True)` | `term.py` | nel terminale le righe si scelgono con le frecce e Invio ne apre una (restituisce l'indice) |
| `Board` / `screen.board()` | `board.py` | tabella a gruppi con spunte: le righe subito, le colonne lente (`fill={colonna: fn(riga)}`, es. ultima build, ultimo controllo in VPN) arrivano in background con `…` finché mancano, Spazio spunta una riga o tutto il gruppo, `a` tutte, le azioni a un tasto (`actions={tasto: (etichetta, fn(screen, righe))}`) vanno sulle spuntate (nessuna: quella sotto il cursore) e poi le loro righe si riempiono di nuovo; Invio restituisce le spuntate. Senza terminale: i gruppi come tabelle, celle tutte attese; `--json`: le righe col loro gruppo |
| righe nuove (`Detail(sections=[(titolo, righe, piegata, nuove)])`) | `detail.py` | le prime `nuove` righe di una sezione (`True`: tutte) sono nuove dall'ultima volta: ● nel margine, la sezione non parte piegata, la vista si apre sulla prima; senza ricerca attiva `n`/`N` vanno alla successiva/precedente con «nuove 2/7» nella riga in basso (una ricerca vuota ridà `n` alle nuove); `--json` le elenca in `new` |
| `Setting` / `edit_settings()` | `settings.py` | le impostazioni si vedono e si cambiano dallo strumento, mai a mano nel JSON: una schermata con ogni impostazione e il suo valore (Invio la cambia, con un controllo prima di salvare), azioni in più (es. «Cambia la chiave API»), «Rifai da capo» che toglie solo le impostazioni elencate e rilancia la preparazione; da riga di comando `NOME`, `NOME VALORE` («-» = predefinito), `--reset`, `--json`, `--prova`. Tipi: testo, sì/no, scelta, numero, lista, cartella, comando, oppure `show`/`parse`/`edit` propri; per un'impostazione che vive fuori dal JSON (il PATH, una preferenza di sistema) `read()` legge il valore vero e `apply(valore)` lo applica prima di salvare (se fallisce non salva niente; mai con `--prova`) |
| `App(banner=…, banner_info=fn)` | `app.py`, `term.py` | il riquadro fisso in alto, come Claude Code: un piccolo logo di blocchi a sinistra (`banner`, righe di testo; `None` = quello della libreria, `()` = nessuno) e accanto titolo, sottotitolo e le righe di `banner_info()` (versione, cartella, contesto). Niente logo sotto le 60 colonne o le 20 righe. La riga dove si scrive, i tasti e l'attesa stanno subito sotto il contenuto e scendono solo quando il contenuto riempie la finestra |
| `screen.fresh(briciole, esito)`, `choose(..., start=)` | `term.py` | in un menu o in una schermata a ciclo la domanda dopo sostituisce quella prima: il riquadro resta in alto, sotto le briciole («Impostazioni › Stile») e l'esito dell'ultima azione; `start` rimette il cursore sulla voce da cui si era entrati. Vale a schermo intero, senza terminale non cambia niente. In una finestra bassa la domanda e la riga selezionata restano visibili. `run_steps` resta un registro: i ✓ dei passi sono storia utile |
| azioni di `Detail` e `Board` | `term.py` | un'azione a un tasto può chiedere (`confirm`, `choose`, `ask`) e aspettare (`wait`) anche mentre le celle si riempiono in background: ciò che dice sostituisce la vista finché non finisce, poi la vista torna con l'esito in basso |
| esito di ogni comando (`screen.done()`) | `app.py`, `term.py` | ogni comando chiude con ✓ verde o ✗ rosso e cosa è successo: se il comando non lo dice, lo aggiunge `App` dal codice di uscita; un errore non gestito è una riga ✗ col tipo e il messaggio, mai un traceback (`PCB_DEBUG=1` lo mostra) |
| `phase(screen, nome)` | `steps.py` | una fase di un comando che non usa `Step`: si vede come un passo (⏺), l'output di `run_live` scorre sotto, chiude con ✓ e il tempo o ✗ |
| tempi per fase (`App(timings=True)`) | `app.py`, `term.py` | ogni passo applicato dice quanto ha impiegato; a fine comando una tabella con ogni fase ora, l'ultima volta e la differenza (tempi nello stato) |
| colori per significato (`role_of`, `RULES`, `screen.output()`) | `term.py` | ogni riga dell'output di un programma prende il ruolo del tema della prima regola che la riconosce (errore, avviso, ok); le regole guardano la riga senza i nomi di file, così «errorHandler.cpp» non è un errore; `screen.rules` si sostituisce; i log su file restano senza colori |
| output dal vivo (`run_live(..., show=10)`) | `proc.py`, `term.py` | a schermo intero le ultime righe del programma scorrono sotto il passo, colorate per significato, come in Claude Code; alla fine «… altre N righe sopra» e dov'è il log. Fuori da un terminale niente righe in più |
| tastiera vera (`stdin_tty()`) | `term.py` | su Windows `< NUL` non conta come tastiera (isatty() direbbe sì e getwch() resterebbe appeso): solo una console vera |
| navigazione uguale ovunque | `app.py`, `term.py` | in ogni menu Esc torna indietro (`choose(..., esc=)`), le briciole «Tool › Sezione › Azione» sopra ogni azione e sezione (`app.crumbs`) |
| `screentest` | `screentest.py` | le schermate provate come le vede una persona: il comando gira in un vero terminale (pty) della dimensione scelta, i tasti partono quando compare un testo, la finestra si ridimensiona mentre gira; ogni schermata si rilegge come righe di testo e `problems(expect=[…])` controlla righe giuste, nessuna troppo larga, separatore e riga dei tasti, nessun traceback, i testi che devono restare visibili; `check_sizes()` prova 60×20, 80×24, 120×40 e il ridimensionamento; `report()` le mostra come testo. Mac e Linux |
| scorciatoie (`key=`, `choose(..., keys=)`, `screen.shortcut_line()`) | `app.py`, `term.py` | ogni voce di menu ha una lettera (scelta con `app.command(..., key="m")`, altrimenti la prima libera del testo; `q` esce) che la apre subito; i tasti delle operazioni della schermata (azioni di `Detail` e `Board`) sono «chip» evidenziati (`Theme.shortcut`), prima e diversi dai tasti generici, così si vede che valgono lì |
| `app.include(altra, "task", rename=)` / `app.cmd()` | `app.py` | un'App dentro un'altra come sezione: `tool task mie`, una voce del menu che apre il suo sottomenu, i suoi comandi in help. I messaggi usano `app.cmd("setup")`, così dicono il nome giusto anche dentro il tool ospite |
| `command(..., dry=False)` | `app.py` | per un comando che inoltra a un programma con la sua prova: niente `--prova` qui, il flag passa a quel programma |
| `temporary` | `access.py` | un accesso riservato (VPN, tunnel, credenziale elevata) aperto solo per l'operazione e chiuso sempre, anche se fallisce; lascia aperto ciò che era già aperto |
| `ReadOnlyClient` | `webapi.py` | client JSON per API web (tracker, CI, wiki) che ha solo GET: non può cambiare niente, qualunque permesso abbia il token. Pagine, nuovi tentativi, token in un'intestazione, CA interna (`ca_file`) o impronta del certificato fissata con scadenza (`pin_sha256` + `pin_expires`), mai la verifica spenta |
| `write_commands` / `PolicyError` | `app.py`, `proc.py` | i programmi che cambiano qualcosa (`App(write_commands=[["git", "push"], ["rm"]])`): `run()` li rifiuta nei comandi di sola lettura e con `--prova`. Un segreto letto con `secret()` non può finire negli argomenti di un programma (si passa con `env=`) ed è mascherato `••••` in ogni output |
| `contract.tests(app)` | `contract.py` | i test che ogni tool riceve gratis: `--prova` in una HOME vuota non scrive niente; ogni comando, con i colori e nessuno alla tastiera, non solleva eccezioni né mostra traceback, chiude ogni passo col suo ✓/✗, finisce con un esito colorato e un codice di uscita coerente (0 ⇔ nessun ✗; `ux_problems`, `PCB_COLORS=1`), non applica passi e non lancia comandi di scrittura; `--json` dà JSON valido (comandi con `json=True`); il codice non carica codice a runtime (`exec`, `eval`, `importlib`, `runpy`): la configurazione si legge solo come JSON con `app.config()` |
| voci di menu in un pty (`contract.tests(app, screens=True)`) | `contract.py`, `screentest.py` | ogni voce del menu (anche dentro le sezioni) aperta dal menu in un vero terminale con una HOME vuota (primo avvio fatto) e `--prova`, a 60×20, 80×24, 120×40 e ridimensionata: `problems()` vuoto e «Tool › Voce» sullo schermo; un test per voce, si scrive da sé; le quattro misure girano insieme; su Windows (niente pty) i test si saltano. `run_screen` accetta anche una funzione al posto della riga di comando (gira nel processo figlio) |
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

Variabili per l'intro: `PCB_COLORS=256|24` forza i colori; di base i pixel sono mezzi blocchi (▀▄, in ogni font), `PCB_PIXEL=4` usa i quadranti (più fini, ma servono un font che li abbia e righe senza spazi).

## Test

```bash
for t in tests/test_*.py examples/*/tests/test_*.py; do python3 "$t" || break; done
```

Pre-commit (test + gitleaks se c'è): `git config core.hooksPath .githooks`.

Licenza MIT.
