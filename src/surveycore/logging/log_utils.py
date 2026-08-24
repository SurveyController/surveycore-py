from __future__ import annotations

import logging
from typing import Any, Callable, Optional


def log_suppressed_exception(context: str, exc: Optional[BaseException] = None, *, level: int = logging.INFO) -> None:
    logging.log(level, "[Suppressed] %s%s", context, f": {exc}" if exc else "")


def log_deduped_message(key: str, message: str, *, level: int = logging.INFO) -> bool:
    del key
    logging.log(level, "%s", message)
    return True


def reset_deduped_log_message(key: str) -> None:
    del key


def register_popup_handler(handler: Optional[Callable[[str, str, str], Any]]) -> None:
    del handler


def log_popup_error(title: str, message: str, **kwargs: Any) -> bool:
    del kwargs
    logging.error("%s: %s", title, message)
    return False


def log_popup_warning(title: str, message: str, **kwargs: Any) -> bool:
    del kwargs
    logging.warning("%s: %s", title, message)
    return True


def log_popup_confirm(title: str, message: str, **kwargs: Any) -> bool:
    del title, message, kwargs
    return False


def shutdown_logging() -> None:
    return None
