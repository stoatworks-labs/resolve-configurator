"""Name sanitisation for media-pool bins and timelines.

Ported 1:1 from nc-filedropbatch's PathSanitizer.php so the two tools produce
the same names from the same CSV. Forbidden characters are *replaced* (not
stripped) so distinct inputs never collapse into one name (e.g. "10:00" vs
"1000").
"""

from __future__ import annotations

import re

_FORBIDDEN = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
_FORBIDDEN_RE = re.compile("|".join(re.escape(c) for c in _FORBIDDEN))
_WHITESPACE_RE = re.compile(r"\s+")
_STRIP_CHARS = " .\t\n\r\0\x0b"
_MAX_LEN = 200


def sanitize_segment(value: str) -> str:
    """Make a single string safe to use as a Resolve bin/timeline name."""
    clean = _FORBIDDEN_RE.sub("-", value)
    clean = _WHITESPACE_RE.sub(" ", clean)
    clean = clean.strip(_STRIP_CHARS)
    if clean == "":
        return "untitled"
    return clean[:_MAX_LEN]
