"""`python3 -m pleiadi_cli_builder`: the builder's own CLI, made with the library itself."""
import os, re, stat, sys

from . import App, Scene, Step, bundle, play, run_steps

app = App("pleiadi-cli-builder", title="Pleiadi CLI builder", accent="#4a6cf7", lang="it",
          menu_subtitle="crea, prova e impacchetta un tool")

TEMPLATE = '''"""{name}: {title}."""
import os, shutil

from pleiadi_cli_builder import App, Scene, Step, play, run, run_steps

app = App("{name}", title="{title}", accent="#4a6cf7", first_run="setup", menu_subtitle="cosa c'è e cosa manca",
          write_commands=[["git", "push"], ["rm"]])  # i programmi che cambiano qualcosa: mai nei comandi di lettura


def steps():
    return [
        Step("git", lambda: shutil.which("git") is not None, fix="Installa git: https://git-scm.com"),
        Step("cartella di lavoro", lambda: os.path.isdir(os.path.expanduser("~/code")),
             apply=lambda: os.makedirs(os.path.expanduser("~/code"), exist_ok=True) or True, plan="creo ~/code"),
    ]


@app.command("setup", help="prepara tutto; si può rilanciare, salta il fatto", menu="Prepara tutto")
def setup(screen, args):
    play(Scene("{title}", "pronto in pochi minuti"), fade=True)
    screen.header("preparazione")
    return 0 if run_steps(screen, steps()) else 1


@app.command("doctor", help="solo i controlli, non cambia niente", menu="Controlla che sia tutto a posto",
             effects=False)
def doctor(screen, args):
    screen.header("controlli")
    return 0 if run_steps(screen, steps(), check_only=True) else 1


def main():
    app.run()


if __name__ == "__main__":
    main()
'''

CONTRACT = '''"""Le regole generali come test: --prova non scrive niente, --json dà JSON, niente codice caricato a runtime."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pleiadi_cli_builder.contract import tests
from {pkg}.__main__ import app

Contract = tests(app)

if __name__ == "__main__":
    unittest.main()
'''

HOOK = '''#!/bin/sh
# prima di ogni commit: i test e nessun segreto (gitleaks se c'è, se no la ricerca della libreria)
set -e
cd "$(git rev-parse --show-toplevel)"
for t in tests/test_*.py; do python3 "$t" >/dev/null 2>&1 || {{ python3 "$t"; exit 1; }}; done
if command -v gitleaks >/dev/null; then gitleaks git --staged --no-banner --redact
else python3 -m pleiadi_cli_builder segreti --staged; fi
'''


@app.command("new", args="NOME [CARTELLA]", help="un tool nuovo pronto da modificare (setup + doctor)",
             menu="Crea un tool nuovo", example=["prova-tool"])
def new(screen, args):
    name = args[0] if args else screen.ask("Nome del comando (minuscole e trattini):", "mio-tool")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", name):
        screen.todo("Nome non valido: minuscole, cifre e trattini, es. deploy-kit")
        return 2
    folder = args[1] if len(args) > 1 else name
    pkg = name.replace("-", "_")
    path = os.path.join(folder, pkg, "__main__.py")
    if os.path.exists(path):
        screen.todo(f"Esiste già: {path}")
        return 1
    if screen.dry:
        screen.info(f"farei: {path} con setup e doctor, tests/test_contract.py, .githooks/pre-commit")
        return 0
    os.makedirs(os.path.dirname(path))
    open(os.path.join(folder, pkg, "__init__.py"), "w").close()
    title = name.replace("-", " ").title()
    files = {path: TEMPLATE.format(name=name, title=title),
             os.path.join(folder, "tests", "test_contract.py"): CONTRACT.format(pkg=pkg),
             os.path.join(folder, ".githooks", "pre-commit"): HOOK.format()}
    for p, text in files.items():
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    hook = os.path.join(folder, ".githooks", "pre-commit")
    os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    screen.section(f"Creato {name}")
    screen.info(f"Prova:      cd {folder} && python3 -m {pkg}")
    screen.info(f"Test:       python3 {folder}/tests/test_contract.py")
    screen.info(f"Pre-commit: git init && git config core.hooksPath .githooks (dentro {folder})")
    screen.info(f"Un file:    python3 -m pleiadi_cli_builder bundle {folder} {pkg}.__main__:main dist/{name}.pyz")
    return 0


@app.command("impronta", args="HOST[:PORTA] …", help="sha256 e scadenza del certificato di un server, da confrontare",
             effects=False, json=True)
def impronta(screen, args):
    from .webapi import server_certificate
    rows = []
    for a in args:
        host, _, port = a.partition(":")
        try:
            sha, expires = server_certificate(host, int(port or 443))
            rows.append({"server": a, "sha256": sha, "scade": expires})
        except (OSError, ValueError) as e:
            screen.out(screen.c(screen.theme.error, screen.theme.no) + f" {a}: {e}")
    if not args:
        screen.todo("Uso: impronta HOST[:PORTA] …")
    if screen.json:  # the data alone on stdout
        screen.table(rows)
    else:
        for r in rows:  # one value per line, whole: it gets copied into the config
            screen.out(f"    {r['server']}\n      sha256       {r['sha256']}\n      pin_expires  {r['scade'] or '?'}")
        if rows:
            screen.todo("Confronta l'impronta con quella che ti dà il proprietario del server (di persona, da un\n"
                        "canale fidato), mai con questa connessione; poi pin_sha256 e pin_expires. Qui non salvo niente.")
    return 0 if rows and len(rows) == len(args) else 1


@app.command("segreti", args="[--staged | FILE…]", help="cerca segreti nei file in stage (o in quelli indicati)",
             effects=False)
def segreti(screen, args):
    from . import scan
    if args and args[0] != "--staged":
        found = []
        for p in args:
            with open(p, encoding="utf-8", errors="replace") as f:
                found += [(p, kind, n) for kind, n in scan.text(f.read())]
    else:
        found = scan.staged()
    for p, kind, n in found:
        screen.out(screen.c(screen.theme.error, screen.theme.no) + f" {p}:{n}  {kind}")
    if found:
        screen.todo("Togli il segreto dal file (leggilo con secret() o da un file fuori dal repo); se è già stato\n"
                    "pubblicato va cambiato, non solo cancellato. Un falso allarme: «scan: ok» in fondo alla riga.")
        return 1
    return 0


@app.command("bundle", args="CARTELLA MODULO:FUNZIONE USCITA.pyz", help="un file unico che gira con solo Python",
             example=["tool", "tool.__main__:main", "dist/tool.pyz"])
def bundle_cmd(screen, args):
    if len(args) != 3:
        screen.todo("Uso: bundle CARTELLA MODULO:FUNZIONE USCITA.pyz")
        return 2
    if screen.dry:
        screen.info(f"farei: {args[2]} e {args[2]}.sha256 da {args[0]} ({args[1]})")
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(args[2])), exist_ok=True)
    digest = bundle(args[0], args[1], args[2])
    screen.section(f"{args[2]} pronto")
    screen.info(f"sha256 {digest} (anche in {args[2]}.sha256, da pubblicare accanto per self_update)")
    return 0


@app.command("demo", help="tutti i pezzi in un giro: passi, attesa, scelte", menu="Guarda la demo")
def demo(screen, args):
    import time

    def slow():
        from . import progress
        for i in range(20):
            progress(i / 20, f"{i}/20 file")
            time.sleep(0.08)
        return True, "20 file"
    screen.header("demo")
    ok = run_steps(screen, [Step("già fatto", lambda: True),
                            Step("scarica i file", lambda: False, apply=slow, wait="scarico"),
                            Step("una cosa da fare a mano", lambda: False, fix="Apri Impostazioni → Rete e premi «Collega»")])
    return 0 if ok else 1  # the exit code says what the summary says


@app.command("intro", args="[TITOLO] [--resta]", help="l'animazione d'apertura (un tasto la salta)",
             menu="Guarda l'intro", effects=False)
def intro(screen, args):
    hold = "--resta" in args
    words = [a for a in args if not a.startswith("--")]
    return play(Scene(" ".join(words) or "PLEIADI", "costruisci il tuo tool", ["un tasto per uscire"] if hold else []),
                hold=hold)


def main():
    app.run()


if __name__ == "__main__":
    main()
