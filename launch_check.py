"""
Check that every task file and worker brief opens with a valid Launch line.

    python launch_check.py --root <checkout>

WHAT IT CHECKS

- `CURRENT_TASK.md` at the root, and every top-level `briefs/*.md`.
- A task file passes if the first non-blank line after its opening `#` heading is
  `**Launch:** <lean|full> · <opus|sonnet|haiku> · <folder>`, or if its content is
  `CURRENT_TASK: none`. A brief passes on the Launch line alone.
- `<folder>` is any non-empty text; it is not looked up on disk, because the check
  runs on the code host, where the workstation path does not exist.
- `briefs/reports/` and anything under `_archive/` are not checked.

REPORTING

Each finding names the file and the line. Any finding fails the run. The output
ends with a summary line and a verdict line, `PRECOMMIT-VERDICT launch PASS` or
`PRECOMMIT-VERDICT launch REFUSE`, so a run that stopped early is visible by the
absence of both. A file that cannot be read is a finding, never a pass.

It uses the Python standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NAME = "launch"
VERDICT = "PRECOMMIT-VERDICT"

PROFILES = ("lean", "full")
MODELS = ("opus", "sonnet", "haiku")
NONE_LINE = "CURRENT_TASK: none"
FORMAT = "**Launch:** <lean|full> · <opus|sonnet|haiku> · <folder>"

LAUNCH_PREFIX = re.compile(r"^\*\*Launch:\*\*\s*(.*)$")


def check_launch_line(line: str) -> str | None:
    """Return what is wrong with a Launch line, or None when it is valid."""
    match = LAUNCH_PREFIX.match(line)
    if not match:
        return f"the first line after the heading is not a Launch line; expected {FORMAT}"
    parts = [part.strip() for part in match.group(1).split("·")]
    if len(parts) != 3:
        return f"Launch line has {len(parts)} part(s), expected 3 separated by ' · ': {FORMAT}"
    profile, model, folder = parts
    if profile not in PROFILES:
        return f"profile '{profile}' is not one of {'/'.join(PROFILES)}"
    if model not in MODELS:
        return f"model '{model}' is not one of {'/'.join(MODELS)}"
    if not folder.strip("`").strip():
        return "folder is empty"
    return None


def _body(text: str) -> list[tuple[int, str]]:
    """The non-blank lines as (line number, text), without the opening heading."""
    lines = [(n, l.strip()) for n, l in enumerate(text.splitlines(), start=1) if l.strip()]
    if lines and lines[0][1].startswith("# "):
        lines = lines[1:]
    return lines


def check_file(path: Path, rel: str, allow_none: bool) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"FILE   {rel}: cannot be read ({exc})"]
    body = _body(text)
    if allow_none and [l for _, l in body] == [NONE_LINE]:
        return []
    if not body:
        return [f"FILE   {rel}: empty; expected {FORMAT}"
                + (f" or '{NONE_LINE}'" if allow_none else "")]
    lineno, line = body[0]
    problem = check_launch_line(line)
    if problem:
        return [f"FILE   {rel}:{lineno}: {problem}"]
    return []


def targets(root: Path) -> list[tuple[Path, str, bool]]:
    found = []
    task = root / "CURRENT_TASK.md"
    if task.is_file():
        found.append((task, "CURRENT_TASK.md", True))
    briefs = root / "briefs"
    if briefs.is_dir():
        for path in sorted(briefs.glob("*.md")):
            found.append((path, f"briefs/{path.name}", False))
    return found


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError, TypeError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", required=True, type=Path, help="a checkout of the repository")
    args = ap.parse_args(argv)

    files = targets(args.root)
    findings = []
    for path, rel, allow_none in files:
        findings += check_file(path, rel, allow_none)
    for line in findings:
        print(line)
    print(f"{NAME}: {len(files)} file(s) checked; {len(findings)} finding(s)")
    print(f"{VERDICT} {NAME} {'REFUSE' if findings else 'PASS'}", flush=True)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
