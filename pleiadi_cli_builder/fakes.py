"""Fake programs for tests: scripts put at the front of PATH that always answer the same, so a flow written for
another computer (a version check, a build, an SQL client) runs anywhere, without the real tools.

    from pleiadi_cli_builder.fakes import fake_programs

    with fake_programs({"git": "git version 2.45.0",          # output, exit 0
                        "msbuild": ("error MSB1009: no project", 1),  # output and exit code
                        "sqlcmd": ""}) as fake:              # no output, exit 0
        code, out = run("git", "--version")                 # finds the fake one
        fake.path("msbuild")                                 # its full path

Mac/Linux: one `sh` script per name; Windows: `name.cmd`. The output is kept in a file beside the script, so any
text (quotes, %, $, accents) comes back as it is. Arguments are ignored. On exit PATH is restored and the folder
removed. Note for Windows: CreateProcess (subprocess with a list) finds only .exe by a bare name; a .cmd — fake or
real, like npm — is found by shutil.which(name) or fake.path(name)."""
import os, shutil, stat, tempfile
from contextlib import contextmanager

WINDOWS = os.name == "nt"


class FakePrograms:
    def __init__(self, folder, names):
        self.folder, self.names = folder, list(names)

    def path(self, name):
        """The full path of the fake `name` (on Windows with .cmd)."""
        return os.path.join(self.folder, name + (".cmd" if WINDOWS else ""))


def _answer(spec):
    if isinstance(spec, (tuple, list)):
        out, code = spec
    else:
        out, code = spec, 0
    out = "" if out is None else str(out)
    return out + ("\n" if out and not out.endswith("\n") else ""), int(code)


def write_fake(folder, name, output="", code=0):
    """One fake program in `folder`: prints `output` and exits with `code`. Returns its path."""
    if not name or os.sep in name or (os.altsep and os.altsep in name) or name.startswith("."):
        raise ValueError(f"fake program name {name!r}: a plain file name")
    out, code = _answer((output, code))
    data = os.path.join(folder, f".{name}.out")
    with open(data, "w", encoding="utf-8", newline="\n" if not WINDOWS else "\r\n") as f:
        f.write(out)
    if WINDOWS:
        path = os.path.join(folder, name + ".cmd")
        body = "@echo off\r\n" + (f'type "{data}"\r\n' if out else "") + f"exit /b {code}\r\n"
    else:
        path = os.path.join(folder, name)
        quoted = "'" + data.replace("'", "'\\''") + "'"
        body = "#!/bin/sh\n" + (f"cat {quoted}\n" if out else "") + f"exit {code}\n"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@contextmanager
def fake_programs(programs):
    """programs = {name: output} or {name: (output, exit code)}: for the block, these names at the front of PATH
    answer always the same (arguments ignored). Yields a FakePrograms (folder, path(name)); afterwards PATH is
    as before and the scripts are gone."""
    folder = tempfile.mkdtemp(prefix="pcb-fakes-")
    before = os.environ.get("PATH")
    try:
        for name, spec in programs.items():
            write_fake(folder, name, *_answer(spec))
        os.environ["PATH"] = folder + (os.pathsep + before if before else "")
        yield FakePrograms(folder, programs)
    finally:
        if before is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = before
        shutil.rmtree(folder, ignore_errors=True)
