# -*- coding: utf-8 -*-
from __future__ import division, print_function

from pywebui.adapter.revit import REVIT_CONTEXT
from System.Windows import ResizeMode, SizeToContent, Window, WindowStartupLocation


def create_window(title, width, height=None):
    # type: (str, int, int | None) -> Window
    window = Window()
    window.Title = title
    window.Width = width
    if height is None:
        window.SizeToContent = SizeToContent.Height
        window.ResizeMode = ResizeMode.NoResize
    else:
        window.Height = height
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    window.Owner = REVIT_CONTEXT.main_window
    return window
