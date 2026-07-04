from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.article import Article
from app.utils.files import ensure_dir


class ScrapeLogger:
    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir

    def write_run(self, articles: list[Article]) -> dict:
        ensure_dir(self.logs_dir)
        log_path = self.logs_dir / "last_scrape.json"
        summary = {
            "run_at": datetime.now(UTC).isoformat(),
            "articles_fetched": len(articles),
            "markdown_files_written": len(articles),
            "articles": [
                {
                    "id": article.id,
                    "title": article.title,
                    "slug": article.slug,
                    "url": article.html_url,
                    "updated_at": article.updated_at,
                }
                for article in articles
            ],
            "log_path": str(log_path),
        }
        log_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return summary
