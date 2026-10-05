import os
import re


def error_details(exc):
    """Report useful diagnostics without logging request URLs or credentials."""
    detail = str(getattr(exc, "error", None) or "")
    for key, value in os.environ.items():
        if value and any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            detail = detail.replace(value, "[REDACTED]")
    detail = re.sub(r"https?://\S+", "[URL REDACTED]", detail)
    return {
        "error_type": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "detail": detail or "No safe provider details available.",
    }
