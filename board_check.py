"""
Check a repository's board and roadmap against the rules a script can decide.

    python board_check.py --repo <owner/name> --root <checkout>

WHAT IT CHECKS

- **An open issue carries at most one state label** from the issue-state table. An
  open issue with no state label is simply open.
- **`ROADMAP.md` carries no issue numbers and no state label names**: state lives
  on the board only, and a copy in the roadmap is a second home that goes stale.
- **The keys sweep**, when its script is present beside this one (see `KEYS_SWEEP`).

Closures are not checked: the code host's own close reason records why an issue
closed.

REPORTING

Each finding names the issue or file. Any finding fails the run. The output ends
with a summary line and then a verdict line, `PRECOMMIT-VERDICT board PASS` or
`PRECOMMIT-VERDICT board REFUSE`, so a run that stopped before its end is visible
by the absence of both.

FAULTS FAIL CLOSED

The check runs on the code host, where a fault must not read as a clean board. If
the issues cannot be listed, it prints the fault, no verdict, and exits 2.

It uses the Python standard library and the `gh` command-line tool.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NAME = "board"
VERDICT = "PRECOMMIT-VERDICT"

# The issue-state table: only states that drive an action. An open issue carries
# at most one of these.
STATE_LABELS = (
    "waiting-on-owner",
    "awaiting-deploy",
    "blocked",
    "needs-decision",
)

# ----------------------------------------------------------------------------
# HOOK POINT - KEYS SWEEP.
# The keys-versus-machines sweep is built separately. When a script of this name
# exists beside this file, it is run as
#     python <KEYS_SWEEP> --root <checkout>
# and judged by its verdict line, `PRECOMMIT-VERDICT keys PASS|REFUSE`. A
# non-zero exit with no verdict is a fault in the sweep, reported as a finding,
# because on the code host a fault must not pass. While the script is absent,
# the run says so in its summary and does not fail for it.
KEYS_SWEEP = "keys_sweep.py"
# ----------------------------------------------------------------------------

ISSUE_NUMBER = re.compile(r"(?<![\w&/])#\d+(?![\w-])|\bissues/\d+\b")

# A state label whose name is a hyphenated term is found anywhere in the roadmap.
# One whose name is an ordinary word (`blocked`) is found
# only where it is used as a label: as the whole content of an inline code span or
# of a table cell. Prose such as "what is blocked on the owner" is not a label.
_HYPHENATED = [s for s in STATE_LABELS if "-" in s]
_WORDS = [s for s in STATE_LABELS if "-" not in s]
STATE_ANYWHERE = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, _HYPHENATED))
                            + r")(?![\w-])")
STATE_AS_LABEL = re.compile(r"`(" + "|".join(map(re.escape, _WORDS)) + r")`"
                            r"|(?:^|\|)\s*(" + "|".join(map(re.escape, _WORDS))
                            + r")\s*(?=\|)")


class Fault(Exception):
    """The check could not reach a verdict."""


def _labels(issue: dict) -> list[str]:
    return [label["name"] if isinstance(label, dict) else str(label)
            for label in issue.get("labels") or []]


def _ref(issue: dict) -> str:
    return f"#{issue['number']} {issue.get('title', '')}".rstrip()


# --- the checks: pure functions over the code host's JSON -------------------

def check_open(issues: list[dict]) -> list[str]:
    findings = []
    for issue in issues:
        states = [name for name in _labels(issue) if name in STATE_LABELS]
        if len(states) > 1:
            findings.append(f"ISSUE  {_ref(issue)}: {len(states)} state labels "
                            f"({', '.join(states)}); at most one is allowed")
    return findings


def check_roadmap(root: Path) -> list[str]:
    path = root / "ROADMAP.md"
    if not path.is_file():
        return ["FILE   ROADMAP.md: missing, in a repository that carries a board"]
    findings = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"FILE   ROADMAP.md: cannot be read ({exc})"]
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in ISSUE_NUMBER.finditer(line):
            findings.append(f"FILE   ROADMAP.md:{lineno}: issue number "
                            f"'{match.group(0)}'")
        for match in STATE_ANYWHERE.finditer(line):
            findings.append(f"FILE   ROADMAP.md:{lineno}: state label "
                            f"'{match.group(1)}'")
        for match in STATE_AS_LABEL.finditer(line):
            findings.append(f"FILE   ROADMAP.md:{lineno}: state label "
                            f"'{match.group(1) or match.group(2)}'")
    return findings


def run_keys_sweep(root: Path, here: Path | None = None) -> tuple[list[str], str]:
    """The hook point for the keys sweep. Returns (findings, summary note)."""
    script = (here or Path(__file__).resolve().parent) / KEYS_SWEEP
    if not script.is_file():
        return [], "keys sweep not present"
    proc = subprocess.run([sys.executable, str(script), "--root", str(root)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    out = proc.stdout.strip().splitlines()
    last = out[-1].strip() if out else ""
    if last == f"{VERDICT} keys PASS":
        return [], "keys sweep passed"
    detail = [f"KEYS   {line}" for line in out[:-1] + proc.stderr.splitlines()
              if line.strip()]
    if last == f"{VERDICT} keys REFUSE":
        return detail or ["KEYS   the keys sweep refused"], "keys sweep refused"
    return (detail + [f"KEYS   the keys sweep ended without a verdict "
                      f"(exit {proc.returncode}); a fault, not a pass"],
            "keys sweep faulted")


# --- the code host ------------------------------------------------------------

def gh_json(args: list[str]) -> list[dict]:
    try:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as exc:
        raise Fault(f"gh could not be run: {exc}") from exc
    if proc.returncode != 0:
        raise Fault(f"gh {' '.join(args[:3])} ... exited {proc.returncode}: "
                    f"{proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise Fault(f"gh returned output that is not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise Fault("gh returned something other than a list of issues")
    return data


LIMIT = "5000"


def fetch_open(repo: str) -> list[dict]:
    return gh_json(["issue", "list", "-R", repo, "--state", "open",
                    "--limit", LIMIT, "--json", "number,title,labels"])


# --- the run --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError, TypeError):
            pass

    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--repo", required=True, help="owner/name on the code host")
    ap.add_argument("--root", required=True, type=Path,
                    help="a checkout of the repository")
    args = ap.parse_args(argv)

    try:
        open_issues = fetch_open(args.repo)
    except Fault as exc:
        print(f"FAULT  {exc}", file=sys.stderr)
        print(f"{NAME}: no verdict - the board could not be read", flush=True)
        return 2

    findings = check_open(open_issues)
    findings += check_roadmap(args.root)
    keys_findings, keys_note = run_keys_sweep(args.root)
    findings += keys_findings

    for line in findings:
        print(line)
    print(f"{NAME}: {args.repo} - {len(open_issues)} open issue(s), ROADMAP.md "
          f"checked, {keys_note}; {len(findings)} finding(s)")
    print(f"{VERDICT} {NAME} {'REFUSE' if findings else 'PASS'}", flush=True)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
