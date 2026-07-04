from __future__ import annotations

import re
import unicodedata


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "article"


def unique_slug(title: str, article_id: str, seen: set[str]) -> str:
    base = slugify(title)
    candidate = base
    if candidate in seen:
        candidate = f"{base}-{article_id}"
    seen.add(candidate)
    return candidate
