# -*- coding: utf-8 -*-
from __future__ import division, print_function

import os
import webbrowser

from Autodesk.Revit import UI
from System import TimeSpan
from System.Windows import TextWrapping, Thickness
from System.Windows.Controls import Button, StackPanel, TextBlock
from System.Windows.Threading import DispatcherTimer

from pywebui import Bridge
from pywebui.adapter.revit import REVIT_CONTEXT
from pywebui.http import HttpSink, HttpTransport

from lib import config, singleton
from lib.log import get_logger
from lib.service import DashboardService
from lib.windows import create_window

log = get_logger()


class DashboardHttpServer(object):
    def __init__(self):
        self.sink = HttpSink()
        self.service = DashboardService(self.sink, Bridge())
        self.site = config.site()
        self.transport = None

    @property
    def port(self):
        return self.transport.port

    @property
    def page_url(self):
        return self.site.browser_url(self.port, self.transport.token)

    def start(self):
        """Bind the first free port and serve. Call on the Revit thread."""
        self.transport = HttpTransport(
            self.sink,
            self.service.submit,
            site=self.site,
            ports=config.HTTP_PORTS,
            info={"protocol": config.PROTOCOL, "revit": REVIT_CONTEXT.version},
            token_header="X-Bim-Token",
            title="BIM Dashboard",
        )
        self.transport.start()
        self.service.subscribe()

    def stop(self):
        self.service.close()
        self.transport.stop()


def show_dashboard(uiapp):
    # type: (UI.UIApplication) -> None
    existing = singleton.get("http_window")
    if existing is not None:
        existing.Activate()  # Closed clears the singleton, so this window is still open
        return

    server = DashboardHttpServer()
    REVIT_CONTEXT.initialize(uiapp)
    server.start()
    try:
        window = _build_window(server)
        window.Show()
    except Exception:
        server.stop()
        raise
    singleton.put("http_window", window)
    webbrowser.open(server.page_url)


def _build_window(server):
    window = create_window("BIM Dashboard (Browser)", 380)

    def label(text, bottom, wrap=False):
        block = TextBlock()
        block.Text = text
        block.Margin = Thickness(0, 0, 0, bottom)
        if wrap:
            block.TextWrapping = TextWrapping.Wrap
        return block

    status = label("", 4)
    button = Button()
    button.Content = "Open in browser"
    button.Padding = Thickness(8, 4, 8, 4)
    button.Click += lambda sender, args: webbrowser.open(server.page_url)

    panel = StackPanel()
    panel.Margin = Thickness(16)
    for child in (
        status,
        label("Revit {}  |  PID {}  |  port {}".format(REVIT_CONTEXT.version, os.getpid(), server.port), 12),
        label("Keep this window open. Closing it disconnects the browser.", 12, wrap=True),
        button,
    ):
        panel.Children.Add(child)
    window.Content = panel

    def refresh(sender=None, args=None):
        status.Text = "Connected browsers: {}".format(server.sink.client_count())

    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromSeconds(1)
    timer.Tick += refresh
    timer.Start()
    refresh()

    def on_closed(sender, args):
        timer.Stop()
        server.stop()
        singleton.put("http_window", None)

    window.Closed += on_closed
    return window
