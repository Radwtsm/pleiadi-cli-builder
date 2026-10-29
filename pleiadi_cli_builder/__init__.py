"""pleiadi-cli-builder: build guided command-line tools with a full-screen layout, arrow-key menus, live
spinners and progress, rerunnable steps, a doctor, a one-file bundle and an animated intro. Standard library
only (Python 3.8+), Mac, Linux and Windows."""
from .app import App, read_json, write_json
from .install import bundle, install_launcher, self_update
from .intro import SHAPES, TINTS, Scene, play
from .proc import run, run_live
from .steps import Result, Step, run_steps
from .term import Screen, Theme, clip, key, progress

__version__ = "0.1.0"
__all__ = ["App", "Screen", "Theme", "Step", "Result", "run_steps", "run", "run_live", "progress", "Scene", "play",
           "SHAPES", "TINTS", "bundle", "install_launcher", "self_update", "read_json", "write_json", "clip", "key"]
