"""Short-lived autosave drafts for an active typing attempt.

Drafts live in the shared cache with an expiry tied to the attempt deadline. They are a
convenience for recovering after a reload and are never used for scoring. Cache failures
are tolerated: the draft is simply unavailable.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

DRAFT_MAX_CHARS = 100000


def draft_key(session_id):
    return f"tsz:typing-draft:{session_id}"


def save_draft_text(session_id, text, timeout):
    try:
        cache.set(draft_key(session_id), text, timeout=timeout)
    except Exception:
        logger.warning("Typing draft could not be saved to cache.")


def load_draft_text(session_id):
    try:
        return cache.get(draft_key(session_id)) or ""
    except Exception:
        logger.warning("Typing draft could not be read from cache.")
        return ""


def clear_draft(session_id):
    try:
        cache.delete(draft_key(session_id))
    except Exception:
        logger.warning("Typing draft could not be cleared from cache.")
