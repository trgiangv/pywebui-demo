# -*- coding: utf-8 -*-
from __future__ import division, print_function

import threading
import traceback

from Autodesk.Revit import DB, UI

from pywebui import Bridge, CommandRequest, EnvelopeField, EnvelopeSink, event_message, response_message
from pywebui.adapter.revit import REVIT_CONTEXT
from pywebui.compat import Callable, Optional, Tuple

from lib.log import get_logger
from lib.revit_api.handler import RevitApiHandler

_LATEST_COMMANDS = ["ColorOverride", "Isolate", "ApplyGroupOverrides"]

log = get_logger()


class DashboardService(object):
    """Runs bridge commands one at a time on the Revit thread.

    ``_LATEST_COMMANDS`` keep only the newest pending request of that name.
    A dropped request is answered at once so its promise settles.

    ``bridge`` holds the Revit commands. A host adds the commands only it can
    serve (for example a native Save dialog) before the service runs.
    """

    def __init__(self, sink, bridge):
        # type: (EnvelopeSink, Bridge) -> None
        self._sink = sink
        self._bridge = bridge
        RevitApiHandler(bridge)
        self._pending = []  # type: list[CommandRequest]
        self._running = False
        self._lock = threading.Lock()
        self._selection_sub = None  # type: Optional[Tuple[UI.UIApplication, Callable[[UI.UIApplication, UI.Events.SelectionChangedEventArgs], None]]]

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
        log.info("run {} {}".format(parsed.command, parsed.id))
        self._sink.send(self._bridge.run(parsed))
        log.info("done {} {}".format(parsed.command, parsed.id))

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
        uiapp = REVIT_CONTEXT.uiapp

        def on_selection_changed(sender, event_args):
            # An exception escaping a Revit event handler becomes a Revit error dialog.
            try:
                ids = []
                for eid in REVIT_CONTEXT.uidoc.Selection.GetElementIds():
                    if not eid.Equals(DB.ElementId.InvalidElementId):
                        ids.append(eid.ToString())
                self._sink.send(event_message("selection-changed", {"element_ids": ids}))
            except Exception:
                log.error("selection event failed:\n{}".format(traceback.format_exc()))

        uiapp.SelectionChanged += on_selection_changed
        self._selection_sub = (uiapp, on_selection_changed)
        log.info("subscribed to SelectionChanged")

    def _unsubscribe(self):
        # type: () -> None
        sub = self._selection_sub
        self._selection_sub = None
        if sub is None:
            return
        sub[0].SelectionChanged -= sub[1]
        log.info("unsubscribed from SelectionChanged")
