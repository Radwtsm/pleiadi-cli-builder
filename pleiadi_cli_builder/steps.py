"""Steps that can be rerun: each one checks first and skips what is already done, so a setup interrupted
halfway resumes where it stopped. The same steps in check-only mode are a `doctor`."""
import time


class Result:
    """fix = what to do when it fails (shown only with ✗); note = detail shown with ✓.
    retry = function that redoes the step and returns True if it now works: offered on the spot."""
    def __init__(self, name, ok, fix="", skipped=False, note="", retry=None):
        self.name, self.ok, self.fix, self.skipped, self.note, self.retry = name, ok, fix, skipped, note, retry

    def __repr__(self):
        return f"Result({self.name!r}, ok={self.ok}, skipped={self.skipped})"


class Step:
    """check() → True when already done (or a short note string); apply() → True/False or (ok, note).
    fix = the instruction for the person when apply fails or there is nothing to apply (check-only)."""
    def __init__(self, name, check, apply=None, fix="", why="", wait=""):
        self.name, self.check, self.apply, self.fix, self.why, self.wait = name, check, apply, fix, why, wait


def _norm(v):
    if isinstance(v, tuple):
        return bool(v[0]), str(v[1] or "")
    return bool(v), (v if isinstance(v, str) else "")


def run_steps(screen, steps, check_only=False):
    """Runs the steps with ⏺ n/total, ✓/✗ and the summary box. check_only = change nothing (doctor).
    Returns True when everything is ok."""
    start = time.time()
    for n, s in enumerate(steps, 1):
        screen.step(n, len(steps), s.name, s.why)
        try:
            done, note = _norm(s.check())
        except Exception as e:  # a broken check is a ✗ with the reason, not a crash
            done, note = False, str(e)
        if done:
            screen.result(Result(s.name, True, skipped=True, note=note))
            continue
        if check_only or not s.apply:
            screen.result(Result(s.name, False, fix=s.fix or note))
            continue
        try:
            if s.wait:
                with screen.wait(s.wait):
                    ok, note = _norm(s.apply())
            else:
                ok, note = _norm(s.apply())
        except Exception as e:
            ok, note = False, str(e)
        retry = (lambda s=s: _norm(s.apply())[0]) if not ok else None
        screen.result(Result(s.name, ok, fix="\n".join(x for x in (s.fix, note if not ok else "") if x),
                             note=note if ok else "", retry=retry))
    return screen.summary(round((time.time() - start) / 60))
