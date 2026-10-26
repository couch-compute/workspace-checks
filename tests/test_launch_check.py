"""
Tests for `launch_check.py`: the Launch line on task files and briefs.

Each rule is driven to a **finding**, not only to a pass: a check whose firing path
is never exercised could be inert without anyone knowing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import launch_check  # noqa: E402

GOOD = "**Launch:** lean · sonnet · `C:\\Users\\Chris\\Claude\\PROJECTS\\x`"


def task(tmp_path, text):
    (tmp_path / "CURRENT_TASK.md").write_text(text, encoding="utf-8")


def brief(tmp_path, name, text, sub=""):
    folder = tmp_path / "briefs" / sub
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def run(tmp_path, capsys):
    code = launch_check.main(["--root", str(tmp_path)])
    return code, capsys.readouterr().out


# --- the line --------------------------------------------------------------------

@pytest.mark.parametrize("profile", ["lean", "full"])
@pytest.mark.parametrize("model", ["opus", "sonnet", "haiku"])
def test_every_valid_profile_and_model_passes(profile, model):
    assert launch_check.check_launch_line(f"**Launch:** {profile} · {model} · here") is None


@pytest.mark.parametrize("line,fragment", [
    ("Launch: lean · sonnet · here", "not a Launch line"),
    ("**Launch:** lean - sonnet - here", "1 part"),
    ("**Launch:** lean · sonnet", "2 part"),
    ("**Launch:** lean · sonnet · here · extra", "4 part"),
    ("**Launch:** medium · sonnet · here", "profile 'medium'"),
    ("**Launch:** lean · gpt · here", "model 'gpt'"),
    ("**Launch:** lean · sonnet · ", "folder is empty"),
    ("**Launch:** lean · sonnet · ``", "folder is empty"),
])
def test_a_malformed_line_is_a_finding(line, fragment):
    assert fragment in launch_check.check_launch_line(line)


# --- task files ------------------------------------------------------------------

def test_a_task_file_with_the_line_after_its_heading_passes(tmp_path, capsys):
    task(tmp_path, f"# Title\n\n{GOOD}\n\nBody\n")
    code, out = run(tmp_path, capsys)
    assert code == 0 and "PRECOMMIT-VERDICT launch PASS" in out


def test_a_task_file_with_the_line_first_and_no_heading_passes(tmp_path, capsys):
    task(tmp_path, f"{GOOD}\nBody\n")
    assert run(tmp_path, capsys)[0] == 0


def test_a_task_file_without_the_line_is_a_finding(tmp_path, capsys):
    task(tmp_path, "# Title\n\nRead the board.\n")
    code, out = run(tmp_path, capsys)
    assert code == 1 and "CURRENT_TASK.md:3" in out and "REFUSE" in out


def test_the_line_below_other_text_is_a_finding(tmp_path, capsys):
    task(tmp_path, f"# Title\n\nSome intro.\n\n{GOOD}\n")
    assert run(tmp_path, capsys)[0] == 1


def test_an_empty_task_file_is_a_finding(tmp_path, capsys):
    task(tmp_path, "\n\n")
    code, out = run(tmp_path, capsys)
    assert code == 1 and "empty" in out


def test_none_passes_for_a_task_file(tmp_path, capsys):
    task(tmp_path, "# Task\n\nCURRENT_TASK: none\n")
    assert run(tmp_path, capsys)[0] == 0


def test_none_with_extra_content_is_a_finding(tmp_path, capsys):
    task(tmp_path, "CURRENT_TASK: none\nbut also this\n")
    assert run(tmp_path, capsys)[0] == 1


def test_none_is_not_accepted_for_a_brief(tmp_path, capsys):
    brief(tmp_path, "w1.md", "CURRENT_TASK: none\n")
    assert run(tmp_path, capsys)[0] == 1


# --- briefs ----------------------------------------------------------------------

def test_a_brief_with_the_line_passes(tmp_path, capsys):
    brief(tmp_path, "w1.md", f"# Worker\n\n{GOOD}\n")
    assert run(tmp_path, capsys)[0] == 0


def test_a_brief_without_the_line_is_a_finding_naming_it(tmp_path, capsys):
    brief(tmp_path, "w1.md", "# Worker\n\n**Id:** w1\n")
    code, out = run(tmp_path, capsys)
    assert code == 1 and "briefs/w1.md:3" in out


def test_reports_and_archive_are_not_checked(tmp_path, capsys):
    brief(tmp_path, "r.md", "no line\n", sub="reports")
    brief(tmp_path, "old.md", "no line\n", sub="_archive")
    code, out = run(tmp_path, capsys)
    assert code == 0 and "0 file(s)" in out


# --- faults and shape ------------------------------------------------------------

def test_an_unreadable_file_is_a_finding_not_a_pass(tmp_path, capsys):
    (tmp_path / "CURRENT_TASK.md").write_bytes(b"\xff\xfe\x00bad")
    code, out = run(tmp_path, capsys)
    assert code == 1 and "cannot be read" in out


def test_a_repository_with_neither_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys)
    assert code == 0 and "0 file(s)" in out


def test_findings_are_all_reported_not_just_the_first(tmp_path, capsys):
    task(tmp_path, "# T\n\nnone\n")
    brief(tmp_path, "a.md", "x\n")
    brief(tmp_path, "b.md", "y\n")
    assert run(tmp_path, capsys)[1].count("FILE ") == 3
