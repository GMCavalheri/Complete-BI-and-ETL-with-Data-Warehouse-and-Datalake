"""
Centralized logging configuration for the DW-Lake Integration project.

Every script in the project imports `get_logger(__name__)` instead of
configuring `logging` on its own. This guarantees a single consistent
format and a single log file, which makes debugging a multi-stage
pipeline (lake -> warehouse) much easier: you can grep one file and
see the full story of a run, in order, across every stage.

Usage
-----
    from src.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "pipeline.log")

# Format includes timestamp, level, module name (via %(name)s) and message.
# The module name is what lets you tell "this came from lake.ingest" vs
# "this came from warehouse.load" when reading the shared log file.
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Return a configured logger.

    Safe to call multiple times with the same name (e.g. if a module
    is imported more than once) — handlers are only attached once,
    so you won't get duplicated log lines.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

        # Console handler: what you see while a script runs.
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Rotating file handler: keeps the last 5 x 5MB log files instead
        # of one file that grows forever. Good habit for any long-running
        # or repeatedly-run pipeline.
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Prevent double-logging if the root logger also has handlers.
        logger.propagate = False

    return logger
