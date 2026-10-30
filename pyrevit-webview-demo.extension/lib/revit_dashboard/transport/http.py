# -*- coding: utf-8 -*-
"""Transport 2: the dashboard runs in the user's own browser over HTTP.

The same envelopes as the WebView2 host, carried by:

* ``POST /api/invoke``  request envelope in, response envelope out (held open
  until Revit has answered).
* ``GET  /api/events``  Server-Sent Events for host events (selection-changed).
* ``GET  /api/health``  liveness probe.
* ``GET  /``            the built UI from ``ui/dist`` (production mode only).

The server binds to loopback and rejects foreign ``Host`` / ``Origin`` headers,
so other web pages cannot drive Revit through it.
"""

from __future__ import division, print_function

import os
import threading
import traceback

try:
    import Queue as queue  # IronPython 2.7
except ImportError:
    import queue

# pyrevit first: it loads the WPF assemblies the System.Windows imports below need.
from pyrevit import HOST_APP, forms
from pyrevit.script import get_logger
from pyrevit_webview import EnvelopeField, EnvelopeKind, parse_request
from pyrevit_webview.adapter.revit import REVIT_CONTEXT
from pyrevit_webview.serialize import serialize
from System import TimeSpan
from System.Diagnostics import Process, ProcessStartInfo
from System.IO import File, StreamReader
from System.Net import HttpListener
from System.Text import Encoding
from System.Windows import TextWrapping, Thickness
from System.Windows.Controls import Button, StackPanel, TextBlock
from System.Windows.Threading import DispatcherTimer

from revit_dashboard import config, singleton
from revit_dashboard.service import DashboardService
from revit_dashboard.windows import create_window

_REQUEST_TIMEOUT = 300.0
_KEEPALIVE = 15.0
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json",
}
_BOOTSTRAP = '<script>window.__BIM_BRIDGE__="http"</script>'

log = get_logger()


class HttpSink(object):
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
    def __init__(self, port):
        self.port = port
        self.sink = HttpSink()
        self.service = DashboardService(self.sink)
        self._listener = None
        dev_origin = config.DEV_SERVER_URL.rstrip("/")
        self._hosts = {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}
        self._origins = {
            "http://127.0.0.1:{}".format(port),
            "http://localhost:{}".format(port),
            dev_origin,
            dev_origin.replace("localhost", "127.0.0.1"),
        }
        self._routes = {
            ("GET", "/api/health"): self._health,
            ("POST", "/api/invoke"): self._invoke,
            ("GET", "/api/events"): self._events,
        }

    @property
    def page_url(self):
        """Dev: the Vite page proxies /api to this server, so tell it to use HTTP."""
        if config.dev_mode():
            return config.DEV_SERVER_URL + "/?bridge=http"
        return "http://localhost:{}/".format(self.port)

    def start(self):
        listener = HttpListener()
        listener.Prefixes.Add("http://127.0.0.1:{}/".format(self.port))
        listener.Prefixes.Add("http://localhost:{}/".format(self.port))
        listener.Start()
        self._listener = listener
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
        path = request.Url.AbsolutePath
        if not path.startswith("/api/"):
            if request.HttpMethod != "GET":
                return _respond(response, 405, "method not allowed")
            return self._static(path, response)
        if not self._trusted(request):
            return _respond(response, 403, "forbidden")
        route = self._routes.get((request.HttpMethod, path))
        if route is None:
            return _respond(response, 404, "not found")
        route(request, response)

    def _trusted(self, request):
        origin = request.Headers["Origin"]
        if request.Headers["Host"] not in self._hosts:
            return False
        return origin is None or origin in self._origins

    # -- endpoints --------------------------------------------------------

    def _health(self, request, response):
        _respond(response, 200, '{"ok":true,"transport":"http"}', "application/json")

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

    def _static(self, path, response):
        if config.dev_mode():
            hint = "Run the Vite dev server (vp dev in ui/) and open {}?bridge=http"
            return _respond(response, 404, hint.format(config.DEV_SERVER_URL))
        root = os.path.abspath(config.UI_DIST)
        full = os.path.abspath(os.path.join(root, path.lstrip("/").replace("/", os.sep)))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            full = os.path.join(root, "index.html")  # SPA fallback
        ext = os.path.splitext(full)[1].lower()
        body = File.ReadAllBytes(full)
        if ext == ".html":
            text = Encoding.UTF8.GetString(body).replace("<head>", "<head>" + _BOOTSTRAP, 1)
            body = Encoding.UTF8.GetBytes(text)
        _respond(response, 200, body, _MIME.get(ext, "application/octet-stream"))


def _spawn(target, *args):
    thread = threading.Thread(target=target, args=args)
    thread.daemon = True
    thread.start()


def _write(out, text):
    data = Encoding.UTF8.GetBytes(text)
    out.Write(data, 0, data.Length)
    out.Flush()


def _respond(response, status, body, content_type="text/plain"):
    """Send ``body`` (text or bytes) and close the response."""
    if not hasattr(body, "Length"):  # str, not a .NET byte[]
        body = Encoding.UTF8.GetBytes(body)
    response.ContentType = content_type
    response.StatusCode = status
    response.ContentLength64 = body.Length
    response.OutputStream.Write(body, 0, body.Length)
    response.OutputStream.Close()


def _open_browser(url):
    info = ProcessStartInfo(url)
    info.UseShellExecute = True
    Process.Start(info)


def show_dashboard():
    # type: () -> None
    """Open the connection window. It owns the HTTP server: closing it stops the bridge."""
    existing = singleton.get("http_window")
    if existing is not None:
        try:
            existing.Activate()
            return
        except Exception:
            singleton.put("http_window", None)

    server = DashboardHttpServer(config.HTTP_PORT)
    try:
        REVIT_CONTEXT.initialize(HOST_APP.uiapp)
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
    button.Click += lambda sender, args: _open_browser(server.page_url)

    panel = StackPanel()
    panel.Margin = Thickness(16)
    for child in (
        status,
        label(server.page_url, 12),
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