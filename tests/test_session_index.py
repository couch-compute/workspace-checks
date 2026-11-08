"""Tests for `session_index.py`: rows generated from current-format records, older rows kept
exactly, newest first, the index's own preamble and columns kept, and --check writing nothing."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import session_index  # noqa: E402

FIVE = "| # | date | label | block | found |\n|---|---|---|---|---|\n"


def record(folder: Path, name: str, heading: str, *lines: str) -> None:
    body = "\n".join(lines)
    (folder / name).write_text(f"# {heading}\n\n{body}\n\nbody\n", encoding="utf-8")


def current(folder: Path, name: str, n: int, label: str, block: str, found: str) -> None:
    record(folder, name, f"Session {n}: {label}",
           f"**Block:** {block} · **Mode:** handed over", "", f"**Found:** {found}")


def sessions(tmp_path: Path) -> Path:
    s = tmp_path / "sessions"
    s.mkdir()
    return s


def rows(s: Path) -> list[str]:
    return [l for l in (s / "INDEX.md").read_text(encoding="utf-8").splitlines()
            if l.startswith("| ") and not l.startswith("| #") and not l.startswith("| date")]


def test_a_current_record_generates_its_row(tmp_path):
    s = sessions(tmp_path)
    current(s, "2026-11-03-abc1234.md", 28, "The Theatre reordered", "demo-build", "Legacy first reads better")
    assert session_index.main([str(tmp_path)]) == 0
    assert rows(s) == ["| 28 | 2026-11-03 | [The Theatre reordered](./2026-11-03-abc1234.md) "
                       "| demo-build | Legacy first reads better |"]


def test_a_record_missing_its_found_line_is_older_and_keeps_its_typed_row(tmp_path):
    s = sessions(tmp_path)
    record(s, "2026-11-02-def5678.md", "Session 27: S1 re-recorded", "**Block:** demo-build · x")
    typed = "| 27 | 2026-11-02 | [S1 re-recorded](2026-11-02-def5678.md) | demo-build | Typed by hand, kept |"
    (s / "INDEX.md").write_text("# Session index\n\nOwn words.\n\n" + FIVE + typed + "\n", encoding="utf-8")
    assert session_index.main([str(tmp_path), "--check"]) == 0


def test_older_rows_preamble_and_column_order_are_kept_and_new_rows_follow_them(tmp_path):
    s = sessions(tmp_path)
    record(s, "2026-09-02-later.md", "Session 5 · 2026-09-02 — later")
    current(s, "2026-10-01-aaa1111.md", 6, "Next", "model", "It | worked")
    head = "# Session index\n\nA preamble of its own.\n\n| # | date | block | label | what it found |\n|---|---|---|---|---|\n"
    old = "| 5 | 2026-09-02 |  | [later](./2026-09-02-later.md) | — the gate passes |"
    gone = "| 4 | 2026-09-01 |  | [lost](./2026-09-01-lost.md) | — no file any more |"
    (s / "INDEX.md").write_text(head + old + "\n" + gone + "\n", encoding="utf-8")
    session_index.main([str(tmp_path)])
    text = (s / "INDEX.md").read_text(encoding="utf-8")
    assert text.startswith(head)
    assert rows(s) == ["| 6 | 2026-10-01 | model | [Next](./2026-10-01-aaa1111.md) | It \\| worked |", old, gone]


def test_rows_typed_out_of_order_are_put_newest_first(tmp_path):
    s = sessions(tmp_path)
    for n, day in ((19, "29"), (20, "29"), (21, "29")):
        record(s, f"2026-10-{day}-{n:07x}.md", f"Session {n}: s{n}")
    typed = [f"| {n} | 2026-10-29 | [s{n}](2026-10-29-{n:07x}.md) | b | f{n} |" for n in (21, 19, 20)]
    (s / "INDEX.md").write_text("# Session index\n\n" + FIVE + "\n".join(typed) + "\n", encoding="utf-8")
    session_index.main([str(tmp_path)])
    assert rows(s) == [typed[0], typed[2], typed[1]]


def test_an_older_record_with_no_row_gets_one_from_its_heading(tmp_path):
    s = sessions(tmp_path)
    record(s, "2026-10-20-abc1234.md", "Session 19 · 2026-10-20 — The old one")
    record(s, "2026-10-29-def5678.md", "The new one")
    (s / "notes.txt").write_text("not a record", encoding="utf-8")
    assert session_index.main([str(tmp_path)]) == 0
    assert rows(s) == ["|  | 2026-10-29 | [The new one](./2026-10-29-def5678.md) |  |  |",
                       "| 19 | 2026-10-20 | [The old one](./2026-10-20-abc1234.md) |  |  |"]


def test_the_two_column_format_is_widened_without_losing_a_row(tmp_path):
    s = sessions(tmp_path)
    record(s, "2026-10-30-864b2c2.md", "The overhead cut")
    two = "# Session index\n\nGenerated.\n\n| date | record |\n|---|---|\n| 2026-10-30 | [The overhead cut](./2026-10-30-864b2c2.md) |\n"
    (s / "INDEX.md").write_text(two, encoding="utf-8")
    session_index.main([str(tmp_path)])
    assert rows(s) == ["|  | 2026-10-30 | [The overhead cut](./2026-10-30-864b2c2.md) |  |  |"]


def test_check_writes_nothing_and_reports_a_difference(tmp_path, capsys):
    s = sessions(tmp_path)
    current(s, "2026-11-03-abc1234.md", 1, "One", "b", "f")
    (s / "INDEX.md").write_text("# Session index\n\n" + FIVE, encoding="utf-8")
    before = (s / "INDEX.md").read_text(encoding="utf-8")
    assert session_index.main(["--check", str(tmp_path)]) == 1
    assert (s / "INDEX.md").read_text(encoding="utf-8") == before
    assert "+| 1 | 2026-11-03" in capsys.readouterr().out


def test_unrecognised_columns_are_an_error_not_a_rewrite(tmp_path):
    s = sessions(tmp_path)
    (s / "INDEX.md").write_text("# x\n\n| a | b | c |\n|---|---|---|\n", encoding="utf-8")
    assert session_index.main([str(tmp_path)]) == 2
    assert (s / "INDEX.md").read_text(encoding="utf-8").startswith("# x")


def test_a_pipe_in_a_heading_does_not_break_the_table(tmp_path):
    s = sessions(tmp_path)
    record(s, "2026-10-01-aaaa111.md", "A | B")
    session_index.main([str(tmp_path)])
    assert "A \\| B" in (s / "INDEX.md").read_text(encoding="utf-8")


def test_no_sessions_folder_is_an_error_not_an_empty_index(tmp_path):
    assert session_index.main([str(tmp_path)]) == 2


def test_check_refuses_columns_that_are_not_the_standard_order(tmp_path, capsys):
    s = sessions(tmp_path)
    head = "# Session index\n\n| # | date | block | label | what it found |\n|---|---|---|---|---|\n"
    (s / "INDEX.md").write_text(head, encoding="utf-8")
    assert session_index.main(["--check", str(tmp_path)]) == 1
    assert "the standard is" in capsys.readouterr().out
    assert (s / "INDEX.md").read_text(encoding="utf-8") == head


def test_check_passes_the_standard_columns(tmp_path):
    s = sessions(tmp_path)
    (s / "INDEX.md").write_text("# Session index\n\n" + FIVE, encoding="utf-8")
    assert session_index.main(["--check", str(tmp_path)]) == 0


def test_check_can_print_any_character_on_a_windows_console_encoding(tmp_path):
    s = sessions(tmp_path)
    current(s, "2026-11-03-abc1234.md", 1, "One", "b", "an arrow → here")
    (s / "INDEX.md").write_text("# Session index\n\n" + FIVE, encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-B", session_index.__file__, "--check", str(tmp_path)],
        capture_output=True, env=dict(os.environ, PYTHONIOENCODING="cp1252"))
    assert run.returncode == 1, run.stderr
    assert b"Traceback" not in run.stderr
