from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str
    locale: str
    article_limit: int
    data_dir: Path
    markdown_dir: Path
    logs_dir: Path
    request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        data_dir = Path(os.getenv("DATA_DIR", "data"))
        markdown_dir = Path(os.getenv("MARKDOWN_DIR", str(data_dir / "markdown")))
        logs_dir = Path(os.getenv("LOGS_DIR", str(data_dir / "logs")))

        return cls(
            base_url=os.getenv("ZENDESK_BASE_URL", "https://support.optisigns.com").rstrip("/"),
            locale=os.getenv("ZENDESK_LOCALE", "en-us"),
            article_limit=int(os.getenv("ARTICLE_LIMIT", "30")),
            data_dir=data_dir,
            markdown_dir=markdown_dir,
            logs_dir=logs_dir,
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        )
