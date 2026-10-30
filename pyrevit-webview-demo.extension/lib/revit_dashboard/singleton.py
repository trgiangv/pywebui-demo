# -*- coding: utf-8 -*-
"""State that survives a clean engine.

A clean engine reloads every module on each button click, so module globals
reset. The open window is kept in the AppDomain instead.
"""

from __future__ import division, print_function

from System import AppDomain


def get(key):
    return AppDomain.CurrentDomain.GetData("revit_dashboard." + key)


def put(key, value):
    AppDomain.CurrentDomain.SetData("revit_dashboard." + key, value)
