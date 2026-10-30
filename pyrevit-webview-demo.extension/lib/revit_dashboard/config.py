# -*- coding: utf-8 -*-
"""Paths and switches shared by both hosts (WebView2 and browser)."""

from __future__ import division, print_function

import os

_LIB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSION_DIR = os.path.dirname(_LIB_DIR)  # type: str
UI_DIR = os.path.join(EXTENSION_DIR, "ui")  # type: str
UI_DIST = os.path.join(UI_DIR, "dist")  # type: str

DEV_SERVER_URL = "http://localhost:5173"  # type: str
DEV_CDP_PORT = 9225  # type: int
HTTP_PORT = 8765  # type: int
HTTP_HOST = "127.0.0.1"  # type: str


def dev_mode():
    # type: () -> bool
    """True serves the page from the Vite dev server.

    ``REVIT_DASHBOARD_DEV=1`` / ``0`` forces it. Otherwise dev mode is on only
    when ``ui/dist`` has not been built.
    """
    flag = os.environ.get("REVIT_DASHBOARD_DEV")
    if flag is not None:
        return flag.strip().lower() in ("1", "true", "yes")
    return not os.path.isfile(os.path.join(UI_DIST, "index.html"))
