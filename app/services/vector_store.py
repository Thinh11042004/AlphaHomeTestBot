from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config.settings import Settings
from openai import OpenAI


def collect_markdown_paths(markdown_dir: Path) -> list[Path]:
    if not markdown_dir.exists():
        return []
    return sorted(path for path in markdown_dir.glob("*.md") if path.is_file())


def estimate_chunks(text: str, chunk_size_tokens: int, chunk_overlap_tokens: int) -> int:
    if not text.strip():
        return 0
    estimated_tokens = max(1, math.ceil(len(text) / 4))
    step = max(1, chunk_size_tokens - chunk_overlap_tokens)
    return max(1, math.ceil(max(0, estimated_tokens - chunk_overlap_tokens) / step))


def build_chunking_strategy(chunk_size_tokens: int, chunk_overlap_tokens: int) -> dict:
    return {
        "type": "static",
        "static": {
            "max_chunk_size_tokens": chunk_size_tokens,
            "chunk_overlap_tokens": chunk_overlap_tokens,
        },
    }


class OpenAIVectorStoreUploader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def upload_markdown_files(self, markdown_paths: list[Path]) -> dict:
        vector_store_id = self.settings.openai_vector_store_id or self._create_vector_store()
        uploaded_files = self._upload_files_concurrently(markdown_paths)
        file_batch = self.client.vector_stores.file_batches.create(
            vector_store_id=vector_store_id,
            file_ids=[item["openai_file_id"] for item in uploaded_files],
            chunking_strategy=build_chunking_strategy(
                self.settings.chunk_size_tokens,
                self.settings.chunk_overlap_tokens,
            ),
        )
        file_batch = self._wait_for_file_batch(vector_store_id, file_batch.id)

        return {
            "enabled": True,
            "dry_run": False,
            "uploaded_files": len(uploaded_files),
            "estimated_chunks": estimate_total_chunks(
                markdown_paths,
                self.settings.chunk_size_tokens,
                self.settings.chunk_overlap_tokens,
            ),
            "vector_store_id": vector_store_id,
            "vector_store_file_batch_id": file_batch.id,
            "file_counts": _file_counts_to_dict(file_batch.file_counts),
            "files": uploaded_files,
            "skipped_reason": None,
        }

    def _upload_files_concurrently(self, markdown_paths: list[Path]) -> list[dict]:
        max_workers = min(self.settings.upload_concurrency, len(markdown_paths))
        uploaded_by_path: dict[Path, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(self._upload_file, path): path for path in markdown_paths}
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                uploaded_by_path[path] = future.result()
        return [uploaded_by_path[path] for path in markdown_paths]

    def _upload_file(self, path: Path) -> dict:
        with path.open("rb") as file_obj:
            openai_file = self.client.files.create(file=file_obj, purpose="assistants")
        return {
            "path": str(path),
            "openai_file_id": openai_file.id,
        }

    def _create_vector_store(self) -> str:
        vector_store = self.client.vector_stores.create(name=self.settings.openai_vector_store_name)
        return vector_store.id

    def _wait_for_file_batch(self, vector_store_id: str, file_batch_id: str):
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            file_batch = self.client.vector_stores.file_batches.retrieve(
                vector_store_id=vector_store_id,
                batch_id=file_batch_id,
            )
            status = getattr(file_batch, "status", None)
            if status == "completed":
                return file_batch
            if status in {"failed", "cancelled", "expired"}:
                raise RuntimeError(f"Vector store file batch {file_batch_id} ended with status {status}")
            time.sleep(2)
        raise TimeoutError(f"Timed out waiting for vector store file batch {file_batch_id}")


def estimate_total_chunks(markdown_paths: list[Path], chunk_size_tokens: int, chunk_overlap_tokens: int) -> int:
    return sum(
        estimate_chunks(path.read_text(encoding="utf-8"), chunk_size_tokens, chunk_overlap_tokens)
        for path in markdown_paths
    )


def build_skipped_upload_summary(settings: Settings, reason: str, *, dry_run: bool = False) -> dict:
    return {
        "enabled": False,
        "dry_run": dry_run,
        "uploaded_files": 0,
        "estimated_chunks": 0,
        "vector_store_id": settings.openai_vector_store_id,
        "vector_store_file_batch_id": None,
        "file_counts": None,
        "files": [],
        "skipped_reason": reason,
    }


def build_dry_run_summary(settings: Settings, markdown_paths: list[Path]) -> dict:
    return {
        "enabled": False,
        "dry_run": True,
        "uploaded_files": 0,
        "estimated_chunks": estimate_total_chunks(
            markdown_paths,
            settings.chunk_size_tokens,
            settings.chunk_overlap_tokens,
        ),
        "vector_store_id": settings.openai_vector_store_id,
        "vector_store_file_batch_id": None,
        "file_counts": None,
        "files": [{"path": str(path)} for path in markdown_paths],
        "skipped_reason": "Dry run: no files uploaded.",
    }


def _file_counts_to_dict(file_counts) -> dict:
    return {
        "cancelled": getattr(file_counts, "cancelled", 0),
        "completed": getattr(file_counts, "completed", 0),
        "failed": getattr(file_counts, "failed", 0),
        "in_progress": getattr(file_counts, "in_progress", 0),
        "total": getattr(file_counts, "total", 0),
    }
