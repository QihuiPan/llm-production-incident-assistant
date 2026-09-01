"""Fail CI when a meaningful change omits the required changelog update."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

EXEMPT_PATHS = {"CHANGELOG.md"}


def changed_files(base_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def validate_changelog(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    if "## [Unreleased]" not in content:
        raise SystemExit("CHANGELOG.md must contain an Unreleased section")
    section = content.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0]
    meaningful = [
        line
        for line in section.splitlines()
        if line.startswith("- ") and "Reserved for the next change" not in line
    ]
    if not meaningful and "## [1.0.0]" not in content:
        raise SystemExit("CHANGELOG.md must describe the current release")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref")
    args = parser.parse_args()
    changelog = Path("CHANGELOG.md")
    if not changelog.exists():
        raise SystemExit("CHANGELOG.md is required")
    validate_changelog(changelog)
    if args.base_ref:
        changed = changed_files(args.base_ref)
        meaningful = changed - EXEMPT_PATHS
        if meaningful and "CHANGELOG.md" not in changed:
            raise SystemExit("Every meaningful change must update CHANGELOG.md")
    print("Changelog policy satisfied")


if __name__ == "__main__":
    main()
