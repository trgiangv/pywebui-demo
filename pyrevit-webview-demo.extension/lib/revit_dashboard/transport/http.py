# -*- coding: utf-8 -*-
"""Transport 2: a page hosted elsewhere (GitHub Pages) drives this Revit session.

The same envelopes as the WebView2 host, carried by:

* ``POST /api/invoke``  request envelope in, response envelope out (held open
  until Revit has answered). Needs the session token.
* ``GET  /api/events``  Server-Sent Events for host events (selection-changed).
  Needs the session token (``?token=``, since EventSource cannot set headers).
* ``GET  /api/health``  identity and protocol version. No token, so the page can
  tell instances apart before it has one.

Several Revit sessions can run at once: each binds the first free port of
``config.HTTP_PORTS`` and has its own token. The button opens the page with
``?port=<port>#token=<token>``, so a browser tab is bound to one session.

The server listens on loopback only. Cross-origin calls are accepted from the
page's origin alone (CORS allow-list); every other ``Origin`` or ``Host`` is
rejected.
"""

from __future__ import division, print_function

import binascii
import os
import threading
import traceback

try:
    import Queue as queue  # IronPython 2.7
except ImportError:
    import queue

import clr

# pyrevit first: it loads the WPF assemblies the System.Windows imports below need.
from pyrevit import forms
from pyrevit.compat import NETCORE

# pyrevit does not load HttpListener: System.Net.HttpListener.dll on .NET 8, System.dll on Framework.
clr.AddReference("System.Net.HttpListener" if NETCORE else "System")
from revit_dashboard.log import get_logger
from pyrevit_webview import EnvelopeField, EnvelopeKind, parse_request
from pyrevit_webview.adapter.revit import REVIT_CONTEXT
from pyrevit_webview.serialize import serialize
from System import TimeSpan
from System.Diagnostics import Process, ProcessStartInfo
from System.IO import StreamReader
from System.Net import HttpListener
from System.Text import Encoding
from System.Windows import TextWrapping, Thickness
from System.Windows.Controls import Button, StackPanel, TextBlock
from System.Windows.Threading import DispatcherTimer

from revit_dashboard import config, singleton
from revit_dashboard.service import DashboardService, EnvelopeSink
from revit_dashboard.windows import create_window

_REQUEST_TIMEOUT = 300.0
_KEEPALIVE = 15.0
_TOKEN_HEADER = "X-Bim-Token"

log = get_logger()


class HttpSink(EnvelopeSink):
    """Routes responses to the waiting HTTP request and events to SSE clients."""

    def __init__(self):
        self._lock = threading.Lock()
        self._waiting = {}  # request id -> (Event, [envelope])
        self._clients = []  # list of Queue

    def request(self, request_id, submit, timeout):
        """Run ``submit`` and wait for the response with this id. ``None`` on timeout."""
        slot = (threading.Event(), [None])
        with self._lock:
            self._waiting[request_id] = slot
        submit()
        if slot[0].wait(timeout):
            return slot[1][0]
        with self._lock:
            self._waiting.pop(request_id, None)
        return None

    def client_count(self):
        with self._lock:
            return len(self._clients)

    def add_client(self):
        client = queue.Queue()
        with self._lock:
            self._clients.append(client)
        return client

    def remove_client(self, client):
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def send(self, message):
        if message.get(EnvelopeField.TYPE) == EnvelopeKind.RESPONSE:
            with self._lock:
                slot = self._waiting.pop(message.get(EnvelopeField.ID), None)
            if slot is not None:
                slot[1][0] = message
                slot[0].set()
            return
        with self._lock:
            clients = list(self._clients)
        if clients:
            text = serialize(message)
            for client in clients:
                client.put(text)


class DashboardHttpServer(object):
    def __init__(self):
        self.sink = HttpSink()
        self.service = DashboardService(self.sink)
        self.port = None
        self.token = binascii.hexlify(os.urandom(16)).decode("ascii")
        self._listener = None
        self._hosts = set()
        self._origins = {config.page_origin()}
        self._info = None
        # (method, path) -> (handler, needs token)
        self._routes = {
            ("GET", "/api/health"): (self._health, False),
            ("POST", "/api/invoke"): (self._invoke, True),
            ("GET", "/api/events"): (self._events, True),
        }

    @property
    def page_url(self):
        """The hosted page, bound to this session by its port and token."""
        base = config.page_url().rstrip("/") + "/"
        return "{}?port={}#token={}".format(base, self.port, self.token)

    def start(self):
        """Bind the first free port. Call on the Revit thread."""
        self._listener = self._bind()
        self._hosts = {"127.0.0.1:{}".format(self.port), "localhost:{}".format(self.port)}
        self._info = serialize({
            "ok": True,
            "transport": "http",
            "protocol": config.PROTOCOL,
            "pid": os.getpid(),
            "revit": REVIT_CONTEXT.version,
        })
        _spawn(self._accept_loop)
        self.service.subscribe()
        log.info("HTTP dashboard listening on port {}".format(self.port))

    def stop(self):
        self.service.close()
        listener, self._listener = self._listener, None
        if listener is not None:
            try:
                listener.Stop()
                listener.Close()
            except Exception:
                pass

    def _bind(self):
        for port in config.HTTP_PORTS:
            listener = HttpListener()
            listener.Prefixes.Add("http://127.0.0.1:{}/".format(port))
            listener.Prefixes.Add("http://localhost:{}/".format(port))
            try:
                listener.Start()
            except Exception:
                listener.Close()
                continue  # in use by another Revit session
            self.port = port
            return listener
        raise RuntimeError(
            "no free port in {}-{}".format(config.HTTP_PORTS[0], config.HTTP_PORTS[-1])
        )

    def _accept_loop(self):
        while self._listener is not None:
            try:
                context = self._listener.GetContext()
            except Exception:
                return  # listener stopped
            _spawn(self._handle, context)

    def _handle(self, context):
        request, response = context.Request, context.Response
        try:
            self._dispatch(request, response)
        except Exception as exc:
            log.error("http request failed: {}\n{}".format(exc, traceback.format_exc()))
            try:
                _respond(response, 500, "internal error")
            except Exception:
                pass  # response already closed

    def _dispatch(self, request, response):
        origin = request.Headers["Origin"]
        if request.Headers["Host"] not in self._hosts:
            return _respond(response, 403, "forbidden")
        if origin is not None:
            if origin not in self._origins:
                return _respond(response, 403, "forbidden")
            _allow_origin(response, origin)
        if request.HttpMethod == "OPTIONS":
            return _respond(response, 204, "")  # CORS preflight
        route = self._routes.get((request.HttpMethod, request.Url.AbsolutePath))
        if route is None:
            return _respond(response, 404, "not found")
        handler, needs_token = route
        if needs_token and not self._authorized(request):
            return _respond(response, 401, "missing or wrong token")
        handler(request, response)

    def _authorized(self, request):
        token = request.Headers[_TOKEN_HEADER] or request.QueryString["token"]
        return token == self.token

    # -- endpoints --------------------------------------------------------

    def _health(self, request, response):
        _respond(response, 200, self._info, "application/json")

    def _invoke(self, request, response):
        if "json" not in (request.ContentType or "").lower():
            return _respond(response, 415, "expected application/json")
        parsed = parse_request(StreamReader(request.InputStream, Encoding.UTF8).ReadToEnd())
        if parsed is None:
            return _respond(response, 400, '{"error":"invalid request envelope"}', "application/json")

        reply = self.sink.request(parsed.id, lambda: self.service.submit(parsed), _REQUEST_TIMEOUT)
        if reply is None:
            return _respond(response, 504, '{"error":"Revit did not answer in time"}', "application/json")
        _respond(response, 200, serialize(reply), "application/json")

    def _events(self, request, response):
        response.ContentType = "text/event-stream"
        response.Headers.Add("Cache-Control", "no-cache")
        response.SendChunked = True
        out = response.OutputStream
        client = self.sink.add_client()
        try:
            _write(out, ": connected\n\n")
            while self._listener is not None:
                try:
                    _write(out, "data: {}\n\n".format(client.get(True, _KEEPALIVE)))
                except queue.Empty:
                    _write(out, ": ping\n\n")
        except Exception:
            pass  # client went away
        finally:
            self.sink.remove_client(client)
            try:
                response.Abort()
            except Exception:
                pass


def _spawn(target, *args):
    thread = threading.Thread(target=target, args=args)
    thread.daemon = True
    thread.start()


def _write(out, text):
    data = Encoding.UTF8.GetBytes(text)
    out.Write(data, 0, data.Length)
    out.Flush()


def _allow_origin(response, origin):
    """CORS for the one allowed page. The private-network header answers Chrome's preflight."""
    headers = response.Headers
    headers.Add("Access-Control-Allow-Origin", origin)
    headers.Add("Vary", "Origin")
    headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    headers.Add("Access-Control-Allow-Headers", "Content-Type, " + _TOKEN_HEADER)
    headers.Add("Access-Control-Allow-Private-Network", "true")
    headers.Add("Access-Control-Max-Age", "600")


def _respond(response, status, body, content_type="text/plain"):
    """Send ``body`` (text) and close the response."""
    data = Encoding.UTF8.GetBytes(body)
    response.ContentType = content_type
    response.StatusCode = status
    response.ContentLength64 = data.Length
    response.OutputStream.Write(data, 0, data.Length)
    response.OutputStream.Close()


def _open_browser(url):
    info = ProcessStartInfo(url)
    info.UseShellExecute = True
    Process.Start(info)


def show_dashboard(uiapp):
    # type: (UIApplication) -> None
    """Open the connection window. It owns the HTTP server: closing it stops the bridge."""
    existing = singleton.get("http_window")
    if existing is not None:
        try:
            existing.Activate()
            return
        except Exception:
            singleton.put("http_window", None)

    server = DashboardHttpServer()
    try:
        REVIT_CONTEXT.initialize(uiapp)
        server.start()
        window = _build_window(server)
        window.Show()
        singleton.put("http_window", window)
        _open_browser(server.page_url)
    except Exception as ex:
        log.exception("starting HTTP dashboard failed")
        server.stop()
        forms.alert("Could not start the dashboard server: {}".format(ex), title="Error")


def _build_window(server):
    """Modeless window that keeps the connection alive and shows its state."""
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
    button.Click += lambda sender, args: _open_browser(server.page_url)  # pyright: ignore[reportOperatorIssue]

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
