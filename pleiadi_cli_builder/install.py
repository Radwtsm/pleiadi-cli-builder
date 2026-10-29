"""Getting a tool onto a computer with zero setup: one file (.pyz), a launcher in ~/.local/bin on the PATH, and
a self-update that replaces the file only when it is valid (and matches its checksum, when one is published)."""
import hashlib, io, os, shutil, sys, urllib.request, zipapp, zipfile

from .proc import run
from .term import MAC, WIN

HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, ".local", "bin")


def _read(path, mode="rb"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def home_of(name):
    return os.path.join(HOME, "." + name)


def install_launcher(name, script, aliases=()):
    """Copies `script` (.py or .pyz) to ~/.<name>/ and writes the `name` command (name.cmd on Windows) in
    ~/.local/bin, adding that folder to the PATH. Returns the command's path."""
    dest_dir = home_of(name)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(script))
    if os.path.normcase(os.path.abspath(script)) != os.path.normcase(dest):
        shutil.copy(script, dest)
    os.makedirs(BIN, exist_ok=True)
    for n in (name, *aliases):
        if WIN:
            path = os.path.join(BIN, n + ".cmd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f'@"{sys.executable}" "{dest}" %*\n')
        else:
            path = os.path.join(BIN, n)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f'#!/bin/sh\nexec "{sys.executable}" "{dest}" "$@"\n')
            os.chmod(path, 0o755)
    _path_add(name)
    return os.path.join(BIN, name + (".cmd" if WIN else ""))


def _path_add(name):
    if WIN:
        run("powershell", "-NoProfile", "-Command",
            "$p=[Environment]::GetEnvironmentVariable('Path','User'); $b=\"$HOME\\.local\\bin\"; "
            "if (($p -split ';') -notcontains $b) { [Environment]::SetEnvironmentVariable('Path', \"$p;$b\", 'User') }")
    else:
        line = 'export PATH="$HOME/.local/bin:$PATH"'
        for rc in (".zshrc", ".bashrc") if MAC else (".bashrc",):
            p = os.path.join(HOME, rc)
            text = _read(p, "r") if os.path.exists(p) else ""
            if ".local/bin" not in text:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(f"\n# {name}: commands in ~/.local/bin\n{line}\n")
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if BIN not in parts:  # usable right away, without opening a new terminal
        os.environ["PATH"] = os.pathsep.join([BIN] + parts)


def download(url, timeout=60, agent="pleiadi-cli-builder"):
    req = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def self_update(url, dest, sha256_url):
    """Downloads a published version to `dest`. Replaced only if its sha256 matches the one published at
    `sha256_url` and it is valid Python (or a zip app): your own self-updating code is third-party code for whoever
    receives it, so the checksum is never optional. Returns (ok, message)."""
    try:
        new = download(url)
        want = download(sha256_url).decode().split()[0].lower()
        if hashlib.sha256(new).hexdigest() != want:
            return False, "checksum mismatch: not updated"
        if b"PK\x03\x04" in new[:4096]:  # a zip app (.pyz): must open and have its entry point
            with zipfile.ZipFile(io.BytesIO(new)) as z:
                z.getinfo("__main__.py")
        else:
            compile(new, os.path.basename(dest), "exec")
    except (OSError, SyntaxError, ValueError, KeyError, zipfile.BadZipFile) as e:
        return False, str(e)
    old = _read(dest) if os.path.exists(dest) else b""
    if new == old:
        return True, "up to date"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest + ".tmp", "wb") as f:
        f.write(new)
    os.replace(dest + ".tmp", dest)
    return True, "updated"


def bundle(source_dir, entry, out, library=True):
    """A single runnable file (`python3 out.pyz`, or `./out.pyz`): the tool's folder plus, with `library`,
    this library inside it, so the computer needs only Python. entry = "module:function". Returns the sha256."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        stage = os.path.join(tmp, "app")
        shutil.copytree(source_dir, stage, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".githooks", "tests"))
        if library:
            here = os.path.dirname(os.path.abspath(__file__))
            shutil.copytree(here, os.path.join(stage, os.path.basename(here)),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), dirs_exist_ok=True)
        zipapp.create_archive(stage, out, interpreter="/usr/bin/env python3", main=entry, compressed=True)
    digest = hashlib.sha256(_read(out)).hexdigest()
    with open(out + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{digest}  {os.path.basename(out)}\n")
    return digest
