"""Running other programs: captured, interactive (the person answers), or live into the spinner line."""
import os, queue, re, signal, subprocess, sys, threading, time

from .term import SCREENS, SECRETS, WIN, duration, key_ready, mask, progress, role_of, RULES

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


ERROR_LINE = RULES[0][0]  # kept for who imported it; the meaning of a line: term.role_of


# a program run by run_live gets its own process group, so that stopping it stops everything it started
NEW_GROUP = 0x00000200  # Windows CREATE_NEW_PROCESS_GROUP: the child ignores Ctrl+C, we send it CTRL_BREAK
STOP_GRACE = 2.0  # seconds a program has to end by itself after each signal, before the next, harder one


class Interrupted(KeyboardInterrupt):
    """Ctrl+C (or the terminal closing) while run_live was running a program: the program and everything it started
    have been stopped. command, seconds, last (its last line of output) and log say what may be left half-done;
    App shows it as the ✗ line of the command (describe())."""

    def __init__(self, command, seconds, last="", log=None):
        super().__init__(command)
        self.command, self.seconds, self.last, self.log = command, seconds, last, log

    def describe(self, t):
        """One line in the screen's language (t = Screen.t)."""
        cmd = " ".join(self.command.split())
        cmd = cmd if len(cmd) <= 60 else cmd[:59] + "…"
        parts = [t["interrupted"].format(cmd=cmd, time=duration(self.seconds))]
        last = " ".join(self.last.split())
        parts.append(t["half_done"].format(last=last if len(last) <= 60 else last[:59] + "…") if last
                     else t["half_done_quiet"])
        if self.log:
            parts.append(f"log: {self.log}")
        return " · ".join(parts)


def _console():
    """Windows: True when this process has a console the child can share (CTRL_BREAK reaches it only there)."""
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except (OSError, AttributeError):
        return False


def _group():
    """Popen arguments that put the child (and what it starts) in a group of its own. POSIX: a new session, so the
    terminal's Ctrl+C reaches only this tool, which then stops the whole group. Windows: a new process group (the
    child ignores Ctrl+C, we send CTRL_BREAK); without a console, no window either."""
    if WIN:
        return {"creationflags": NEW_GROUP | (0 if _console() else NO_WINDOW.get("creationflags", 0))}
    return {"start_new_session": True}


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop_tree(p):
    """Stops the program `p` started by run_live and everything it started, gently first: POSIX SIGINT, SIGTERM
    then SIGKILL to its process group, STOP_GRACE seconds apart; Windows CTRL_BREAK_EVENT to its group, then
    `taskkill /T /F` (the tree) — the Windows branch is not tested on Windows yet."""
    if WIN:
        if p.poll() is None:
            try:
                os.kill(p.pid, getattr(signal, "CTRL_BREAK_EVENT", 1))
                p.wait(STOP_GRACE)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if p.poll() is None:
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=10,
                               **NO_WINDOW)
            except (OSError, subprocess.SubprocessError):
                pass
        if p.poll() is None:
            p.kill()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            pass
        return
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        p.poll()  # the leader reaped: a zombie would keep the group «alive»
        if not _group_alive(p.pid):
            break
        try:
            os.killpg(p.pid, sig)
        except (ProcessLookupError, PermissionError):
            break
        end = time.time() + (STOP_GRACE if sig != signal.SIGKILL else 5)
        while time.time() < end:
            p.poll()
            if not _group_alive(p.pid):
                break
            time.sleep(0.05)
        else:
            continue
        break
    try:
        p.wait(1)
    except subprocess.TimeoutExpired:
        pass


def _on_hangup(*_):
    raise KeyboardInterrupt  # the terminal closed: the program in its own group would keep running otherwise


def run_live(*cmd, cwd=None, timeout=900, env=None, log=None, show=10, on_line=None, rules=None,
             scrollback=500):
    """Like run, but every line of the program (also the \\r ones of progress bars) goes into the open spinner
    line, with the percentage when the line has one. Returns (exit code, output).
    show = in full screen the last lines also scroll live under the current step, colored by their meaning, like
    Claude Code (0: only the spinner line); at the end what didn't fit is counted. Meanwhile the keys scroll them
    (↑↓ PgUp PgDn Home End, the wheel): scrolled up the view stays put and counts the new lines, End follows again;
    the last `scrollback` lines are kept. Ctrl+C works all the time.
    log = a file path: the whole output goes there (secrets masked); what comes back is only the error lines, the
    last line and where the log is — long builds don't flood the screen (or Claude's context).
    on_line = a function called with each line (without colors, secrets masked) as it arrives.
    rules = [(regex, Theme role)] (e.g. term.GIT_RULES): on screen only what they catch is colored (the log and what
    comes back stay plain); with log= they also say which lines are errors, before the generic RULES.
    Ctrl+C stops the program and everything it started (its own process group) and raises Interrupted, which says
    what may be left half-done. The program has no terminal of its own: one that asks something goes in
    run(..., interactive=True)."""
    check(cmd)
    screen = SCREENS[-1] if SCREENS else None
    scroll = bool(screen and show > 0 and screen.full and screen.interactive)  # the keys are ours: the program gets no stdin
    try:
        p = subprocess.Popen(list(cmd), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL if scroll else None, **_group())
    except OSError as e:
        return 1, str(e)
    chunks = queue.Queue()

    def pump():  # in a thread: the main one stays free for Ctrl+C, the timeout and the keys
        try:
            while True:
                c = p.stdout.read1(4096)
                chunks.put(c)
                if not c:
                    return
        except (OSError, ValueError):
            chunks.put(b"")
    threading.Thread(target=pump, daemon=True).start()
    hangup = None
    if not WIN and threading.current_thread() is threading.main_thread():
        hangup = {s: signal.signal(s, _on_hangup) for s in (signal.SIGHUP, signal.SIGTERM)}
    if log:
        os.makedirs(os.path.dirname(os.path.abspath(log)), exist_ok=True)
        logf = open(log, "w", encoding="utf-8", newline="\n")
    out, rest, t0 = [], b"", time.time()
    end = t0 + timeout
    shown = 0

    def take(raw):
        nonlocal shown
        t = mask(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw.decode("utf-8", "replace")).strip())
        if not t:
            return
        out.append(t)
        if log:
            logf.write(t + "\n")  # the log stays without colors
        if on_line:
            on_line(t)
        if screen and screen.live(t, show, rules, scrollback, draw=False):
            shown += 1
        pc = re.search(r"(\d{1,3})(?:[.,]\d+)?\s?%", t)
        progress(int(pc.group(1)) / 100 if pc and int(pc.group(1)) <= 100 else None, t)
    try:
        try:
            if scroll:
                screen.live_scroll(True)
            eof = False
            while not eof:
                got, before = 0, shown
                while not eof and got < 64:  # what has arrived, then one drawing for all of it
                    try:
                        chunk = chunks.get(timeout=0.05) if not got and not scroll else chunks.get_nowait()
                    except queue.Empty:  # short waits: Ctrl+C is seen at once on Windows too
                        break
                    got += 1
                    eof = not chunk
                    lines = re.split(rb"[\r\n]", rest + chunk)
                    rest = b"" if eof else lines.pop()
                    for r in lines:
                        take(r)
                if shown != before:
                    screen.draw()
                if scroll and not eof:
                    k = key_ready(0 if got else 0.05)
                    if k:
                        screen.live_key(k)
                if not eof and time.time() > end:
                    stop_tree(p)
                    out.append("timeout")
                    break
        except KeyboardInterrupt:
            stop_tree(p)
            raise Interrupted(mask(" ".join(os.path.basename(str(a)) if i == 0 else str(a) for i, a in enumerate(cmd))),
                              time.time() - t0, out[-1] if out else "", log) from None
        except BaseException:  # on_line failed, or anything else: nothing keeps running behind us
            stop_tree(p)
            raise
    finally:
        if scroll:
            screen.live_scroll(False)
        if hangup:
            for s, h in hangup.items():
                signal.signal(s, h)
        if log:
            logf.close()
    code = p.wait()
    p.stdout.close()
    if shown > show:
        screen.out(screen.dim("    " + screen.t["more_lines"].format(n=shown - show) + (f" · log: {log}" if log else "")))
    if log:
        errors = [t for t in out if role_of(t, list(rules or []) + RULES) == "error"][-20:]
        tail = [out[-1]] if out and out[-1] not in errors else []
        return code, "\n".join(errors + tail + [f"log: {log}"])
    return code, "\n".join(out)
