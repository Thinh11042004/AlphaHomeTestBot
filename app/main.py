from __future__ import annotations

import argparse
import json

from app.config.settings import Settings
from app.services.cleaner import HtmlMarkdownCleaner
from app.services.logger import ScrapeLogger
from app.services.scraper import ZendeskScraper
from app.utils.files import ensure_dir, write_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Zendesk support articles to clean Markdown")
    parser.add_argument("--limit", type=int, default=None, help="Maximum articles to fetch")
    parser.add_argument("--log-json", action="store_true", help="Print final scrape summary as JSON")
    return parser


def scrape_to_markdown(settings: Settings, *, limit: int | None) -> dict:
    ensure_dir(settings.markdown_dir)
    ensure_dir(settings.logs_dir)

    scraper = ZendeskScraper(settings)
    cleaner = HtmlMarkdownCleaner(settings.base_url)

    articles = scraper.fetch_articles(limit=limit or settings.article_limit)
    for article in articles:
        markdown = cleaner.to_markdown(article)
        markdown_path = settings.markdown_dir / f"{article.slug}.md"
        write_text(markdown_path, markdown)

    return ScrapeLogger(settings.logs_dir).write_run(articles)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env()

    summary = scrape_to_markdown(settings, limit=args.limit)
    if args.log_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "Scrape complete: "
            f"articles={summary['articles_fetched']} "
            f"markdown_files={summary['markdown_files_written']} "
            f"log={summary['log_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
