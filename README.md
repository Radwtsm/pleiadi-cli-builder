# pleiadi-cli-builder

[![tests](https://github.com/Radwtsm/pleiadi-cli-builder/actions/workflows/tests.yml/badge.svg)](https://github.com/Radwtsm/pleiadi-cli-builder/actions/workflows/tests.yml)

A Python library for building **guided command-line tools**: setting up a new computer, health checks, repetitive
team workflows. Standard library only (Python 3.8+), macOS, Linux and Windows: the target machine needs nothing but
Python. The tools it produces are meant to be run by people *and* by AI agents, so every line of output is short,
actionable and machine-readable on request.

Italian reference with every module in detail: [README.it.md](README.it.md). Security model: [SECURITY.md](SECURITY.md).

## What you get

| Piece | What it does |
|---|---|
| `App` | commands via `@app.command`, an arrow-key menu when run without arguments, generated `help`, per-machine state |
| `Screen` | full-screen layout like a modern TUI (fixed header and status line, scrolling body, redraws on resize), with a plain-lines fallback outside a real terminal (CI, pipes, agents) |
| `Step` / `run_steps` | idempotent steps: each checks first and skips what is done; a ✗ always says what to do; `check_only=True` turns a setup into a `doctor` |
| `run` / `run_live` | run programs captured, interactive, or live with progress; Ctrl+C stops the whole process tree; optional log file returning only the useful lines |
| `secret` | tokens in the OS keychain (Keychain, Credential Manager, Secret Service), asked once with hidden input; never in files or argv, masked in every output |
| `ReadOnlyClient` | JSON API client with **only GET**: a tool built on it cannot change anything, whatever the token allows. Paging, backoff, internal CA or a pinned certificate with an expiry date, same-origin redirects only |
| `temporary` | open a privileged access (VPN, tunnel, elevated credential) only for one operation and always close it |
| `write_commands` / `--dry-run` | commands declare whether they have effects; read-only commands and dry runs refuse declared write programs at runtime |
| `contract.tests(app)` | tests every tool gets for free: dry run writes nothing in an empty HOME, no tracebacks, consistent exit codes, valid `--json`, no runtime code loading, every menu entry opened in a real pty at several sizes |
| `bundle` / `self_update` | one `.pyz` file with the library inside; updates replace the file only if valid and the sha256 matches |
| `fake_programs` | fake executables on the PATH for testing flows meant for another machine |

## Try it

```bash
python3 -m pleiadi_cli_builder demo
```

A new tool, ready to edit (setup + doctor, contract tests, pre-commit with a secret scan):

```bash
python3 -m pleiadi_cli_builder new deploy-kit
```

```python
import shutil
from pleiadi_cli_builder import App, Step, run_steps

app = App("deploy-kit", title="Deploy kit", accent="#4a6cf7", lang="en")

@app.command("doctor", help="checks only", menu="Check that everything is fine")
def doctor(screen, args):
    ok = run_steps(screen, [Step("git", lambda: shutil.which("git") is not None,
                                 fix="Install git: https://git-scm.com")], check_only=True)
    return 0 if ok else 1

app.run()
```

A read-only command against an issue tracker behind a VPN:

```python
from pleiadi_cli_builder import App, ReadOnlyClient, secret, temporary, run

app = App("team-kit", title="Team kit")

@app.command("open", help="open issues of a project", args="PROJECT", effects=False)
def open_issues(screen, args):
    token = secret("team-kit.tracker", "me", screen, "Tracker API key:")
    vpn = lambda *a: run("vpn-cli", *a)[0] == 0
    with temporary(lambda: vpn("up"), lambda: vpn("down"), is_open=lambda: vpn("status"), screen=screen, label="VPN"):
        api = ReadOnlyClient("https://tracker.example", token=token, header="X-Api-Key", scheme="")
        rows = [{"id": t["id"], "title": t["subject"]}
                for t in api.pages("/issues.json", {"project_id": args[0]}, items="issues")]
    screen.table(rows)
```

`team-kit open web` shows a table; `team-kit open web --json | jq …` hands the same data to another program.

A complete example: [`examples/pm-kit`](examples/pm-kit), a tool for project managers working on any Redmine.

## Setup: run it on another computer (Python 3.8+ only)

One file from the GitHub release; check its checksum before running it.

macOS or Linux:

```bash
curl -fLO https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pleiadi-cli-builder.pyz
curl -fsL https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pleiadi-cli-builder.pyz.sha256 | shasum -a 256 -c
python3 pleiadi-cli-builder.pyz
```

Windows (PowerShell); the comparison line must print `True`:

```powershell
$u = "https://github.com/Radwtsm/pleiadi-cli-builder/releases/latest/download/pleiadi-cli-builder.pyz"
Invoke-WebRequest $u -OutFile pleiadi-cli-builder.pyz
(Get-FileHash pleiadi-cli-builder.pyz -Algorithm SHA256).Hash.ToLower() -eq (Invoke-WebRequest "$u.sha256").Content.Split(" ")[0]
py pleiadi-cli-builder.pyz
```

## Design rules

- Functions never print; only `Screen` does, so the same logic runs behind another interface or in tests.
- Every step can be rerun: check first, then act. An interrupted setup resumes where it stopped.
- Every ✗ says what to do next, naming the exact button or menu.
- Outside a real terminal everything becomes plain lines and questions take the recommended answer.
- An explicit command never leaves the screen silent: program output is shown live, never less than running the
  program alone, and no hidden machine formats are added.
- Zero dependencies: a freshly installed computer must be able to run the tool.
- Commands declare their effects; `effects=False` is enforced by the code, not by convention.
- Project configuration stays data (JSON): the library never imports or executes files supplied by others.

## Tests

```bash
for t in tests/test_*.py examples/*/tests/test_*.py; do python3 "$t" || break; done
```

CI runs them on Ubuntu, macOS and Windows. The pre-commit hook (`git config core.hooksPath .githooks`) runs the
tests and a secret scan (gitleaks when installed, a built-in scanner otherwise).

MIT license.
