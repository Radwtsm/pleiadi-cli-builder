"""Privileged access for the time of an operation only (a VPN, an elevated credential, a tunnel): opened before,
closed after, always, even when the operation fails or is interrupted.

Inside the interactive menu (`session()`, opened by App.menu) an access opened for one action stays open for the
next ones, so the person isn't reconnected at every choice: it closes when the tool exits (also on Ctrl+C or an
error) and after `idle_minutes` without actions. Outside the menu (one command, a script) nothing changes."""
import atexit, threading, time
from contextlib import contextmanager

SESSION = None


class _Session:
    def __init__(self, idle_minutes, check_every):
        self.idle, self.open, self.lock = idle_minutes * 60, {}, threading.RLock()  # label → [close, since, last, in use]
        self.stop = threading.Event()
        threading.Thread(target=self._watch, args=(check_every,), daemon=True).start()

    def _watch(self, every):
        while not self.stop.wait(every):
            with self.lock:
                for label, (close, since, last, busy) in list(self.open.items()):
                    if not busy and time.time() - last > self.idle:
                        self._close(label)

    def _close(self, label):
        close = self.open.pop(label)[0]
        try:
            close()
        except Exception:  # closing must never stop closing the others
            pass

    def close_all(self):
        self.stop.set()
        with self.lock:
            for label in list(self.open):
                self._close(label)


@contextmanager
def session(idle_minutes=5, check_every=5):
    """The menu's session: accesses opened inside stay open until it ends or they sit idle `idle_minutes`."""
    global SESSION
    s = _Session(idle_minutes, check_every)
    SESSION = s
    atexit.register(s.close_all)  # also when the process ends some other way
    try:
        yield s
    finally:
        SESSION = None
        s.close_all()


def status_line():
    """«VPN aperta da 4 min» for the fixed bottom line while the menu keeps an access open; "" otherwise."""
    s = SESSION
    if not s:
        return ""
    with s.lock:
        return " · ".join(f"{label} aperta da {int((time.time() - since) // 60)} min"
                          for label, (_, since, _, _) in s.open.items())


@contextmanager
def temporary(open_fn, close_fn, is_open=None, screen=None, label="", close_always=False):
    """
        with temporary(vpn_up, vpn_down, is_open=vpn_is_up, screen=screen, label="VPN"):
            ...  # only here the network is reachable

    open_fn/close_fn: functions (e.g. lambda: run("vpn", "up")[0] == 0). If `is_open` says it was already open
    before, it is left open afterwards: this closes only what it opened — unless close_always, which closes it
    anyway and says so. open_fn returning False = RuntimeError. Inside the menu's session() an access with a label
    stays open for the next actions (see the module)."""
    s = SESSION
    if s and label and not close_always:
        with s.lock:
            kept = s.open.get(label)
            if kept:
                kept[3] += 1
        if kept:
            try:
                yield
            finally:
                with s.lock:
                    kept[2], kept[3] = time.time(), kept[3] - 1
            return
    was_open = bool(is_open and is_open())
    if not was_open:
        if screen and label:
            with screen.wait(label):
                ok = open_fn()
        else:
            ok = open_fn()
        if ok is False:
            raise RuntimeError(f"{label or 'access'}: could not open")
    if s and label and not close_always and not was_open:
        entry = [close_fn, time.time(), time.time(), 1]
        with s.lock:
            s.open[label] = entry
        try:
            yield
        finally:
            with s.lock:
                entry[2], entry[3] = time.time(), entry[3] - 1
        return
    try:
        yield
    finally:
        if not was_open:
            close_fn()
        elif close_always:
            if screen:
                screen.info(f"{label or 'access'}: it was already open; closing it anyway (close_always)")
            close_fn()
