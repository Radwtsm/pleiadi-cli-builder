"""pyproject.toml takes the version from __init__.__version__ (it drifted once: 0.10.0 against 0.17.0)."""
import os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from release import DYNAMIC, version_problem  # noqa: E402


class Version(unittest.TestCase):
    def test_single_source(self):
        self.assertIsNone(version_problem())

    def test_refuses_static_version(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "pyproject.toml"), "w", encoding="utf-8") as f:
                f.write('[project]\nname = "x"\nversion = "0.10.0"\n\n[tool.setuptools.dynamic]\n%s\n' % DYNAMIC)
            self.assertIn("0.10.0", version_problem(d))

    def test_refuses_missing_dynamic(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "pyproject.toml"), "w", encoding="utf-8") as f:
                f.write('[project]\nname = "x"\n')
            self.assertIsNotNone(version_problem(d))


if __name__ == "__main__":
    unittest.main()
