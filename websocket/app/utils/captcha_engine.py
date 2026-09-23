"""Helpers for persisting captcha engine metadata safely."""

from __future__ import annotations


def normalize_captcha_engine(
    engine: object,
    error: str | None = None,
) -> tuple[str, str | None]:
    """Keep the database engine label bounded and preserve diagnostics.

    ``captcha_engine`` is a short ``VARCHAR`` used for filtering and display.
    Remote workers may append a full exception to the engine label (for
    example ``remote:Connection aborted...``); persisting that value can make
    MySQL reject the whole risk-log update and leave it in ``processing``.
    Store a stable engine name and return the diagnostic separately for
    ``error_message``.
    """
    normalized = str(engine).strip()
    if normalized.startswith("remote:"):
        remote_reason = normalized.split(":", 1)[1].strip()
        normalized = "remote"
        if remote_reason and not error:
            error = remote_reason

    # Keep this guard aligned with the current schema (VARCHAR(32)) so future
    # engine implementations cannot reintroduce the same persistence failure.
    if len(normalized) > 32:
        if not error:
            error = f"滑块引擎返回异常标识: {normalized}"
        normalized = normalized[:32]
    return normalized, error
