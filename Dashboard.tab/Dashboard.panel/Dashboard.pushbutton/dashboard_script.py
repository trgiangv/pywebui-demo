# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import UI

# sys.path.append(os.path.join(os.environ["APPDATA"], "pyRevit", "Extensions", "pyWebUI.lib"))

from lib import config  # noqa: E402
from pywebui import embed  # noqa: E402

WEBVIEW = UI.TaskDialogResult.CommandLink1
BROWSER = UI.TaskDialogResult.CommandLink2

dialog = UI.TaskDialog("BIM Dashboard")
dialog.MainInstruction = "Open the dashboard in"
dialog.AddCommandLink(
    UI.TaskDialogCommandLinkId.CommandLink1,
    "WebView2 window",
    "Inside Revit, in its own window.",
)
dialog.AddCommandLink(
    UI.TaskDialogCommandLinkId.CommandLink2,
    "Browser",
    "Your default browser. Keep the connection window open while you work.",
)
dialog.CommonButtons = UI.TaskDialogCommonButtons.Cancel
dialog.DefaultButton = WEBVIEW

choice = dialog.Show()
if choice in (WEBVIEW, BROWSER):
    transport = "webview" if choice == WEBVIEW else "http"
    embed.start(*config.embed_paths())
    embed.run(
        "from lib.transport.{} import show_dashboard\nshow_dashboard(uiapp)".format(transport),
        uiapp=__revit__,  # pyright: ignore[reportUndefinedVariable]
    )