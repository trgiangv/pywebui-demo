# -*- coding: utf-8 -*-
"""Transport 1: dashboard inside a WPF window hosting WebView2.

The window navigates to the hosted page (GitHub Pages, or the Vite server in dev).

Requests arrive through ``chrome.webview.postMessage``. Replies and events go
back as a ``bim-bridge`` CustomEvent dispatched with ``ExecuteScriptAsync``.
"""

from __future__ import division, print_function

import os
import traceback

from pyrevit import HOST_APP, forms
from pyrevit.script import get_logger
from pyrevit_webview import EnvelopeField, event_message, parse_request
from pyrevit_webview.adapter.revit import REVIT_CONTEXT
from pyrevit_webview.host import (
    RemoteContent,
    WebViewControl,
    WebViewSession,
    WebViewSettings,
)
from pyrevit_webview.host.wpf import WebView2, WpfUi
from pyrevit_webview.serialize import serialize
from System import Convert
from System.IO import File

from revit_dashboard import config, singleton
from revit_dashboard.service import DashboardService
from revit_dashboard.windows import create_window

_ROW_CHUNK = 250

log = get_logger()


class WebViewSink(object):
    """Delivers envelopes to the page. Large ``rows`` go out in chunks."""

    def __init__(self):
        self.control = None  # type: WebViewControl | None

    def send(self, message):
        payload = message.get(EnvelopeField.PAYLOAD) if isinstance(message, dict) else None
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) <= _ROW_CHUNK:
            self._emit(message)
            return

        msg_id = message.get(EnvelopeField.ID)
        total = len(rows)
        for start in range(0, total, _ROW_CHUNK):
            self._emit(event_message("snapshot-rows", {
                EnvelopeField.ID: msg_id,
                "start": start,
                "rows": rows[start:start + _ROW_CHUNK],
            }))

        slim = dict(payload)
        del slim["rows"]
        slim["rows_chunked"] = True
        slim["row_count"] = total
        reply = dict(message)
        reply[EnvelopeField.PAYLOAD] = slim
        self._emit(reply)
        log.info("posted {} rows in chunks of {}".format(total, _ROW_CHUNK))

    def _emit(self, message):
        # ``PostWebMessageAsJson`` queues on the dispatcher and this page never
        # observed those messages, so deliver a CustomEvent from script instead.
        literal = serialize(serialize(message))
        script = "window.dispatchEvent(new CustomEvent('bim-bridge',{detail:JSON.parse(" + literal + ")}));"
        if self.control is None or not self.control.is_available:
            log.warning("WebView is not available")
            return
        try:
            self.control.execute_script(script)
        except Exception as exc:
            log.error("emit failed ({} chars): {}".format(len(script), exc))


def show_dashboard():
    # type: () -> None
    """Open one modeless dashboard window, or activate the existing one."""
    active = singleton.get("webview_window")
    if active is not None:
        try:
            active.Activate()
            return
        except Exception:
            singleton.put("webview_window", None)

    REVIT_CONTEXT.initialize(HOST_APP.uiapp)

    try:
        sink = WebViewSink()
        window = create_window("BIM Dashboard (WebView2)", 1600, 900)
        service = DashboardService(
            sink,
            extra_commands={"SaveWorkbook": _write_workbook},
        )
        webview = WebView2() # type: WebView2
        window.Content = webview

        def on_message(raw_json):
            parsed = parse_request(raw_json)
            if parsed is not None:
                service.submit(parsed)

        control = WebViewControl(
            webview,
            _session(),
            [],
            WpfUi(window, webview),
            on_browser_ready=lambda _ready: service.subscribe(),
            on_web_message=on_message,
        )
        sink.control = control

        def on_closed(sender, args):
            service.close()
            control.dispose()
            singleton.put("webview_window", None)

        window.Closed += on_closed
        window.Show()
        singleton.put("webview_window", window)
    except Exception as ex:
        log.exception("showing WebView failed")
        forms.alert("Error showing WebView: {}\n\n{}".format(ex, traceback.format_exc()), title="Error")


def _write_workbook(payload):
    """Show the Save dialog and write the workbook bytes."""
    if not isinstance(payload, dict):
        raise TypeError("workbook payload is missing")
    content = payload.get("content_base64")
    if not content:
        raise ValueError("workbook is empty")

    filename = os.path.basename(str(payload.get("filename") or "bim_dashboard_export.xlsx"))
    path = forms.save_file(file_ext="xlsx", default_name=filename, title="Export Dashboard")
    if not path:
        return {"cancelled": True}

    File.WriteAllBytes(path, Convert.FromBase64String(content))
    return {"cancelled": False, "path": path}


def _session():
    # type: () -> WebViewSession
    dev = config.dev_mode()
    return WebViewSession(
        RemoteContent(config.page_url()),
        app_name="RevitDashboard",
        debug_cdp_port=config.DEV_CDP_PORT if dev else None,
        settings=WebViewSettings(dev_tools_enabled=dev),
    )
