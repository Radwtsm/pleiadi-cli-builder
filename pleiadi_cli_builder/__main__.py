"""`python3 -m pleiadi_cli_builder`: the builder's own CLI, made with the library itself."""
import os, re

from . import App, Scene, Step, bundle, play, run_steps

app = App("pleiadi-cli-builder", title="Pleiadi CLI builder", accent="#4a6cf7", lang="it",
          menu_subtitle="crea, prova e impacchetta un tool")

TEMPLATE = '''"""{name}: {title}."""
import os, shutil

from pleiadi_cli_builder import App, Scene, Step, play, run, run_steps

app = App("{name}", title="{title}", accent="#4a6cf7", first_run="setup", menu_subtitle="cosa c'è e cosa manca")


def steps():
    return [
        Step("git", lambda: shutil.which("git") is not None, fix="Installa git: https://git-scm.com"),
        Step("cartella di lavoro", lambda: os.path.isdir(os.path.expanduser("~/code")),
             apply=lambda: os.makedirs(os.path.expanduser("~/code"), exist_ok=True) or True),
    ]


@app.command("setup", help="prepara tutto; si può rilanciare, salta il fatto", menu="Prepara tutto")
def setup(screen, args):
    play(Scene("{title}", "pronto in pochi minuti"), fade=True)
    screen.header("preparazione")
    return 0 if run_steps(screen, steps()) else 1


@app.command("doctor", help="solo i controlli, non cambia niente", menu="Controlla che sia tutto a posto")
def doctor(screen, args):
    screen.header("controlli")
    return 0 if run_steps(screen, steps(), check_only=True) else 1


def main():
    app.run()


if __name__ == "__main__":
    main()
'''


@app.command("new", args="NOME [CARTELLA]", help="un tool nuovo pronto da modificare (setup + doctor)",
             menu="Crea un tool nuovo")
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
    os.makedirs(os.path.dirname(path))
    open(os.path.join(folder, pkg, "__init__.py"), "w").close()
    title = name.replace("-", " ").title()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(TEMPLATE.format(name=name, title=title))
    screen.section(f"Creato {name}")
    screen.info(f"Prova:      cd {folder} && python3 -m {pkg}")
    screen.info(f"Un file:    python3 -m pleiadi_cli_builder bundle {folder} {pkg}.__main__:main dist/{name}.pyz")
    return 0


@app.command("bundle", args="CARTELLA MODULO:FUNZIONE USCITA.pyz", help="un file unico che gira con solo Python")
def bundle_cmd(screen, args):
    if len(args) != 3:
        screen.todo("Uso: bundle CARTELLA MODULO:FUNZIONE USCITA.pyz")
        return 2
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
    run_steps(screen, [Step("già fatto", lambda: True),
                       Step("scarica i file", lambda: False, apply=slow, wait="scarico"),
                       Step("una cosa da fare a mano", lambda: False, fix="Apri Impostazioni → Rete e premi «Collega»")])
    return 0


@app.command("intro", args="[TITOLO] [--resta]", help="l'animazione d'apertura (un tasto la salta)",
             menu="Guarda l'intro")
def intro(screen, args):
    hold = "--resta" in args
    words = [a for a in args if not a.startswith("--")]
    return play(Scene(" ".join(words) or "PLEIADI", "costruisci il tuo tool", ["un tasto per uscire"] if hold else []),
                hold=hold)


if __name__ == "__main__":
    app.run()
