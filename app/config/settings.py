from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PLACEHOLDER_KEYS = {"", "...", "changeme", "change-me", "replace-me", "your-api-key"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    locale: str
    article_limit: int
    data_dir: Path
    markdown_dir: Path
    logs_dir: Path
    vector_state_path: Path
    openai_api_key: str
    openai_vector_store_id: str | None
    openai_vector_store_name: str
    upload_concurrency: int
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    request_timeout_seconds: float

    @property
    def has_real_openai_key(self) -> bool:
        return self.openai_api_key.strip().lower() not in PLACEHOLDER_KEYS

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        data_dir = Path(os.getenv("DATA_DIR", "data"))
        markdown_dir = Path(os.getenv("MARKDOWN_DIR", str(data_dir / "markdown")))
        logs_dir = Path(os.getenv("LOGS_DIR", str(data_dir / "logs")))
        vector_state_path = Path(os.getenv("VECTOR_STATE_PATH", str(data_dir / "vector_state.json")))
        openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY", "")

        return cls(
            base_url=os.getenv("ZENDESK_BASE_URL", "https://support.optisigns.com").rstrip("/"),
            locale=os.getenv("ZENDESK_LOCALE", "en-us"),
            article_limit=int(os.getenv("ARTICLE_LIMIT", "30")),
            data_dir=data_dir,
            markdown_dir=markdown_dir,
            logs_dir=logs_dir,
            vector_state_path=vector_state_path,
            openai_api_key=openai_key,
            openai_vector_store_id=os.getenv("OPENAI_VECTOR_STORE_ID") or None,
            openai_vector_store_name=os.getenv("OPENAI_VECTOR_STORE_NAME", "optibot-mini-clone"),
            upload_concurrency=max(1, int(os.getenv("UPLOAD_CONCURRENCY", "5"))),
            chunk_size_tokens=int(os.getenv("CHUNK_SIZE_TOKENS", "900")),
            chunk_overlap_tokens=int(os.getenv("CHUNK_OVERLAP_TOKENS", "120")),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        )
