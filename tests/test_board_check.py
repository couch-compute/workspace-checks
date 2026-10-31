"""
Tests for `board_check.py`: at most one state label on an open issue, state kept out
of the roadmap, and the keys-sweep hook point.

Each check is driven to a **finding**, not only to a pass: a check whose firing path
is never exercised could be inert without anyone knowing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import board_check  # noqa: E402

def issue(number=1, labels=(), **extra):
    return {"number": number, "title": f"issue {number}",
            "labels": [{"name": name} for name in labels], **extra}


# --- open issues -----------------------------------------------------------------

def test_an_open_issue_with_no_state_passes():
    assert board_check.check_open([issue(7, labels=["bug"])]) == []


def test_an_open_issue_with_one_state_passes():
    assert board_check.check_open([issue(labels=["blocked"])]) == []


def test_an_open_issue_with_two_states_is_a_finding():
    found = board_check.check_open([issue(3, labels=["blocked", "needs-decision"])])
    assert len(found) == 1 and "#3" in found[0] and "2 state labels" in found[0]


@pytest.mark.parametrize("state", board_check.STATE_LABELS)
def test_every_state_in_the_table_is_accepted(state):
    assert board_check.check_open([issue(labels=[state])]) == []


# --- the roadmap -----------------------------------------------------------------

def write_roadmap(tmp_path, text):
    (tmp_path / "ROADMAP.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_a_clean_roadmap_passes(tmp_path):
    root = write_roadmap(tmp_path, "# Roadmap\n\n| block | why |\n|---|---|\n"
                                   "| ledger | what is blocked on the owner |\n")
    assert board_check.check_roadmap(root) == []


def test_a_missing_roadmap_is_a_finding(tmp_path):
    found = board_check.check_roadmap(tmp_path)
    assert len(found) == 1 and "missing" in found[0]


@pytest.mark.parametrize("text", ["see #12 for detail", "tracked in issues/12",
                                  "https://github.com/o/r/issues/12"])
def test_an_issue_number_in_the_roadmap_is_a_finding(tmp_path, text):
    found = board_check.check_roadmap(write_roadmap(tmp_path, f"line\n{text}\n"))
    assert found and all("ROADMAP.md:2" in f for f in found)
    assert any("issue number" in f for f in found)


def test_a_markdown_heading_anchor_is_not_an_issue_number(tmp_path):
    assert board_check.check_roadmap(
        write_roadmap(tmp_path, "see [x](#3-blocks) and colour &#39;\n")) == []


@pytest.mark.parametrize("text", ["| ledger | waiting-on-owner |",
                                  "status: needs-decision",
                                  "| ledger | blocked |",
                                  "state `blocked` for now"])
def test_a_state_label_in_the_roadmap_is_a_finding(tmp_path, text):
    found = board_check.check_roadmap(write_roadmap(tmp_path, text + "\n"))
    assert len(found) == 1 and "state label" in found[0]


def test_an_ordinary_word_that_is_also_a_state_is_not_a_finding_in_prose(tmp_path):
    root = write_roadmap(tmp_path, "Work that is blocked waits for its input.\n")
    assert board_check.check_roadmap(root) == []


# --- the keys-sweep hook point -----------------------------------------------------

def test_an_absent_sweep_is_noted_and_not_a_finding(tmp_path):
    findings, note = board_check.run_keys_sweep(tmp_path, here=tmp_path)
    assert findings == [] and "not present" in note


def sweep(tmp_path, body):
    here = tmp_path / "checks"
    here.mkdir()
    (here / board_check.KEYS_SWEEP).write_text(body, encoding="utf-8")
    return here


def test_a_passing_sweep_is_not_a_finding(tmp_path):
    here = sweep(tmp_path, "print('PRECOMMIT-VERDICT keys PASS')\n")
    assert board_check.run_keys_sweep(tmp_path, here=here) == ([], "keys sweep passed")


def test_a_refusing_sweep_is_a_finding(tmp_path):
    here = sweep(tmp_path, "print('unregistered key age1xyz')\n"
                           "print('PRECOMMIT-VERDICT keys REFUSE')\n")
    findings, note = board_check.run_keys_sweep(tmp_path, here=here)
    assert note == "keys sweep refused" and any("age1xyz" in f for f in findings)


def test_a_sweep_that_crashes_is_a_finding_not_a_pass(tmp_path):
    here = sweep(tmp_path, "raise SystemExit(3)\n")
    findings, note = board_check.run_keys_sweep(tmp_path, here=here)
    assert note == "keys sweep faulted" and any("without a verdict" in f
                                                for f in findings)


# --- the run ---------------------------------------------------------------------

def run(monkeypatch, tmp_path, capsys, open_issues, roadmap="# R\n"):
    write_roadmap(tmp_path, roadmap)
    monkeypatch.setattr(board_check, "fetch_open", lambda repo: open_issues)
    monkeypatch.setattr(board_check, "run_keys_sweep",
                        lambda root: ([], "keys sweep not present"))
    code = board_check.main(["--repo", "o/r", "--root", str(tmp_path)])
    return code, capsys.readouterr().out.strip().splitlines()


def test_a_clean_run_passes_with_a_summary_and_a_verdict(monkeypatch, tmp_path, capsys):
    code, out = run(monkeypatch, tmp_path, capsys,
                    [issue(labels=["blocked"])])
    assert code == 0
    assert out[-1] == "PRECOMMIT-VERDICT board PASS"
    assert "1 open issue(s)" in out[-2] and "0 finding(s)" in out[-2]


def test_any_finding_fails_the_run(monkeypatch, tmp_path, capsys):
    code, out = run(monkeypatch, tmp_path, capsys,
                    [issue(11, labels=["blocked", "needs-decision"])])
    assert code == 1
    assert out[-1] == "PRECOMMIT-VERDICT board REFUSE"
    assert any("#11" in line for line in out)


def test_a_board_that_cannot_be_read_is_a_fault_not_a_pass(monkeypatch, tmp_path, capsys):
    def boom(repo):
        raise board_check.Fault("no network")
    write_roadmap(tmp_path, "# R\n")
    monkeypatch.setattr(board_check, "fetch_open", boom)
    code = board_check.main(["--repo", "o/r", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 2 and "PRECOMMIT-VERDICT" not in out


def test_gh_output_that_is_not_a_list_is_a_fault(monkeypatch):
    class Done:
        returncode = 0
        stdout = '{"message": "rate limited"}'
        stderr = ""
    monkeypatch.setattr(board_check.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(board_check.Fault):
        board_check.gh_json(["issue", "list"])


def test_gh_failing_is_a_fault(monkeypatch):
    class Done:
        returncode = 1
        stdout = ""
        stderr = "HTTP 404"
    monkeypatch.setattr(board_check.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(board_check.Fault):
        board_check.gh_json(["issue", "list"])
