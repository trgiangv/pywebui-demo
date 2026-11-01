# -*- coding: utf-8 -*-
from __future__ import division, print_function

import os

from pywebui import Mode, Site
from pywebui.runtime import find_python, packages_dir

# Where the dashboard page comes from. Mode.DEV: Vite at DEV_SERVER_URL. Mode.LOCAL: ui/dist after `vp build`.
# Mode.SERVER: the page deployed to PAGES_URL.
MODE = Mode.SERVER
PAGES_URL = "https://trgiangv.github.io/pywebui-demo/"
DEV_SERVER_URL = "http://localhost:5173"
DIST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "ui", "dist"))
DEV_CDP_PORT = 9225
# Bumped when the request/response contract changes. The page checks it against
# /api/health and refuses to talk to a tool it does not understand.
PROTOCOL = 1
HTTP_PORTS = tuple(range(8765, 8775))
CPYTHON_ENGINE = "CPY312"
EMBEDDED_REFERENCES = (
    "RevitAPI",
    "RevitAPIUI",
    "UIFramework",
    "WindowsBase",
    "PresentationCore",
    "PresentationFramework",
)
PYWEBUI_LIB_DIR = os.path.join(os.environ["APPDATA"], "pyRevit", "Extensions", "pyWebUI.lib")


def site():
    # type: () -> Site
    return Site(MODE, dev_url=DEV_SERVER_URL, server_url=PAGES_URL, dist_dir=DIST_DIR)


def embed_paths():
    # type: () -> tuple[str, str, str, list[str], tuple[str, ...]]
    """Arguments of ``pywebui.embed.start``, from pyRevit's bin folder. Only the IronPython launcher calls this."""
    from pyrevit import ROOT_BIN_DIR
    from System import Environment

    runtime_folder = "netcore" if Environment.Version.Major >= 8 else "netfx"
    runtime_dll = os.path.join(ROOT_BIN_DIR, runtime_folder, "pyRevitLabs.PythonNet.dll")
    python_home = os.path.dirname(find_python(os.path.join(ROOT_BIN_DIR, "cengines"), CPYTHON_ENGINE))
    python_dll = os.path.join(python_home, "python312.dll")
    pushbutton_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys_path = [pushbutton_dir, PYWEBUI_LIB_DIR, packages_dir("cp312")]
    return runtime_dll, python_dll, python_home, sys_path, EMBEDDED_REFERENCES
