from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config.settings import Settings
from app.services.assistant import AssistantRunError, OptiBotAssistantService
from app.services.cleaner import HtmlMarkdownCleaner
from app.services.logger import ScrapeLogger
from app.services.scraper import ZendeskScraper
from app.services.vector_store import (
    OpenAIVectorStoreUploader,
    bootstrap_state_from_remote_vector_store,
    build_no_change_upload_summary,
    build_dry_run_summary,
    build_skipped_upload_summary,
    classify_upload_delta,
    collect_markdown_paths,
    load_vector_state,
    save_vector_state,
    update_vector_state_after_upload,
)
from app.utils.files import ensure_dir, write_text


def print_text(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Zendesk support articles, clean Markdown, and upload to OpenAI vector store")
    parser.add_argument("--limit", type=int, default=None, help="Maximum articles to fetch")
    parser.add_argument("--skip-upload", action="store_true", help="Only scrape Markdown; do not upload to OpenAI vector store")
    parser.add_argument("--upload-only", action="store_true", help="Upload existing Markdown files without scraping Zendesk")
    parser.add_argument("--setup-assistant", action="store_true", help="Create or update the OpenAI assistant and attach the vector store")
    parser.add_argument("--ask", help="Ask the configured OptiBot assistant")
    parser.add_argument("--dry-run", action="store_true", help="Preview vector-store upload without calling OpenAI")
    parser.add_argument("--log-json", action="store_true", help="Print final pipeline summary as JSON")
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


def upload_markdown_to_vector_store(settings: Settings, *, dry_run: bool) -> dict:
    ensure_dir(settings.logs_dir)
    markdown_paths = collect_markdown_paths(settings.markdown_dir)
    state = load_vector_state(settings, markdown_paths)
    delta = classify_upload_delta(markdown_paths, state)
    upload_paths = [settings.markdown_dir / Path(key).name for key in delta["upload_keys"]]

    if (
        not dry_run
        and settings.has_real_openai_key
        and settings.openai_vector_store_id
        and not state.get("files")
        and upload_paths
    ):
        remote_state = bootstrap_state_from_remote_vector_store(settings, markdown_paths)
        if remote_state.get("files"):
            state = remote_state
            delta = classify_upload_delta(markdown_paths, state)
            upload_paths = [settings.markdown_dir / Path(key).name for key in delta["upload_keys"]]

    if not markdown_paths:
        upload_summary = build_skipped_upload_summary(settings, "No Markdown files found to upload.", dry_run=dry_run, delta=delta)
    elif dry_run:
        upload_summary = build_dry_run_summary(settings, upload_paths, delta=delta)
    elif not settings.has_real_openai_key:
        upload_summary = build_skipped_upload_summary(
            settings,
            "No non-placeholder API key found in OPENAI_API_KEY or API_KEY.",
            delta=delta,
        )
    elif not upload_paths:
        upload_summary = build_no_change_upload_summary(settings, delta)
        save_vector_state(settings, update_vector_state_after_upload(settings, state, delta, upload_summary))
    else:
        uploader = OpenAIVectorStoreUploader(settings)
        upload_summary = uploader.upload_markdown_files(upload_paths, previous_records=delta["previous_records"])
        upload_summary["delta_counts"] = {
            "added": len(delta["added"]),
            "updated": len(delta["updated"]),
            "skipped": len(delta["skipped"]),
            "deleted": len(delta["deleted"]),
        }
        save_vector_state(settings, update_vector_state_after_upload(settings, state, delta, upload_summary))

    return ScrapeLogger(settings.logs_dir).write_upload_run(upload_summary)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env()

    if args.setup_assistant:
        summary = OptiBotAssistantService(settings).setup()
        if args.log_json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print(
                "Assistant setup complete: "
                f"assistant_id={summary['assistant_id']} "
                f"model={summary['model']} "
                f"vector_store_id={summary['vector_store_id']}"
            )
            if summary["model_fallback_reason"]:
                print(summary["model_fallback_reason"])
            print(f"Playground: {summary['playground_url']}")
        return 0

    if args.ask:
        try:
            answer = OptiBotAssistantService(settings).ask(args.ask)
        except AssistantRunError as exc:
            print(f"Assistant run failed: {exc}")
            return 2
        print_text(answer)
        return 0

    if args.upload_only:
        summary = upload_markdown_to_vector_store(settings, dry_run=args.dry_run)
        if args.log_json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            upload = summary["upload"]
            print(
                "Vector upload complete: "
                f"uploaded={upload['uploaded_files']} "
                f"estimated_chunks={upload['estimated_chunks']} "
                f"vector_store_id={upload['vector_store_id']} "
                f"log={summary['log_path']}"
            )
        return 0

    summary = scrape_to_markdown(settings, limit=args.limit)
    if not args.skip_upload:
        summary["vector_upload"] = upload_markdown_to_vector_store(settings, dry_run=args.dry_run)

    if args.log_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "Scrape complete: "
            f"articles={summary['articles_fetched']} "
            f"markdown_files={summary['markdown_files_written']} "
            f"log={summary['log_path']}"
        )
        if not args.skip_upload:
            upload = summary["vector_upload"]["upload"]
            print(
                "Vector upload complete: "
                f"uploaded={upload['uploaded_files']} "
                f"estimated_chunks={upload['estimated_chunks']} "
                f"vector_store_id={upload['vector_store_id']} "
                f"log={summary['vector_upload']['log_path']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
