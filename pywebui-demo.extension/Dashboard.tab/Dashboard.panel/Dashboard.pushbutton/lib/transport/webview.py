# -*- coding: utf-8 -*-
from __future__ import division, print_function

import os
import traceback

from Autodesk.Revit import UI
from Microsoft.Win32 import SaveFileDialog
from lib.log import get_logger
from pywebui import Bridge, EnvelopeField, EnvelopeSink, event_message, parse_request
from pywebui.adapter.revit import REVIT_CONTEXT
from pywebui.webview import (
    WebViewControl,
    WebViewSession,
    WebViewSettings,
)
from pywebui.webview.wpf import WebView2, WpfUi
from pywebui.serialize import serialize
from System import Convert
from System.IO import File

from lib import config, singleton
from lib.service import DashboardService
from lib.windows import create_window

_ROW_CHUNK = 250

log = get_logger()


class WebViewSink(EnvelopeSink):
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


def show_dashboard(uiapp):
    # type: (UI.UIApplication) -> None
    active = singleton.get("webview_window")
    if active is not None:
        active.Activate()
        return

    REVIT_CONTEXT.initialize(uiapp)

    try:
        sink = WebViewSink()
        window = create_window("BIM Dashboard (WebView2)", 1600, 900)
        bridge = Bridge()
        bridge.add("SaveWorkbook", _write_workbook)
        service = DashboardService(sink, bridge)
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
        UI.TaskDialog.Show("BIM Dashboard", "Error showing WebView: {}\n\n{}".format(ex, traceback.format_exc()))


def _write_workbook(payload):
    if not isinstance(payload, dict):
        raise TypeError("workbook payload is missing")
    content = payload.get("content_base64")
    if not content:
        raise ValueError("workbook is empty")

    filename = os.path.basename(str(payload.get("filename") or "bim_dashboard_export.xlsx"))
    dialog = SaveFileDialog()
    dialog.Title = "Export Dashboard"
    dialog.Filter = "Excel workbook (*.xlsx)|*.xlsx"
    dialog.FileName = filename
    if not dialog.ShowDialog():
        return {"cancelled": True}

    File.WriteAllBytes(dialog.FileName, Convert.FromBase64String(content))
    return {"cancelled": False, "path": dialog.FileName}


def _session():
    # type: () -> WebViewSession
    site = config.site()
    return WebViewSession(
        site.webview_content(),
        app_name="RevitDashboard",
        debug_cdp_port=config.DEV_CDP_PORT if site.dev else None,
        settings=WebViewSettings(dev_tools_enabled=site.dev),
    )
