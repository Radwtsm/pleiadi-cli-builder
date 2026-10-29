"""pleiadi-cli-builder: build guided command-line tools with a full-screen layout, arrow-key menus, live
spinners and progress, rerunnable steps, a doctor, tables and --json, secrets in the keychain, time-boxed access,
a read-only web API client, a one-file bundle and an animated intro. Standard library
only (Python 3.8+), Mac, Linux and Windows."""
from .access import temporary
from .app import App, read_json, write_json
from .detail import Detail
from .credentials import CommandSource, ProtectedFile, check_secret, forget, secret
from .install import bundle, install_launcher, self_update
from .intro import SHAPES, TINTS, Scene, play
from .proc import PolicyError, run, run_live
from .steps import Result, Step, run_steps
from .term import Screen, Theme, clip, key, progress
from .webapi import HTTPError, ReadOnlyClient, pin_step, server_certificate

__version__ = "0.7.0"
__all__ = ["App", "Screen", "Theme", "Step", "Result", "run_steps", "run", "run_live", "progress", "Scene", "play",
           "SHAPES", "TINTS", "bundle", "install_launcher", "self_update", "read_json", "write_json", "clip", "key",
           "temporary", "secret", "forget", "ReadOnlyClient", "HTTPError", "pin_step", "PolicyError",
           "CommandSource", "ProtectedFile", "server_certificate",
           "check_secret", "Detail"]
