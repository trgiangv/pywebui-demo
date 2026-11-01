# -*- coding: utf-8 -*-
# IronPython: pyRevit runs startup.py in its default engine.
import os

from pyrevit import ROOT_BIN_DIR
from pyrevit.coreutils.logger import get_logger
from pywebui.runtime import HTTP_REQUIREMENTS, ensure_packages, find_python
from System.Threading import Thread, ThreadStart

CPYTHON_ENGINE = "CPY312"
EXTRA_PACKAGES = []  # more PEP 508 requirements, installed with the browser transport's

logger = get_logger(__name__)


def _ensure_packages():
    python_exe = find_python(os.path.join(ROOT_BIN_DIR, "cengines"), CPYTHON_ENGINE)
    if python_exe is None:
        logger.error("no {} engine under {}".format(CPYTHON_ENGINE, ROOT_BIN_DIR))
        return
    try:
        ok, message = ensure_packages(python_exe, list(HTTP_REQUIREMENTS) + EXTRA_PACKAGES)
    except Exception as exc:  # a background thread must not take Revit down
        logger.error("Packages: {}".format(exc))
        return
    if ok:
        logger.info("Packages: {}".format(message))
    else:
        logger.error("Packages missing: {}".format(message))


thread = Thread(ThreadStart(_ensure_packages))
thread.IsBackground = True
thread.Start()
