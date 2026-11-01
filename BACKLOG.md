# Backlog

Dalla meno alla più impegnativa. Ogni voce arriva con il suo test automatico (colonna «Prova»). Le idee nuove
vanno qui, non nel codice subito. Solo cose generiche: le funzioni di uno strumento aziendale stanno nel suo repo.

| # | Cosa | Impegno | Prova |
|---|---|---|---|
| 4 | **Modalità compatta** sotto 70 colonne o 22 righe, anche ridimensionando dal vivo: titolo su una riga, nel menu principale le notifiche in cima e i pulsanti base con la lettera (`[m] Mie`, `[…] Altro`), etichette brevi (`short=` su `app.command`), riga dei tasti corta; tornando grande, la vista normale | medio, ~150 | `screentest`: grande → 60×20 → 40×15 → grande, la domanda e i pulsanti sempre visibili |
| 5 | **`run_live(..., on_line=)`** e **Ctrl+C pulito su Windows**: una callback per ogni riga; l'interruzione ferma tutto l'albero del processo (gruppo di processi / `CTRL_BREAK`) e dice cosa è rimasto a metà (da skf-cli) | medio, ~80 | programma finto che stampa e resta appeso, su Windows e Mac |
| 6 | **`screen.highlight(testo, regole)` e `run_live(..., rules=)`**: lista di (regex, ruolo), vince la prima; colora solo ciò che la regex prende; i nomi di file si riconoscono prima delle parole (`errorHandler.cpp` non è rosso); a schermo con i colori, nel log senza; regole pronte per svn, git, MSBuild (da skf-cli) | medio, ~120 | tabella di righe vere → colori attesi |
| 7 | **Output scorrevole come in Claude Code**: PgSu/PgGiù, frecce e rotella anche mentre il comando gira (tasti letti durante l'attesa); in fondo segue, risalendo si ferma con «↓ 120 righe nuove», Fine torna giù; limite di 500 righe configurabile; tasti scritti a schermo, Ctrl+C sempre attivo. Provare in VS Code e Windows Terminal: se la rotella su Windows non si può avere, dirlo (da skf-cli) | alto, ~250 | logica senza terminale + pty |
| 8 | **Regole di contratto per comandi espliciti** (da confermare con l'owner, arrivate via skf-cli): mai schermo muto, ogni passo dice cosa fa e com'è andato; l'output si vede sempre dal vivo e mai meno del comando lanciato da solo, niente formati macchina nascosti | medio, ~60 | `contract.tests` |
| 9 | **Istruzioni di setup con ogni strumento** (da confermare con l'owner, arrivate via skf-cli): un task che aggiunge tool, dipendenza o passo manuale aggiorna il setup nello stesso task; provato su una macchina pulita quando si può | poco, ~30 | controllo che il README abbia la sezione setup |
| 10 | **pm-kit installabile**: `.pyz` con launcher come il builder; oggi parte solo da un clone con `PYTHONPATH` | poco, ~40 | installazione in una cartella vuota |
