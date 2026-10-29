"""Builds dist/pleiadi-cli-builder.pyz (+ .sha256) for a GitHub release: the builder itself in one file."""
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pleiadi_cli_builder import __version__, bundle

out = os.path.join(ROOT, "dist", "pleiadi-cli-builder.pyz")
os.makedirs(os.path.dirname(out), exist_ok=True)
with tempfile.TemporaryDirectory() as empty:
    print(__version__, bundle(empty, "pleiadi_cli_builder.__main__:main", out))
