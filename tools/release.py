"""Builds the files of a GitHub release, each with its .sha256: dist/pleiadi-cli-builder.pyz (the builder itself in
one file) and dist/pm-kit.pyz (the pm-kit example with the library inside)."""
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import __version__, bundle

DIST = os.path.join(ROOT, "dist")
os.makedirs(DIST, exist_ok=True)
with tempfile.TemporaryDirectory() as empty:
    print(__version__, "pleiadi-cli-builder.pyz",
          bundle(empty, "pleiadi_cli_builder.__main__:main", os.path.join(DIST, "pleiadi-cli-builder.pyz")))
print(__version__, "pm-kit.pyz",
      bundle(os.path.join(ROOT, "examples", "pm-kit"), "pm_kit.__main__:main", os.path.join(DIST, "pm-kit.pyz")))
