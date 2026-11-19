# Security

## Reporting

Open a private security advisory on GitHub (Security → Report a vulnerability). Please do not open a public issue
for a vulnerability.

## Threat model

Tools built with this library run on a person's own computer, with their privileges, and often hold API tokens
for internal services. The library assumes the network and the servers it talks to may be hostile, and that a
tool's source folder may contain things that must not ship.

| Attack | Defence | Test |
|---|---|---|
| A server (or an open redirect on it) bounces an authenticated request to another host or to plain http, collecting the token | `ReadOnlyClient` follows redirects only within its own scheme + host; anything else is refused and not retried | `tests/test_security.py` |
| A token leaks through the process list or logs | secrets are refused in argv (`PolicyError`, pass them with `env=`) and masked `••••` in every output and log | `tests/test_04.py` |
| A tool with a broad token modifies data | `ReadOnlyClient` has only GET; declared write programs are refused in read-only commands and dry runs | `tests/test_04.py`, `tests/test_08.py`, contract |
| TLS interception on an internal network | system CAs or an explicit CA file; a pinned sha256 must carry an expiry date; verification is never simply switched off | `tests/test_04.py`, `tests/test_13.py` |
| A tampered or truncated update | `self_update` only over https, replaces the file only if the sha256 matches and the file is valid Python or a zip app | `tests/test_all.py`, `tests/test_security.py` |
| A developer ships `.env`, keys or a hard-coded token inside a `.pyz` | `bundle` leaves out key and env files and stops (`SecretInBundle`) when a file looks like it holds a secret | `tests/test_security.py` |
| A path with shell metacharacters runs code from the launcher | the `sh` launcher quotes paths with `shlex.quote`; the Windows `.cmd` refuses paths with `"%^&\|<>` | `tests/test_security.py` |
| Cached data readable by other users | snapshots are created `0600` in a `0700` folder, never chmod-ed afterwards | `tests/test_05.py` |
| Code injection through configuration | configuration is read only as JSON; the contract test fails on `exec`, `eval`, `importlib`, `runpy` | contract |

## Known limits

- **The update checksum comes from the same release as the file.** It catches a broken or swapped download, not a
  compromised release account. Tools that need more should pin the expected hash out of band or verify a
  signature.
- **macOS Keychain items created through `security`** are readable without a prompt by other processes of the same
  user that call `security`. The keychain protects secrets at rest and from other users, not from malware already
  running as you.
- **Programs are resolved through the PATH.** Whoever can write to a folder early in your PATH can already run code
  as you; the library does not try to defend against that.
- The Windows branches of process-tree termination are covered by CI but not by an interactive test.
