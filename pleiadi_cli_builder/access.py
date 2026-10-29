"""Privileged access for the time of an operation only (a VPN, an elevated credential, a tunnel): opened before,
closed after, always, even when the operation fails or is interrupted."""
from contextlib import contextmanager


@contextmanager
def temporary(open_fn, close_fn, is_open=None, screen=None, label="", close_always=False):
    """
        with temporary(vpn_up, vpn_down, is_open=vpn_is_up, screen=screen, label="VPN"):
            ...  # only here the network is reachable

    open_fn/close_fn: functions (e.g. lambda: run("vpn", "up")[0] == 0). If `is_open` says it was already open
    before, it is left open afterwards: this closes only what it opened — unless close_always, which closes it
    anyway and says so. open_fn returning False = RuntimeError."""
    was_open = bool(is_open and is_open())
    if not was_open:
        if screen and label:
            with screen.wait(label):
                ok = open_fn()
        else:
            ok = open_fn()
        if ok is False:
            raise RuntimeError(f"{label or 'access'}: could not open")
    try:
        yield
    finally:
        if not was_open:
            close_fn()
        elif close_always:
            if screen:
                screen.info(f"{label or 'access'}: it was already open; closing it anyway (close_always)")
            close_fn()
