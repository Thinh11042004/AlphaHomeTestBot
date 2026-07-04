from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.models.article import Article


UNRELATED_SELECTORS = [
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    ".breadcrumbs",
    ".breadcrumb",
    ".sidenav",
    ".sidebar",
    ".article-votes",
    ".article-comments",
    ".related-articles",
    ".recent-articles",
    ".share",
    ".ad",
    ".ads",
]


class HtmlMarkdownCleaner:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.base_host = urlparse(self.base_url).netloc

    def to_markdown(self, article: Article) -> str:
        soup = BeautifulSoup(article.body_html or "", "html.parser")
        for selector in UNRELATED_SELECTORS:
            for tag in soup.select(selector):
                tag.decompose()

        for tag in soup.find_all(True):
            self._strip_ui_attrs(tag)
            if tag.name == "a":
                self._clean_link(tag)
            if tag.name == "img":
                self._clean_image(tag)

        body = md(
            str(soup),
            heading_style="ATX",
            bullets="-",
            strip=["span"],
        )
        body = self._normalize_markdown(body)

        header = "\n".join(
            [
                f"# {article.title}",
                "",
                f"Article URL: {article.html_url}",
                f"Article ID: {article.id}",
                f"Updated: {article.updated_at}",
                f"Locale: {article.locale}",
                "",
                "---",
                "",
            ]
        )
        return f"{header}{body}\n"

    def _strip_ui_attrs(self, tag) -> None:
        for attr in ["class", "style", "data-list-item-id", "target", "rel"]:
            tag.attrs.pop(attr, None)

    def _clean_link(self, tag) -> None:
        href = tag.get("href")
        if not href:
            return
        parsed = urlparse(href)
        if parsed.netloc == self.base_host and parsed.path.startswith("/hc/"):
            tag["href"] = parsed.path + (f"#{parsed.fragment}" if parsed.fragment else "")

    def _clean_image(self, tag) -> None:
        if not tag.get("alt"):
            tag["alt"] = "Article image"
        for attr in ["width", "height"]:
            tag.attrs.pop(attr, None)

    def _normalize_markdown(self, text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        return text.strip()
