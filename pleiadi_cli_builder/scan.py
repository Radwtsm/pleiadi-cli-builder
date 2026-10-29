"""Secrets in what is about to be committed, with the standard library only: the fallback of the pre-commit hook
when gitleaks isn't installed (gitleaks finds more: prefer it when it is there)."""
import re, subprocess

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("AWS key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Anthropic/OpenAI key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}\b")),
    ("password or token in the code", re.compile(
        r"""(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d|pwd)\b["']?\s*[:=]\s*["'][^"'\s$<>{}]{12,}["']""")),
]


def text(content):
    """[(kind, line number)] of the secrets in a text: one per line, the most specific kind."""
    found = []
    for n, line in enumerate(content.splitlines(), 1):
        if "scan: ok" in line:
            continue
        kind = next((k for k, rx in PATTERNS if rx.search(line)), None)
        if kind:
            found.append((kind, n))
    return found


def staged(repo="."):
    """[(path, kind, line)] in the staged version of every added or changed file."""
    names = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=repo,
                           capture_output=True).stdout.decode("utf-8", "replace").split("\0")
    found = []
    for p in filter(None, names):
        blob = subprocess.run(["git", "show", f":{p}"], cwd=repo, capture_output=True).stdout
        if b"\0" in blob[:8000]:  # binary
            continue
        found += [(p, kind, n) for kind, n in text(blob.decode("utf-8", "replace"))]
    return found
