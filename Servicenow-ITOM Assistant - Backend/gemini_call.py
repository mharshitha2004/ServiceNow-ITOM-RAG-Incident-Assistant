"""
One place to call Gemini so a temporary overload doesn't take the app down.

Google's models sometimes answer "503 UNAVAILABLE - high demand" (or 429 /
5xx) for a few minutes at a time. When that happens this tries backup models
in order, and if none of them can answer it raises ModelBusyError - which
main.py turns into a clean HTTP 503 with a readable message instead of a
crash.

Backup models come from GEMINI_FALLBACK_MODELS in .env, a comma-separated
list tried in order. If it isn't set, gemini-3.6-flash is used. Set it to an
empty value (GEMINI_FALLBACK_MODELS=) to turn fallbacks off.
"""

import os

from google.genai import errors as genai_errors

DEFAULT_FALLBACK_MODELS = "gemini-3.6-flash"

# Temporary trouble on Google's side: worth trying another model.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ModelBusyError(Exception):
    """Every configured Gemini model was overloaded or unavailable."""


def _fallback_models() -> list[str]:
    # Read at call time (not import time) so a value in .env is picked up
    # even though .env is loaded after this module is imported.
    raw = os.getenv("GEMINI_FALLBACK_MODELS")

    if raw is None:
        raw = DEFAULT_FALLBACK_MODELS

    return [name.strip() for name in raw.split(",") if name.strip()]


def generate_content_with_fallback(client, *, model: str, contents):
    """Same as client.models.generate_content, with backup models.

    - The main model failing with a temporary error (429/5xx) moves on to the
      backups. Any other error (bad request, bad key...) is raised as-is,
      because another model wouldn't fix it.
    - A backup failing for ANY reason just moves on to the next one, so a
      mistyped backup name can never turn a busy model into a 500.
    - If nothing works, raises ModelBusyError.
    """

    backups = [name for name in _fallback_models() if name != model]
    last_error = None

    for index, name in enumerate([model, *backups]):
        try:
            return client.models.generate_content(model=name, contents=contents)

        except genai_errors.APIError as error:
            is_primary = index == 0

            if is_primary and error.code not in RETRYABLE_STATUS_CODES:
                raise

            last_error = error

            print(
                f"[Gemini] {name} failed ({error.code}); "
                + ("trying a backup model..." if index < len(backups) else "no backups left.")
            )

    raise ModelBusyError(
        "The AI model is busy right now. Please try again in a moment."
    ) from last_error