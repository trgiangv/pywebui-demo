# -*- coding: utf-8 -*-
"""Plain WPF window owned by the Revit main window."""

from __future__ import division, print_function

from pyrevit import HOST_APP
from System.Windows import ResizeMode, SizeToContent, Window, WindowStartupLocation
from System.Windows.Interop import WindowInteropHelper


def create_window(title, width, height=None):
    # type: (str, int, int | None) -> Window
    """Return a centered window. Without ``height`` it sizes to its content."""
    window = Window()
    window.Title = title
    window.Width = width
    if height is None:
        window.SizeToContent = SizeToContent.Height
        window.ResizeMode = ResizeMode.NoResize
    else:
        window.Height = height
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    WindowInteropHelper(window).Owner = HOST_APP.proc_window
    return window
