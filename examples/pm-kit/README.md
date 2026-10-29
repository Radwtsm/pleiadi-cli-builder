# pm-kit (esempio)

Un tool completo fatto con pleiadi-cli-builder: i progetti in lavorazione su **qualunque Redmine**, per chi li
segue. Solo lettura (`ReadOnlyClient` ha solo GET), chiave API nel portachiavi, VPN aperta solo per scaricare,
un'istantanea dei dati (`--aggiorna` per riscaricarla), tabella o `--json`.

| Comando | Cosa mostra |
|---|---|
| `pm-kit setup` | chiede indirizzo e utente (file JSON) e la chiave API (portachiavi); si può rilanciare |
| `pm-kit doctor` | configurazione, chiave, Redmine che risponde, impronta del certificato che scade |
| `pm-kit mie` | le task aperte assegnate a me: il download leggero, per tutti |
| `pm-kit task --progetto ID --stato aperte\|chiuse\|tutte --persona me\|ID --scadenza GIORNI --testo PAROLA` | una ricerca filtrata sul server (al massimo 200 risultati) |
| `pm-kit progetti --tutti` | per chi segue i progetti: ogni progetto attivo con aperte, in ritardo, chiuse in 7 giorni, avanzamento, ultima attività; scarica tutto, quindi vuole `--tutti`, `"ruolo": "pm"` o una conferma nel menu |
| `pm-kit stato PROGETTO --tutti` | per stato, per persona, in ritardo, scadenze dei prossimi 14 giorni |
| `pm-kit issue N` | una task nel dettaglio: stato, priorità, assegnatario, scadenza, avanzamento, versione, autore, date (in rosso ritardo e urgenza, in giallo scadenza vicina, ferma da più di 14 giorni o ti cita, in verde se è tua); descrizione leggibile, note e cambi di stato dalle più recenti, relazioni e sotto-task, allegati. Da `mie` e `task` si apre anche con Invio sulla riga |
| `pm-kit allegati N` | tutti gli allegati della task in `<cartella_download>/<N>/` (la cartella la chiede `setup`); nella vista della task: `d` li scarica, `c` copia il numero |
| `pm-kit copia si\|no\|cancella` | la copia locale dei dati: attiva, disattiva, cancella |

Configurazione (`~/.config/pm-kit/config.json`, o il percorso in `PM_KIT_CONFIG`): `url` e `user`; se serve
`ca_file` (CA interna) oppure `pin_sha256` + `pin_expires` (vedi `pleiadi-cli-builder impronta HOST`), e `vpn` con
tre righe di comando `up`, `down`, `status` (liste di argomenti). È un dato: niente codice nel file.

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
