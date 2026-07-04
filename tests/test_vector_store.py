from __future__ import annotations

from app.services.vector_store import build_chunking_strategy, collect_markdown_paths, estimate_chunks


def test_collect_markdown_paths_returns_sorted_markdown_files(tmp_path):
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("ignore", encoding="utf-8")

    paths = collect_markdown_paths(tmp_path)

    assert [path.name for path in paths] == ["a.md", "b.md"]


def test_estimate_chunks_uses_overlap_step():
    text = "x" * 4000

    assert estimate_chunks(text, chunk_size_tokens=900, chunk_overlap_tokens=120) == 2


def test_build_chunking_strategy_uses_static_settings():
    assert build_chunking_strategy(900, 120) == {
        "type": "static",
        "static": {
            "max_chunk_size_tokens": 900,
            "chunk_overlap_tokens": 120,
        },
    }
