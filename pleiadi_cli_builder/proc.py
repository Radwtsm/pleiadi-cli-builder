"""Running other programs: captured, interactive (the person answers), or live into the spinner line."""
import os, re, subprocess, sys, time

from .term import SCREENS, SECRETS, WIN, mask, progress

# Windows: from a detached background run every child would flash a black console window
NO_WINDOW: dict = {"creationflags": 0x08000000} if WIN else {}
# set by App.call for the running command: the programs that write, and whether writing is forbidden now
POLICY = {"write_commands": [], "read_only": False, "dry": False}
REFUSED = []  # what check() refused in this run (the contract tests read it)


class PolicyError(RuntimeError):
    """A command refused by the rules (a secret in the arguments, a write where writing isn't allowed)."""


def check(cmd):
    """Raises RuntimeError when `cmd` may not run now: a secret in its arguments (it belongs in env=), or a declared
    write command inside a read-only command or a dry run."""
    args = [str(a) for a in cmd]
    if any(v in a for v in SECRETS for a in args):
        REFUSED.append(os.path.basename(args[0]))
        raise PolicyError(f"{os.path.basename(args[0])}: an argument contains a secret (visible to every process): "
                          "pass it with env= instead")
    if POLICY["read_only"] or POLICY["dry"]:
        names = [os.path.basename(args[0])] + args[1:]
        for w in POLICY["write_commands"]:
            if names[:len(w)] == list(w):
                why = "read-only command" if POLICY["read_only"] else "dry run"
                REFUSED.append(" ".join(w))
                raise PolicyError(f"`{' '.join(w)}` writes: not allowed in a {why}")


def run(*cmd, cwd=None, timeout=300, interactive=False, env=None):
    """(exit code, output). interactive=True: the person sees the program and answers it (a login, an installer);
    the full screen is suspended meanwhile. Output comes back with this run's secrets masked."""
    check(cmd)
    try:
        if interactive:
            tty = None
            if not WIN and sys.stdout.isatty():  # input from the real terminal, not /dev/tty: some hosts (Bun on
                tty = open(os.ttyname(sys.stdout.fileno()), "rb")  # macOS) stop on /dev/tty with «kqueue EINVAL»
            screen = SCREENS[-1] if SCREENS else None
            if screen:
                screen.suspend()
            try:
                return subprocess.run(list(cmd), cwd=cwd, stdin=tty, env=env).returncode, ""
            finally:
                if tty:
                    tty.close()
                if screen:
                    screen.resume()
        r = subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd,
                           timeout=timeout, env=env, **NO_WINDOW)
        return r.returncode, mask((r.stdout + r.stderr).strip())
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


ERROR_LINE = re.compile(r"(?i)\b(error|errore|failed|failure|fatal|exception|traceback|denied|panic)\b")


def run_live(*cmd, cwd=None, timeout=900, env=None, log=None):
    """Like run, but every line of the program (also the \\r ones of progress bars) goes into the open spinner
    line, with the percentage when the line has one. Returns (exit code, output).
    log = a file path: the whole output goes there (secrets masked); what comes back is only the error lines, the
    last line and where the log is — long builds don't flood the screen (or Claude's context)."""
    check(cmd)
    try:
        p = subprocess.Popen(list(cmd), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **NO_WINDOW)
    except OSError as e:
        return 1, str(e)
    if log:
        os.makedirs(os.path.dirname(os.path.abspath(log)), exist_ok=True)
        logf = open(log, "w", encoding="utf-8", newline="\n")
    out, rest, end = [], b"", time.time() + timeout
    try:
        while True:
            chunk = p.stdout.read1(4096)
            if not chunk:
                break
            lines = re.split(rb"[\r\n]", rest + chunk)
            rest = lines.pop()
            for r in lines:
                t = mask(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", r.decode("utf-8", "replace")).strip())
                if t:
                    out.append(t)
                    if log:
                        logf.write(t + "\n")
                    pc = re.search(r"(\d{1,3})(?:[.,]\d+)?\s?%", t)
                    progress(int(pc.group(1)) / 100 if pc and int(pc.group(1)) <= 100 else None, t)
            if time.time() > end:
                p.kill()
                out.append("timeout")
                break
    finally:
        if log:
            logf.close()
    code = p.wait()
    if log:
        errors = [t for t in out if ERROR_LINE.search(t)][-20:]
        tail = [out[-1]] if out and out[-1] not in errors else []
        return code, "\n".join(errors + tail + [f"log: {log}"])
    return code, "\n".join(out)
