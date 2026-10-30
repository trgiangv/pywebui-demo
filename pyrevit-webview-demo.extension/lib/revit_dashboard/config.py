# -*- coding: utf-8 -*-
"""Addresses and switches shared by both hosts (WebView2 and browser).

The UI is not shipped with the tool. A release opens the page hosted on GitHub
Pages; the page talks back to this Revit session.
"""

from __future__ import division, print_function

import os

PAGES_URL = "https://trgiangv.github.io/pyrevit-webview-demo/"  # type: str
DEV_SERVER_URL = "http://localhost:5173"  # type: str
DEV_CDP_PORT = 9225  # type: int

# Bumped when the request/response contract changes. The page checks it against
# /api/health and refuses to talk to a tool it does not understand.
PROTOCOL = 1  # type: int

# One Revit session binds the first free port of the range.
HTTP_HOST = "127.0.0.1"  # type: str
HTTP_PORTS = tuple(range(8765, 8775))  # type: tuple[int, ...]


def dev_mode():
    # type: () -> bool
    """True opens the Vite dev server instead of GitHub Pages (``REVIT_DASHBOARD_DEV=1``)."""
    return os.environ.get("REVIT_DASHBOARD_DEV", "").strip().lower() in ("1", "true", "yes")


def page_url():
    # type: () -> str
    return DEV_SERVER_URL if dev_mode() else PAGES_URL


def page_origin():
    # type: () -> str
    """Scheme and host of the page, as a browser sends it in ``Origin``."""
    parts = page_url().split("/")
    return "/".join(parts[:3])
