from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlencode

import httpx

from app.config.settings import Settings
from app.models.article import Article
from app.utils.slug import unique_slug


class ZendeskScraper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "optibot-mini-clone/1.0"},
            follow_redirects=True,
        )

    def fetch_articles(self, *, limit: int) -> list[Article]:
        articles: list[Article] = []
        seen_slugs: set[str] = set()

        for payload in self._article_payloads(limit=limit):
            title = payload.get("title") or payload.get("name") or f"article-{payload['id']}"
            html_url = payload.get("html_url") or ""
            slug = unique_slug(title, str(payload["id"]), seen_slugs)
            articles.append(
                Article(
                    id=str(payload["id"]),
                    title=title.strip(),
                    html_url=html_url,
                    body_html=payload.get("body") or "",
                    updated_at=payload.get("updated_at") or "",
                    locale=payload.get("locale") or self.settings.locale,
                    slug=slug,
                )
            )
            if len(articles) >= limit:
                break

        if len(articles) < 30:
            raise RuntimeError(f"Expected at least 30 articles, got {len(articles)}")
        return articles

    def _article_payloads(self, *, limit: int) -> Iterator[dict]:
        params = {
            "per_page": min(max(limit, 30), 100),
            "sort_by": "updated_at",
            "sort_order": "desc",
        }
        next_url = (
            f"{self.settings.base_url}/api/v2/help_center/"
            f"{self.settings.locale}/articles.json?{urlencode(params)}"
        )

        while next_url:
            response = self.client.get(next_url)
            response.raise_for_status()
            data = response.json()
            for article in data.get("articles", []):
                if not article.get("draft", False):
                    yield article
            next_url = data.get("next_page")
