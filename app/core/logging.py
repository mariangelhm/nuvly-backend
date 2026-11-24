import copy
import logging
import re
import sys


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if re.search(r"password|token|secret|credential|authorization|cookie|reseturl", str(key), re.I)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact(item) for item in value)
    if isinstance(value, str):
        value = re.sub(r"(?i)\bBearer\s+[\w.~+/=-]+", "Bearer [REDACTED]", value)
        return re.sub(
            r"(?i)\b(password|token(?:_ws)?|access_token|refresh_token|secret|authorization|reseturl)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,}&]+)",
            r"\1=[REDACTED]",
            value,
        )
    return value


class SensitiveFormatter(logging.Formatter):
    def format(self, record):
        safe = copy.copy(record)
        safe.args = redact(safe.args)
        safe.msg = redact(safe.getMessage())
        safe.args = ()
        # Exception strings may embed inputs, credentials or provider tokens.
        if safe.exc_info:
            safe.msg = f"{safe.getMessage()} | exceptionType={safe.exc_info[0].__name__}"
            safe.args = ()
            safe.exc_info = None
        safe.exc_text = None
        return super().format(safe)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(SensitiveFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
