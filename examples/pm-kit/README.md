# pm-kit (esempio)

Un tool completo fatto con pleiadi-cli-builder: i progetti in lavorazione su **qualunque Redmine**, per chi li
segue. Solo lettura (`ReadOnlyClient` ha solo GET), chiave API nel portachiavi, VPN aperta solo per scaricare,
un'istantanea dei dati (`--aggiorna` per riscaricarla), tabella o `--json`.

| Comando | Cosa mostra |
|---|---|
| `pm-kit setup` | chiede indirizzo e utente (file JSON) e la chiave API (portachiavi); si può rilanciare |
| `pm-kit impostazioni` | (menu: Impostazioni, tasto `i`) ogni impostazione con il suo valore, Invio la cambia: indirizzo, utente, ruolo, progetti, copia locale, minuti fra i download, cartella degli allegati, VPN (controlla che i programmi esistano), minuti di VPN aperta, stati negli indicatori; «Cambia la chiave API»; «Rifai da capo» (toglie impostazioni e chiave, rilancia la preparazione). Da riga di comando: `impostazioni NOME VALORE` («-» = predefinito), `--json` |
| `pm-kit doctor` | configurazione, chiave, Redmine che risponde, impronta del certificato che scade |
| `pm-kit mie` | le task aperte assegnate a me: il download leggero, per tutti; ● sulle task cambiate (o nuove per me) da quando le ho viste |
| `pm-kit novita [--visto]` | cosa è cambiato sulle mie task dall'ultima volta (stato, scadenza, fatto, priorità, assegnatario, o solo note); Invio apre la task, che da lì conta come vista; `--visto` le segna tutte. La prima volta fissa il punto di partenza. Cosa ho visto sta in `viste.json` accanto alle copie (niente titoli né testi) |
| `pm-kit task --progetto ID --stato aperte\|chiuse\|tutte --persona me\|ID --scadenza GIORNI --testo PAROLA` | una ricerca filtrata sul server (al massimo 200 risultati) |
| `pm-kit progetti --tutti` | per chi segue i progetti: ogni progetto attivo con aperte, in ritardo, chiuse in 7 giorni, avanzamento, ultima attività; scarica tutto, quindi vuole `--tutti`, `"ruolo": "pm"` o una conferma nel menu |
| `pm-kit stato PROGETTO --tutti` | per stato, per persona, in ritardo, scadenze dei prossimi 14 giorni |
| `pm-kit issue N` | una task nel dettaglio: stato, priorità, assegnatario, scadenza, avanzamento, versione, autore, date (in rosso ritardo e urgenza, in giallo scadenza vicina, ferma da più di 14 giorni o ti cita, in verde se è tua); descrizione leggibile, note e cambi di stato dalle più recenti, relazioni e sotto-task, allegati. Da `mie` e `task` si apre anche con Invio sulla riga; se è cambiata da quando l'ho vista, prima la sezione «Cosa è cambiato» (i campi cambiati) e le note e gli allegati arrivati dopo sono segnati ● (gli allegati nuovi in cima, «nuova versione» se un file con lo stesso nome c'era già): `n`/`N` li scorrono uno per uno, «nuove 2/7» in basso |
| `pm-kit allegati N` | tutti gli allegati della task in `<cartella_download>/<N>/` (la cartella la chiede `setup`); nella vista della task: `d` li scarica, `c` copia il numero |
| `pm-kit copia si\|no\|cancella` | la copia locale dei dati: attiva, disattiva, cancella |
| `pm-kit installa` | dal file `pm-kit.pyz` della release: il comando `pm-kit` in `~/.local/bin` (come installarlo: README della libreria, «pm-kit su un altro computer») |
| `pm-kit nuova-versione` | scarica l'ultimo `pm-kit.pyz` dalla release e sostituisce quello installato solo se il suo sha256 corrisponde |

Configurazione (`~/.config/pm-kit/config.json`, o il percorso in `PM_KIT_CONFIG`): `url` e `user`; se serve
`ca_file` (CA interna) oppure `pin_sha256` + `pin_expires` (vedi `pleiadi-cli-builder impronta HOST`), e `vpn` con
tre righe di comando `up`, `down`, `status` (liste di argomenti). È un dato: niente codice nel file.

Gli indicatori sopra `mie` (e `riepilogo --json`, chiave `per_stato`) contano le task anche per stato. Con `stati`
gli stati di Redmine si raggruppano nelle etichette che servono, in quest'ordine, il resto va in «altro» (maiuscole
indifferenti; `doctor` controlla che sia scritta bene):

    "stati": {"in corso": ["In Progress"], "in attesa": ["Pending", "Feedback"], "risolte": ["Resolved"]}

Senza `stati`: i nomi di Redmine così come sono, i più numerosi prima.

Usa solo i campi standard dell'API REST di Redmine (`/projects.json`, `/issues.json`, `/users/current.json`); per
campi personalizzati o versioni si aggiunge un calcolo in `pm_kit/redmine.py` con il suo test.

Prova, dalla cartella del repo della libreria:

```bash
PYTHONPATH=.:examples/pm-kit python3 -m pm_kit help
```

```bash
python3 examples/pm-kit/tests/test_pm_kit.py
```

I test usano un Redmine finto con dati inventati, più i test di contratto della libreria.
