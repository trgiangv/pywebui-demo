# -*- coding: utf-8 -*-
"""The open window of each transport, kept in the AppDomain.

The embedded interpreter outlives a button click and caches ``lib.*``, so a
module global would work too. The AppDomain keeps the window reachable if the
modules are ever reloaded.
"""

from __future__ import division, print_function

from System import AppDomain


def get(key):
    return AppDomain.CurrentDomain.GetData("revit_dashboard." + key)


def put(key, value):
    AppDomain.CurrentDomain.SetData("revit_dashboard." + key, value)
