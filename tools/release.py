"""Builds the files of a GitHub release, each with its .sha256: dist/pleiadi-cli-builder.pyz (the builder itself in
one file) and dist/pm-kit.pyz (the pm-kit example with the library inside).

Refuses when pyproject.toml carries its own version instead of reading __version__ (it drifted to 0.10.0 once)."""
import os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import __version__, bundle

DYNAMIC = 'version = { attr = "pleiadi_cli_builder.__version__" }'


def version_problem(root=ROOT):
    """None when pyproject.toml takes its version from __init__.__version__, else what is wrong (Italian)."""
    with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
        text = f.read()
    project = re.search(r"^\[project\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    static = project and re.search(r'^version\s*=\s*"([^"]*)"', project.group(1), re.M)
    if static:
        return "pyproject.toml ha version = %s, __init__.py %s: usa dynamic = [\"version\"]" % (static.group(1), __version__)
    if not (project and re.search(r'^dynamic\s*=\s*\[[^\]]*"version"', project.group(1), re.M)) or DYNAMIC not in text:
        return "pyproject.toml non prende la versione da __init__.py (%s)" % DYNAMIC
    return None


def main():
    problem = version_problem()
    if problem:
        print("✗ " + problem)
        return 1
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    with tempfile.TemporaryDirectory() as empty:
        print(__version__, "pleiadi-cli-builder.pyz",
              bundle(empty, "pleiadi_cli_builder.__main__:main", os.path.join(dist, "pleiadi-cli-builder.pyz")))
    print(__version__, "pm-kit.pyz",
          bundle(os.path.join(ROOT, "examples", "pm-kit"), "pm_kit.__main__:main", os.path.join(dist, "pm-kit.pyz")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
