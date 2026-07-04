from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    html_url: str
    body_html: str
    updated_at: str
    locale: str
    slug: str
