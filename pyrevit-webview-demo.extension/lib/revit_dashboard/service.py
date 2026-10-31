# -*- coding: utf-8 -*-
"""Transport-agnostic dashboard service.

Both hosts feed requests in with :meth:`DashboardService.submit` and receive
envelopes through a sink (``sink.send(envelope)``). Everything that touches
Revit runs here, on the Revit thread, through ``REVIT_CONTEXT.post``.
"""

from __future__ import division, print_function

import threading
import traceback

from Autodesk.Revit.UI.Events import SelectionChangedEventArgs
from pyrevit import DB, UI

from pyrevit_webview import (
    CommandRequest,
    EnvelopeField,
    event_message,
    response_message,
)
from pyrevit_webview.adapter.revit import REVIT_CONTEXT
from pyrevit_webview.bridge.envelope import Envelope
from pyrevit_webview.compat import Callable, Dict, Optional, Tuple
from pyrevit_webview.serialize import JsonValue

from revit_dashboard.log import get_logger
from revit_dashboard.revit_api.handler import RevitApiHandler

_LATEST_COMMANDS = ["ColorOverride", "Isolate", "ApplyGroupOverrides"]

log = get_logger()


class EnvelopeSink(object):
    """Where the service delivers responses and events. One subclass per host."""

    def send(self, message):
        # type: (Envelope) -> None
        raise NotImplementedError


class DashboardService(object):
    """Runs bridge commands one at a time on the Revit thread.

    ``_LATEST_COMMANDS`` keep only the newest pending request of that name.
    A dropped request is answered at once so its promise settles.

    ``extra_commands`` maps a command name to ``fn(payload) -> result`` for
    commands only one host can serve (for example a native Save dialog).
    """

    def __init__(self, sink, extra_commands=None):
        # type: (EnvelopeSink, Optional[Dict[str, Callable[[Dict[str, JsonValue]], Optional[JsonValue]]]]) -> None
        self._sink = sink
        self._api = RevitApiHandler()
        self._extra = extra_commands or {}
        self._pending = []  # type: list[CommandRequest]
        self._running = False
        self._lock = threading.Lock()
        self._selection_sub = None  # type: Optional[Tuple[UI.UIApplication, Callable[[UI.UIApplication, SelectionChangedEventArgs], None]]]

    # -- requests ---------------------------------------------------------

    def submit(self, parsed):
        # type: (CommandRequest) -> None
        """Queue a request. Safe from any thread."""
        dropped = []
        start = False
        with self._lock:
            if parsed.command in _LATEST_COMMANDS:
                dropped = [p for p in self._pending if p.command == parsed.command]
                self._pending = [p for p in self._pending if p.command != parsed.command]
            self._pending.append(parsed)
            if not self._running:
                self._running = True
                start = True
        for item in dropped:
            self._sink.send(response_message(item.command, item.id, payload={EnvelopeField.OK: True}))
        if start:
            REVIT_CONTEXT.post(self._pump)

    def _pump(self):
        # type: () -> None
        with self._lock:
            if not self._pending:
                self._running = False
                return
            parsed = self._pending.pop(0)
        try:
            self._run(parsed)
        finally:
            REVIT_CONTEXT.post(self._pump)

    def _run(self, parsed):
        # type: (CommandRequest) -> None
        command = parsed.command
        extra = self._extra.get(command)
        if extra is None and not self._api.knows(command):
            self._sink.send(
                response_message(command, parsed.id, error="Unknown command: {}".format(command))
            )
            return
        try:
            if extra is not None:
                result = extra(parsed.payload)
            else:
                result = self._api.run(command, parsed.payload)
            self._sink.send(response_message(command, parsed.id, payload=result))
        except Exception as exc:
            log.error("command {} failed: {}\n{}".format(command, exc, traceback.format_exc()))
            self._sink.send(response_message(command, parsed.id, error=str(exc)))

    # -- events -----------------------------------------------------------

    def subscribe(self):
        # type: () -> None
        REVIT_CONTEXT.post(self._subscribe)

    def close(self):
        # type: () -> None
        REVIT_CONTEXT.post(self._unsubscribe)

    def _subscribe(self):
        # type: () -> None
        if self._selection_sub is not None:
            return
        try:
            uiapp = REVIT_CONTEXT.uiapp

            def on_selection_changed(sender, event_args):
                try:
                    ids = []
                    for eid in REVIT_CONTEXT.uidoc.Selection.GetElementIds():
                        if not eid.Equals(DB.ElementId.InvalidElementId):
                            ids.append(eid.ToString())
                    self._sink.send(event_message("selection-changed", {"element_ids": ids}))
                except Exception as exc:
                    log.error("selection event failed: {}".format(exc))

            uiapp.SelectionChanged += on_selection_changed
            self._selection_sub = (uiapp, on_selection_changed)
            log.info("subscribed to SelectionChanged")
        except AttributeError:
            log.warning("SelectionChanged is not available on this Revit version")
        except Exception as exc:
            log.error("could not subscribe to SelectionChanged: {}".format(exc))

    def _unsubscribe(self):
        # type: () -> None
        sub = self._selection_sub
        self._selection_sub = None
        if sub is None:
            return
        try:
            sub[0].SelectionChanged -= sub[1]
            log.info("unsubscribed from SelectionChanged")
        except Exception as exc:
            log.error("unsubscribe SelectionChanged failed: {}".format(exc))
