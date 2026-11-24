import logging
from pathlib import Path
import threading
import re

LOG_FOLDER = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_FOLDER / "nexus_activity.log"
_LOGGER = logging.getLogger("nexus_activity")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_CONFIGURED = False
_CONFIGURATION_LOCK = threading.Lock()

REDACTION_MARKER = "[REDACTED]"

_SENSITIVE_FIELD_PATTERN = (
    r"(?:api[_-]?key|apikey|apiKey|access[_-]?token|"
    r"auth(?:orization)?[_-]?token|refresh[_-]?token|"
    r"secret(?:[_-]?key)?|password|passwd|private[_-]?key|"
    r"signing[_-]?key|signing[_-]?secret|seed(?:[_-]?phrase)?|"
    r"mnemonic(?:[_-]?phrase)?|recovery[_-]?phrase)"
)


def redact_sensitive_text(message):
    """Replace recognizable credentials and secret material in log text."""
    if message is None:
        return ""

    text = str(message)

    text = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^@\s]+@",
        r"\1" + REDACTION_MARKER + "@",
        text,
    )

    text = re.sub(
        r"(?i)([?&](?:api[_-]?key|apikey|access[_-]?token|"
        r"auth(?:orization)?[_-]?token|refresh[_-]?token|"
        r"secret(?:[_-]?key)?|password|passwd|private[_-]?key|"
        r"signing[_-]?key|signing[_-]?secret|seed(?:[_-]?phrase)?|"
        r"mnemonic(?:[_-]?phrase)?|recovery[_-]?phrase|token)="
        r")([^&#\s]+)",
        r"\1" + REDACTION_MARKER,
        text,
    )

    text = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*",
        "Bearer " + REDACTION_MARKER,
        text,
    )

    text = re.sub(
        r"(?i)\bAuthorization\s*:\s*[^\r\n,;]+",
        "Authorization: " + REDACTION_MARKER,
        text,
    )

    text = re.sub(
        r"(?i)\b("
        r"seed(?:[_ -]?phrase)?|mnemonic(?:[_ -]?phrase)?|"
        r"recovery[_ -]?phrase"
        r")\b(\s*[=:]\s*)([A-Za-z]+(?:[\s,]+[A-Za-z]+){11,23})",
        lambda match: (
            match.group(1)
            + match.group(2)
            + REDACTION_MARKER
        ),
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?i)"
        r"(?:-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)"
        r"[\s\S]*?"
        r"(?:-----END [A-Z0-9 ]*PRIVATE KEY-----)",
        "[REDACTED PRIVATE KEY]",
        text,
    )

    text = re.sub(
        r"(?i)\b("
        + _SENSITIVE_FIELD_PATTERN
        + r")\b(\s*[=:]\s*)([\"'])(.*?)\3",
        lambda match: (
            match.group(1)
            + match.group(2)
            + match.group(3)
            + REDACTION_MARKER
            + match.group(3)
        ),
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?i)\b("
        + _SENSITIVE_FIELD_PATTERN
        + r")\b(\s*[=:]\s*)(?![\"'])"
        r"([^\s,;\r\n}\]]+)",
        lambda match: (
            match.group(1)
            + match.group(2)
            + REDACTION_MARKER
        ),
        text,
    )

    text = re.sub(
        r"(?i)\b("
        r"seed(?:[_ -]?phrase)?|mnemonic(?:[_ -]?phrase)?|"
        r"recovery[_ -]?phrase"
        r")\b(\s*[=:]\s*)([A-Za-z]+(?:[\s,]+[A-Za-z]+){11,23})",
        lambda match: (
            match.group(1)
            + match.group(2)
            + REDACTION_MARKER
        ),
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?i)\b(private[_-]?key|signing[_-]?key|signing[_-]?secret)"
        r"\b(\s*[=:]\s*)([A-Fa-f0-9]{32,128})",
        lambda match: (
            match.group(1)
            + match.group(2)
            + REDACTION_MARKER
        ),
        text,
    )

    return text


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
        _LOGGER.info(redact_sensitive_text(message))

    @staticmethod
    def warning(message):
        _configure_logger()
        _LOGGER.warning(redact_sensitive_text(message))

    @staticmethod
    def error(message):
        _configure_logger()
        _LOGGER.error(redact_sensitive_text(message))