# -*- coding: utf-8 -*-
"""Dashboard log.

Writes to a file as well as stdout. After a pyRevit button script returns,
stdout is no longer shown, and the HTTP threads and Revit external events keep
running, so the file is the only record of them.

The file is ``%TEMP%\revit_dashboard.log``. ``REVIT_DASHBOARD_LOG`` selects the
level (``DEBUG``, ``INFO``, ...) and defaults to INFO.
"""

from __future__ import division, print_function

import logging
import logging.handlers
import os
import sys

LOGGER_NAME = "revit_dashboard"  # type: str
LOG_FILE = os.path.join(os.environ.get("TEMP", "."), "revit_dashboard.log")  # type: str


class _FlushStreamHandler(logging.StreamHandler):
    def emit(self, record):
        logging.StreamHandler.emit(self, record)
        self.flush()


def get_logger():
    # type: () -> logging.Logger
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s %(message)s")
    handlers = [_FlushStreamHandler(sys.stdout)]
    try:
        handlers.append(
            logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=2000000, backupCount=1, delay=True)
        )
    except Exception:
        pass  # file not writable: stdout only
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    name = os.environ.get("REVIT_DASHBOARD_LOG", "INFO").upper()
    logger.setLevel(getattr(logging, name, logging.INFO))
    logger.propagate = False
    return logger
