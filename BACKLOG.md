# Backlog

Dalla meno alla più impegnativa. Ogni voce arriva con il suo test automatico (colonna «Prova»). Le idee nuove
vanno qui, non nel codice subito. Solo cose generiche: le funzioni di uno strumento aziendale stanno nel suo repo.

| # | Cosa | Impegno | Prova |
|---|---|---|---|
| 1 | **Ogni voce di menu provata da sola**: `contract.tests(app)` apre ogni comando del menu in un pty (`screentest.check_sizes`, config finta) a 60×20, 80×24, 120×40 e ridimensionato; nessun problema di `problems()` | poco, ~60 righe | si scrive da sé: ogni comando nuovo è coperto |
| 2 | **Programmi finti per i test**: un helper che mette in testa al PATH script che rispondono sempre uguale (es. un controllo versione, una build, un client SQL), con uscita 0 o errore a scelta; così i flussi pensati per Windows si provano anche su Mac/Linux | poco, ~40 | test dell'helper stesso |
| 3 | **Tempo di ogni comando** in un file locale (comando, durata, esito; niente argomenti né dati): base per misurare prima/dopo, `App.timings()` per leggerlo | poco, ~30 | orologio finto |
| 4 | **Modalità compatta** sotto 70 colonne o 22 righe, anche ridimensionando dal vivo: titolo su una riga, solo la domanda corrente, nel menu principale le notifiche in cima e i pulsanti base con la lettera (`[m] Mie`, `[…] Altro`), etichette brevi (`short=` su `app.command`), riga dei tasti corta; tornando grande, la vista normale | medio, ~150 | `screentest`: grande → 60×20 → 40×15 → grande, la domanda e i pulsanti sempre visibili |
