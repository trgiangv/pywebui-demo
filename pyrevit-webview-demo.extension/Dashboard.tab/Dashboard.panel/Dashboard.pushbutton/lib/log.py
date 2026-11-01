# -*- coding: utf-8 -*-
from __future__ import division, print_function

import logging
import logging.handlers
import os
import sys

LOGGER_NAME = "revit_dashboard"
LOG_FILE = os.path.join(os.environ.get("TEMP", "."), "revit_dashboard.log")


class _FlushStreamHandler(logging.StreamHandler):
    def emit(self, record):
        logging.StreamHandler.emit(self, record)
        self.flush()


def get_logger():
    # type: () -> logging.Logger
    logger = logging.getLogger(LOGGER_NAME)
    library = logging.getLogger("pywebui")
    if logger.handlers and logger.handlers == library.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s %(message)s")
    handlers = [
        _FlushStreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=2000000, backupCount=1, delay=True),
    ]
    level = getattr(logging, os.environ.get("REVIT_DASHBOARD_LOG", "INFO").upper(), logging.INFO)
    for handler in handlers:
        handler.setFormatter(formatter)
    for target in (logger, library):
        for handler in list(target.handlers):
            target.removeHandler(handler)
        for handler in handlers:
            target.addHandler(handler)
        target.setLevel(level)
        target.propagate = False
    return logger
