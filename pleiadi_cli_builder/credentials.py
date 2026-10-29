"""Secrets (tokens, API keys) in the system keychain: macOS Keychain, Windows Credential Manager, Linux Secret
Service (secret-tool). Asked once with hidden input, stored there, never in a file, an argument or an env file of
the tool. No keychain = asked every time, kept only in memory."""
import subprocess, sys

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


def keychain():
    global KEYCHAIN
    if KEYCHAIN is None:
        KEYCHAIN = system_keychain()
    return KEYCHAIN


def secret(service, account, screen=None, question=None):
    """The secret for (service, account): from the keychain, or asked once with hidden input and stored there.
    Returns None when it is missing and nobody can answer. `service` = your tool's name + what it is for (e.g.
    "deploy-kit.tracker"); `account` = the user or the server it belongs to."""
    k = keychain()
    v = k.get(service, account)
    if v:
        SECRETS.add(v)
        return v
    if screen is None or not sys.stdin.isatty():
        return None
    v = screen.secret_input(question or f"{service} ({account}):")
    if v:
        SECRETS.add(v)
        k.set(service, account, v)
    return v or None


def forget(service, account):
    """Removes a stored secret (for a rotated or wrong token): the next `secret()` asks again."""
    return keychain().delete(service, account)
