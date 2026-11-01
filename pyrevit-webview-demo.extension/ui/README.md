# BIM Dashboard UI

React page for the open Revit document. Revit hosts it in WebView2 or the default browser. Opened on its own, it uses mock data.

## Run

```powershell
vp install
vp dev
```

Open http://localhost:5173 for mock data with no Revit.

The page picks its data source on load:

| Where it runs                                                | Source                               |
| ------------------------------------------------------------ | ------------------------------------ |
| Inside the Revit WebView2 window                             | `chrome.webview` bridge              |
| URL has `?port=<n>#token=<t>` (opened by the Browser button) | HTTP + SSE to `http://127.0.0.1:<n>` |
| Anywhere else                                                | mock data                            |

The released page is hosted on GitHub Pages. In Revit, `MODE` in `lib/config.py` picks the source for both hosts: `Mode.SERVER` (Pages, default), `Mode.DEV` (this dev server) or `Mode.LOCAL` (`dist` after `vp build`).

## Check

```powershell
vp check
vp build
```

## Stack

React 19, TypeScript, Vite+, Semi Design, Apache ECharts, and `lucide-react`. Product layout is in `design.md`.
