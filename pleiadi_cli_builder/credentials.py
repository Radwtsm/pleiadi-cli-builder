"""Secrets (tokens, API keys) in the system keychain: macOS Keychain, Windows Credential Manager, Linux Secret
Service (secret-tool). Asked once with hidden input, stored there, never in a file, an argument or an env file of
the tool. No keychain = asked every time, kept only in memory."""
import re, subprocess, sys

from .term import MAC, SECRETS, WIN


class Keychain:
    def get(self, service, account):
        raise NotImplementedError

    def set(self, service, account, value):
        raise NotImplementedError

    def delete(self, service, account):
        raise NotImplementedError


def _quote(v):
    if '"' in v or "\\" in v or "\n" in v:
        raise ValueError("unsupported character in a keychain item")
    return f'"{v}"'


class MacKeychain(Keychain):
    def get(self, service, account):
        r = subprocess.run(["security", "find-generic-password", "-s", service, "-a", account, "-w"],
                           capture_output=True, text=True)
        return r.stdout.rstrip("\n") if r.returncode == 0 else None

    def set(self, service, account, value):
        # through `security -i` on stdin: the value never appears in the process list
        cmd = f"add-generic-password -U -s {_quote(service)} -a {_quote(account)} -w {_quote(value)}\n"
        r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True)
        return r.returncode == 0 and "error" not in (r.stdout + r.stderr).lower()

    def delete(self, service, account):
        return subprocess.run(["security", "delete-generic-password", "-s", service, "-a", account],
                              capture_output=True).returncode == 0


class SecretTool(Keychain):
    def get(self, service, account):
        r = subprocess.run(["secret-tool", "lookup", "service", service, "account", account], capture_output=True, text=True)
        return r.stdout.rstrip("\n") if r.returncode == 0 and r.stdout else None

    def set(self, service, account, value):
        return subprocess.run(["secret-tool", "store", f"--label={service} ({account})", "service", service,
                               "account", account], input=value, text=True, capture_output=True).returncode == 0

    def delete(self, service, account):
        return subprocess.run(["secret-tool", "clear", "service", service, "account", account],
                              capture_output=True).returncode == 0


class WindowsCredentials(Keychain):
    """Generic credentials of the Credential Manager, through advapi32 (no extra modules)."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.c, self.w = ctypes, wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
        self.CREDENTIAL = CREDENTIAL
        self.api = ctypes.windll.advapi32

    def _target(self, service, account):
        return f"{service}:{account}"

    def get(self, service, account):
        c = self.c
        p = c.POINTER(self.CREDENTIAL)()
        if not self.api.CredReadW(self._target(service, account), 1, 0, c.byref(p)):
            return None
        try:
            return c.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode("utf-16-le")
        finally:
            self.api.CredFree(p)

    def set(self, service, account, value):
        c = self.c
        blob = value.encode("utf-16-le")
        cred = self.CREDENTIAL(Type=1, TargetName=self._target(service, account), UserName=account, Persist=2,
                               CredentialBlobSize=len(blob), CredentialBlob=c.cast(c.create_string_buffer(blob, len(blob)),
                                                                                    c.POINTER(c.c_char)))
        return bool(self.api.CredWriteW(c.byref(cred), 0))

    def delete(self, service, account):
        return bool(self.api.CredDeleteW(self._target(service, account), 1, 0))


class MemoryOnly(Keychain):
    """No keychain on this computer (or in tests): kept for this run only."""
    def __init__(self):
        self.items = {}

    def get(self, service, account):
        return self.items.get((service, account))

    def set(self, service, account, value):
        self.items[(service, account)] = value
        return True

    def delete(self, service, account):
        return self.items.pop((service, account), None) is not None


class CommandSource:
    """Read-only: a secret another tool already keeps (a password manager's CLI, an encrypted store), read from
    the first line a program prints. cmd = argv list; "{service}" and "{account}" inside it are replaced.
        CommandSource(["op", "read", "op://team/{service}/{account}"])
    There is no set/delete: this library never writes into someone else's store."""
    def __init__(self, cmd, timeout=30):
        self.cmd, self.timeout = list(cmd), timeout

    def get(self, service, account):
        argv = [a.replace("{service}", service).replace("{account}", account) for a in self.cmd]
        try:
            r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        line = r.stdout.splitlines()[0].strip() if r.returncode == 0 and r.stdout.strip() else ""
        return line or None


class ProtectedFile:
    """Read-only: a file encrypted for the current Windows user (DPAPI, e.g. written by another tool with
    CryptProtectData / PowerShell ConvertFrom-SecureString). Only that user on that computer can read it."""
    def __init__(self, path):
        self.path = path

    def get(self, service, account):
        if not WIN:
            raise OSError("ProtectedFile (DPAPI) exists only on Windows")
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        try:
            with open(self.path, "rb") as f:
                data = f.read()
        except OSError:
            return None
        src = BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
        out = BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
            return None
        try:
            raw = ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
        for enc in ("utf-16-le", "utf-8"):
            try:
                v = raw.decode(enc).strip("\x00").strip()
                if v:
                    return v
            except UnicodeDecodeError:
                continue
        return None


def system_keychain():
    if MAC:
        return MacKeychain()
    if WIN:
        try:
            return WindowsCredentials()
        except (OSError, AttributeError):
            return MemoryOnly()
    from shutil import which
    return SecretTool() if which("secret-tool") else MemoryOnly()


KEYCHAIN = None
CLIPBOARD = None  # {"read": fn, "clear": fn}; None = the system clipboard (tests replace it)


def _clipboard():
    if CLIPBOARD:
        return CLIPBOARD
    from shutil import which
    run = lambda *c, **k: subprocess.run(list(c), capture_output=True, text=True, encoding="utf-8", **k)
    if MAC:
        return {"read": lambda: run("pbpaste").stdout, "clear": lambda: run("pbcopy", input=""),
                "write": lambda t: run("pbcopy", input=t)}
    if WIN:
        return {"read": lambda: run("powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw").stdout,
                "clear": lambda: run("cmd", "/c", "type nul | clip"),
                "write": lambda t: run("powershell", "-NoProfile", "-Command", "$input | Set-Clipboard", input=t)}
    if which("wl-paste"):
        return {"read": lambda: run("wl-paste", "-n").stdout, "clear": lambda: run("wl-copy", "--clear"),
                "write": lambda t: run("wl-copy", input=t)}
    if which("xclip"):
        return {"read": lambda: run("xclip", "-o", "-selection", "clipboard").stdout,
                "clear": lambda: run("xclip", "-i", "-selection", "clipboard", "/dev/null"),
                "write": lambda t: run("xclip", "-i", "-selection", "clipboard", input=t)}
    return None


def copy_to_clipboard(text):
    """Puts `text` (a task number, a path) in the clipboard: True if there is one. Never for secrets."""
    clip = _clipboard()
    if not clip or "write" not in clip:
        return False
    clip["write"](text)
    return True


def check_secret(value, validate=None):
    """(clean value, None) or (None, why): spaces around are dropped; control characters (a Ctrl+V that a hidden
    prompt took literally), spaces inside, or a value not matching `validate` (a regex for the whole value, or a
    function) are refused — before anything is stored."""
    v = (value or "").strip()
    if not v:
        return None, "vuota"
    if any(ord(c) < 32 or ord(c) == 127 for c in v):
        return None, "contiene caratteri di controllo (incollata con Ctrl+V? usa il clic destro, o Invio vuoto per gli appunti)"
    if any(c.isspace() for c in v):
        return None, "contiene spazi"
    ok = validate(v) if callable(validate) else (re.fullmatch(validate, v) if validate else True)
    return (v, None) if ok else (None, "non ha il formato atteso")


def keychain():
    global KEYCHAIN
    if KEYCHAIN is None:
        KEYCHAIN = system_keychain()
    return KEYCHAIN


def secret(service, account, screen=None, question=None, source=None, validate=None, tries=3):
    """The secret for (service, account): from the keychain, or asked once with hidden input and stored there.
    Returns None when it is missing and nobody can answer. `service` = your tool's name + what it is for (e.g.
    "deploy-kit.tracker"); `account` = the user or the server it belongs to.
    source = a read-only store kept by another tool (CommandSource, ProtectedFile): read from there only — never
    asked, never stored — with the same guarantees (never in arguments, masked in every output).
    validate = the expected format (regex for the whole value, or a function): checked with check_secret before
    storing; an empty answer offers the clipboard, which is cleared after reading."""
    if source is not None:
        v = source.get(service, account)
        if v:
            SECRETS.add(v)
        return v or None
    k = keychain()
    v = k.get(service, account)
    if v:
        SECRETS.add(v)
        return v
    if screen is None or not getattr(screen, "interactive", sys.stdin.isatty()):
        return None
    for _ in range(tries):
        raw = screen.secret_input(question or f"{service} ({account}):")
        clip = _clipboard() if not (raw or "").strip() else None
        if clip and screen.confirm("Prendo il valore dagli appunti (poi li svuoto)?", "Sì, dagli appunti", "No"):
            raw = clip["read"]()
            clip["clear"]()
        v, why = check_secret(raw, validate)
        if v:
            SECRETS.add(v)
            k.set(service, account, v)
            return v
        screen.todo(f"Non salvato: {why}. Riprova.")
    return None


def forget(service, account):
    """Removes a stored secret (for a rotated or wrong token): the next `secret()` asks again."""
    return keychain().delete(service, account)
