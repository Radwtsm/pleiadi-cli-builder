# CLAUDE.md — pleiadi-cli-builder

Libreria pubblica (MIT) per costruire CLI guidate. Repo pubblico: mai nomi di persone, aziende, account, host o
percorsi privati, mai codice o dati di chi la usa (un tool aziendale vive nel repo dell'azienda e importa questa).

- Solo libreria standard, Python ≥ 3.8 (prova anche con `/usr/bin/python3` del Mac, 3.9). Niente dipendenze.
- Le funzioni non stampano; stampa solo `Screen`. Ogni ramo a schermo intero ha il suo ramo a righe semplici.
- API e codice in inglese; testi per le persone in `TEXTS` di `term.py` (it/en), mai sparsi nel codice.
- Mai cambiare in modo incompatibile un nome pubblico di `__init__.py`: aggiungi, poi deprecazione.
- Prima del commit: `python3 tests/test_all.py` verde (include una prova vera a schermo intero in un pty).
