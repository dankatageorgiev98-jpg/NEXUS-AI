import logging
from pathlib import Path
import threading

LOG_FOLDER = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_FOLDER / "nexus_activity.log"
_LOGGER = logging.getLogger("nexus_activity")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_CONFIGURED = False
_CONFIGURATION_LOCK = threading.Lock()


def _configure_logger():
    global _CONFIGURED
    if _CONFIGURED:
        return

    with _CONFIGURATION_LOCK:
        if _CONFIGURED:
            return

        LOG_FOLDER.mkdir(exist_ok=True)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        _LOGGER.addHandler(file_handler)
        _LOGGER.addHandler(stream_handler)
        _CONFIGURED = True


class ActivityLogger:

    @staticmethod
    def info(message):
        _configure_logger()
        _LOGGER.info(message)

    @staticmethod
    def warning(message):
        _configure_logger()
        _LOGGER.warning(message)

    @staticmethod
    def error(message):
        _configure_logger()
        _LOGGER.error(message)