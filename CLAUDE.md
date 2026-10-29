# CLAUDE.md — pleiadi-cli-builder

Libreria pubblica (MIT) per costruire CLI guidate. Repo pubblico: mai nomi di persone, aziende, account, host o
percorsi privati, mai codice o dati di chi la usa (un tool aziendale vive nel repo dell'azienda e importa questa).

- Solo libreria standard, Python ≥ 3.8 (prova anche con `/usr/bin/python3` del Mac, 3.9). Niente dipendenze.
- Le funzioni non stampano; stampa solo `Screen`. Ogni ramo a schermo intero ha il suo ramo a righe semplici.
- API e codice in inglese; testi per le persone in `TEXTS` di `term.py` (it/en), mai sparsi nel codice.
- Mai cambiare in modo incompatibile un nome pubblico di `__init__.py`: aggiungi, poi deprecazione.
- Prima del commit: tutti i `tests/test_*.py` verdi (include una prova vera a schermo intero in un pty); lo fa il
  pre-commit (`git config core.hooksPath .githooks`, con gitleaks).
- Release: `python3 tools/release.py` → `dist/pleiadi-cli-builder.pyz` + `.sha256`, poi tag `vX.Y.Z` e
  `gh release create` con i due file (il README rimanda a `releases/latest`).
- Output pensato anche per Claude (che legge ogni riga a token): righe brevi, ✓/✗ con cosa fare, un riepilogo;
  i dati con `--json`. Mai log interi a schermo: l'ultima riga utile, il resto in un file.
- Colori per ruolo, come Claude Code (`Theme`, mai codici scritti a mano fuori da lì): un solo accento per ciò che è
  interattivo o selezionato; `dim` per il secondario (bordi, note, descrizioni dei tasti); `ok`/`warn`/`error`
  solo per un significato. Riga selezionata = barra su tutta la larghezza (`select`); nei suggerimenti il tasto in
  accento e grassetto, cosa fa attenuato (`screen.keys`); tabelle con titoli in grassetto e una riga sotto.
