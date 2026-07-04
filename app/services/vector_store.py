from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings
from app.utils.files import ensure_dir, read_json
from app.utils.hashing import sha256_text
from openai import NotFoundError, OpenAI


def collect_markdown_paths(markdown_dir: Path) -> list[Path]:
    if not markdown_dir.exists():
        return []
    return sorted(path for path in markdown_dir.glob("*.md") if path.is_file())


def path_key(path: Path) -> str:
    return path.as_posix()


def hash_markdown_file(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


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

    def upload_markdown_files(self, markdown_paths: list[Path], *, previous_records: dict[str, dict] | None = None) -> dict:
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
        deleted_old_files = self._delete_replaced_files(vector_store_id, previous_records or {})

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
            "deleted_old_files": deleted_old_files,
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

    def _delete_replaced_files(self, vector_store_id: str, previous_records: dict[str, dict]) -> list[dict]:
        deleted = []
        for path, record in previous_records.items():
            openai_file_id = record.get("openai_file_id")
            if not openai_file_id:
                continue
            item = {"path": path, "openai_file_id": openai_file_id, "deleted": False, "error": None}
            try:
                self.client.vector_stores.files.delete(file_id=openai_file_id, vector_store_id=vector_store_id)
                self.client.files.delete(openai_file_id)
                item["deleted"] = True
            except Exception as exc:  # Keep the new upload successful even if cleanup needs manual retry.
                item["error"] = str(exc)
            deleted.append(item)
        return deleted

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


def load_vector_state(settings: Settings, markdown_paths: list[Path]) -> dict:
    state = read_json(settings.vector_state_path, default=None)
    if state:
        return state
    return _bootstrap_state_from_latest_upload_log(settings, markdown_paths)


def bootstrap_state_from_remote_vector_store(settings: Settings, markdown_paths: list[Path]) -> dict:
    if not settings.openai_vector_store_id or not settings.has_real_openai_key:
        return {"updated_at": None, "vector_store_id": settings.openai_vector_store_id, "files": {}}

    client = OpenAI(api_key=settings.openai_api_key)
    paths_by_name = {path.name: path for path in markdown_paths}
    files = {}
    remote_file_count = 0
    missing_remote_files = []

    page = client.vector_stores.files.list(vector_store_id=settings.openai_vector_store_id, limit=100)
    while True:
        for vector_store_file in page.data:
            remote_file_count += 1
            openai_file_id = getattr(vector_store_file, "id", None)
            if not openai_file_id:
                continue
            try:
                openai_file = client.files.retrieve(openai_file_id)
            except NotFoundError:
                missing_remote_files.append(openai_file_id)
                continue
            path = paths_by_name.get(openai_file.filename)
            if not path:
                continue
            key = path_key(path)
            files[key] = {
                "path": key,
                "hash": hash_markdown_file(path),
                "openai_file_id": openai_file_id,
                "uploaded_at": None,
                "bootstrapped_from": "remote_vector_store",
            }

        has_next_page = getattr(page, "has_next_page", None)
        if not callable(has_next_page) or not has_next_page():
            break
        page = page.get_next_page()

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "vector_store_id": settings.openai_vector_store_id,
        "files": files,
        "remote_file_count": remote_file_count,
        "missing_remote_files": missing_remote_files,
    }


def classify_upload_delta(markdown_paths: list[Path], state: dict) -> dict:
    previous_files = state.get("files", {})
    current = {
        path_key(path): {
            "path": path_key(path),
            "hash": hash_markdown_file(path),
        }
        for path in markdown_paths
    }
    added = []
    updated = []
    skipped = []

    for key, record in current.items():
        previous = previous_files.get(key)
        if not previous:
            added.append(key)
        elif previous.get("hash") != record["hash"]:
            updated.append(key)
        else:
            skipped.append(key)

    deleted = sorted(key for key in previous_files if key not in current)

    return {
        "current": current,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "deleted": deleted,
        "upload_keys": added + updated,
        "previous_records": {key: previous_files[key] for key in updated if key in previous_files},
    }


def save_vector_state(settings: Settings, state: dict) -> None:
    ensure_dir(settings.vector_state_path.parent)
    settings.vector_state_path.write_text(_json_dumps(state), encoding="utf-8")


def update_vector_state_after_upload(settings: Settings, state: dict, delta: dict, upload_summary: dict) -> dict:
    now = datetime.now(UTC).isoformat()
    files = dict(state.get("files", {}))

    for key in delta["deleted"]:
        files.pop(key, None)

    for item in upload_summary.get("files", []):
        key = Path(item["path"]).as_posix()
        current = delta["current"][key]
        files[key] = {
            "path": key,
            "hash": current["hash"],
            "openai_file_id": item["openai_file_id"],
            "uploaded_at": now,
        }

    for key in delta["skipped"]:
        if key in files:
            files[key]["last_seen_at"] = now

    return {
        "updated_at": now,
        "vector_store_id": upload_summary.get("vector_store_id") or settings.openai_vector_store_id,
        "files": files,
    }


def build_no_change_upload_summary(settings: Settings, delta: dict) -> dict:
    return build_skipped_upload_summary(
        settings,
        "No added or changed Markdown files to upload.",
        delta=delta,
    )


def build_skipped_upload_summary(settings: Settings, reason: str, *, dry_run: bool = False, delta: dict | None = None) -> dict:
    delta_counts = _delta_counts(delta)
    return {
        "enabled": False,
        "dry_run": dry_run,
        "uploaded_files": 0,
        "estimated_chunks": 0,
        "vector_store_id": settings.openai_vector_store_id,
        "vector_store_file_batch_id": None,
        "file_counts": None,
        "delta_counts": delta_counts,
        "deleted_old_files": [],
        "files": [],
        "skipped_reason": reason,
    }


def build_dry_run_summary(settings: Settings, markdown_paths: list[Path], *, delta: dict | None = None) -> dict:
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
        "delta_counts": _delta_counts(delta),
        "deleted_old_files": [],
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


def _bootstrap_state_from_latest_upload_log(settings: Settings, markdown_paths: list[Path]) -> dict:
    log = read_json(settings.logs_dir / "vector_upload.json", default={})
    upload = log.get("upload", {})
    if not upload.get("enabled") or upload.get("dry_run"):
        return {"updated_at": None, "vector_store_id": settings.openai_vector_store_id, "files": {}}

    existing_paths = {path_key(path): path for path in markdown_paths}
    files = {}
    for item in upload.get("files", []):
        key = Path(item.get("path", "")).as_posix()
        openai_file_id = item.get("openai_file_id")
        path = existing_paths.get(key)
        if path and openai_file_id:
            files[key] = {
                "path": key,
                "hash": hash_markdown_file(path),
                "openai_file_id": openai_file_id,
                "uploaded_at": log.get("run_at"),
                "bootstrapped_from": str(settings.logs_dir / "vector_upload.json"),
            }

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "vector_store_id": upload.get("vector_store_id") or settings.openai_vector_store_id,
        "files": files,
    }


def _delta_counts(delta: dict | None) -> dict:
    if not delta:
        return {"added": 0, "updated": 0, "skipped": 0, "deleted": 0}
    return {
        "added": len(delta["added"]),
        "updated": len(delta["updated"]),
        "skipped": len(delta["skipped"]),
        "deleted": len(delta["deleted"]),
    }


def _json_dumps(data: dict) -> str:
    import json

    return json.dumps(data, indent=2, sort_keys=True)
