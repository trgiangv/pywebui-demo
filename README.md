# pyrevit-webview-demo

One dashboard, two ways to host it. Logic and UI are shared; only the transport differs.

| Button | Host | Transport |
|--------|------|-----------|
| **WebView2** | WPF window inside Revit | `chrome.webview.postMessage` in, `bim-bridge` CustomEvent out |
| **Browser** | Your default browser | `POST /api/invoke` + Server-Sent Events `/api/events` on `127.0.0.1:<8765-8774>` |

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

The UI is **not shipped with the tool**. A release opens the page hosted on GitHub Pages
(`config.PAGES_URL`); CI publishes it from `ui/`.

| Mode | Set by | Page | WebView2 button | Browser button |
|------|--------|------|-----------------|----------------|
| Release | default | GitHub Pages | window navigates to the page | opens `<pages>/?port=<n>#token=<t>` |
| Dev | `REVIT_DASHBOARD_DEV=1` | `http://localhost:5173` | same, against Vite | same, against Vite |

Dev: run `vp dev` in `ui/` first, set the variable, reload pyRevit, click a button.
Release: reload pyRevit and click a button; nothing to build locally.

## How the page finds the right Revit

- Each Revit session binds the first free port of `8765-8774` and makes its own token.
- The Browser button opens the page with `?port=<n>#token=<t>`. The token is in the
  fragment, so the page host never receives it. A tab remembers its session for reloads.
- Several Revit sessions (other PIDs, other versions) can run at once; each tab talks to the
  one it was opened from. `GET /api/health` returns `{protocol, pid, revit}`.
- The page checks `protocol` against its own (`ui/src/lib/session.ts`, `config.PROTOCOL`) and
  shows an error if they differ. Bump both when the request contract changes.
- The server answers CORS for the page's origin only and requires the token on `/api/invoke`
  and `/api/events`. Chrome may ask permission for the page to reach the local network.
## Logs

The dashboard writes to `%TEMP%\revit_dashboard.log` (and stdout). After a button script returns, pyRevit no longer shows stdout, so use the file. `REVIT_DASHBOARD_LOG=DEBUG` adds per-category counts.

## CI

`.github/workflows/pages.yml` runs `vp check` and `vp build` with `voidzero-dev/setup-vp`
and deploys `ui/dist` to GitHub Pages on `main`; that is the page the release opens. Pages must be set to *GitHub Actions*
in the repository settings.
## Notes

- Export: WebView2 uses a native Save dialog (`SaveWorkbook` command); the
  browser saves by itself.
- UI toolchain is Vite+ (`vp install | dev | build | check | test`); versions are pinned through `ui/pnpm-workspace.yaml`.
- Not yet run inside Revit.
