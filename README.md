# pyrevit-webview-demo

One dashboard, two ways to host it. Logic and UI are shared; only the transport differs.

| Button | Host | Transport |
|--------|------|-----------|
| **WebView2** | WPF window inside Revit | `chrome.webview.postMessage` in, `bim-bridge` CustomEvent out |
| **Browser** | Your default browser | `POST /api/invoke` + Server-Sent Events `/api/events` on `127.0.0.1:8765` |

```
ui/ (React)  ──BridgeClient──┬─ webview ─► transport/webview.py ─┐
                             ├─ http ────► transport/http.py ────┼─► service.py ─► revit_api/handler.py ─► Revit
                             └─ mock (plain browser, no Revit)   │      (queue, one command at a time
                                                                 ┘       on the Revit thread)
```

Shared: `lib/revit_dashboard/{data,revit_api,service.py}` and all of `ui/`.
Same envelope (`request` / `response` / `event`) on both transports, so the UI
has one code path above `BridgeClient`.

The **Browser** button opens a small connection window in Revit that owns the HTTP server and shows how many browsers are connected. Keep it open while you work in the browser; closing it stops the server. **WebView2** opens the dashboard itself in a window, as usual.

## Layout

The repo root is the pyRevit search path; everything below lives in `pyrevit-webview-demo.extension/` (`*.tab`, `lib/`, `ui/`, `extension.json`).

## Setup (once)

1. `pyrevit extend lib pyrevit-webview https://github.com/trgiangv/pyrevit-webview.git`
2. `pyrevit extensions paths add <repo root>`, then reload pyRevit.
3. `cd pyrevit-webview-demo.extension/ui && vp install`

## Start

Both buttons need a page to show. Today that page comes from one of two places:

| Mode | When | What to run first | WebView2 button | Browser button |
|------|------|-------------------|-----------------|----------------|
| Dev | `ui/dist` is missing, or `REVIT_DASHBOARD_DEV=1` | `vp dev` in `ui/` (keep it running, port 5173) | navigates to `http://localhost:5173` | opens `http://localhost:5173/?bridge=http`; Vite proxies `/api` to Revit |
| Local build | `ui/dist` exists | `vp build` in `ui/` | maps `ui/dist` to `https://app.local` | server on `127.0.0.1:8765` serves `ui/dist` |

Order: start `vp dev` (dev mode only), reload pyRevit, click a button.
The **Browser** button keeps its connection window open; close it to stop the server.

Hosting the page on GitHub Pages (CI below) is not wired into the buttons yet: the
Python server still needs CORS, a session token and a port range first.

## CI

`.github/workflows/pages.yml` runs `vp check` and `vp build` with `voidzero-dev/setup-vp`
and deploys `ui/dist` to GitHub Pages on `main`. Pages must be set to *GitHub Actions*
in the repository settings.
## Notes

- The browser host binds loopback only and rejects foreign `Host` / `Origin`
  headers and non-JSON bodies, so other web pages cannot drive Revit.
- Export: WebView2 uses a native Save dialog (`SaveWorkbook` command); the
  browser saves by itself.
- UI toolchain is Vite+ (`vp install | dev | build | check | test`); versions are pinned through `ui/pnpm-workspace.yaml`.
- Not yet run inside Revit.
