"""Tests for `session_index.py`: newest first, numbered headings normalised, other files ignored."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import session_index  # noqa: E402


def record(folder: Path, name: str, heading: str) -> None:
    (folder / name).write_text(f"# {heading}\n\nbody\n", encoding="utf-8")


def test_index_lists_records_newest_first_with_clean_titles(tmp_path):
    s = tmp_path / "sessions"
    s.mkdir()
    record(s, "2026-10-20-abc1234.md", "Session 19 · 2026-10-20 — The old one")
    record(s, "2026-10-29-def5678.md", "The new one")
    (s / "notes.txt").write_text("not a record", encoding="utf-8")
    assert session_index.main([str(tmp_path)]) == 0
    rows = [l for l in (s / "INDEX.md").read_text(encoding="utf-8").splitlines()
            if l.startswith("| 2026")]
    assert rows == ["| 2026-10-29 | [The new one](./2026-10-29-def5678.md) |",
                    "| 2026-10-20 | [The old one](./2026-10-20-abc1234.md) |"]


def test_a_pipe_in_a_heading_does_not_break_the_table(tmp_path):
    s = tmp_path / "sessions"
    s.mkdir()
    record(s, "2026-10-01-aaaa111.md", "A | B")
    session_index.main([str(tmp_path)])
    assert "A \\| B" in (s / "INDEX.md").read_text(encoding="utf-8")


def test_no_sessions_folder_is_an_error_not_an_empty_index(tmp_path):
    assert session_index.main([str(tmp_path)]) == 2
