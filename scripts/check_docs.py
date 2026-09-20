#!/usr/bin/env python3
"""Documentation integrity checks for this repository.

Replaces the manual review performed on PR #1 so the same checks run on every
change. Checks are deliberately narrow: they verify mechanical facts about the
Markdown corpus, not the correctness of any research claim.

Exit code 0 when clean, 1 when any check fails.

Usage:
    python3 scripts/check_docs.py [--root .]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Markers that indicate unfinished prose. Templates are exempt because their
# whole purpose is to carry instructions for a human to replace.
PLACEHOLDER_MARKERS = ("TODO", "TBD", "FIXME", "XXX", "<placeholder", "LOREM IPSUM")
PLACEHOLDER_EXEMPT_DIRS = ("templates",)

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache"}

# [text](target) where target is not an image and not a bare reference
LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)]+)\)")


def markdown_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".md"):
                found.append(Path(dirpath) / name)
    return sorted(found)


def check_local_links(path: Path, text: str, root: Path) -> list[str]:
    """Every relative link target must resolve to a file that exists."""
    errors: list[str] = []
    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Strip any anchor fragment; we verify the file, not the heading.
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        resolved = (path.parent / file_part).resolve()
        if not resolved.exists():
            rel = path.relative_to(root)
            errors.append(f"{rel}: broken local link -> {target}")
    return errors


def check_final_newline(path: Path, text: str, root: Path) -> list[str]:
    if text and not text.endswith("\n"):
        return [f"{path.relative_to(root)}: missing final newline"]
    return []


def check_placeholders(path: Path, text: str, root: Path) -> list[str]:
    rel = path.relative_to(root)
    if any(part in PLACEHOLDER_EXEMPT_DIRS for part in rel.parts):
        return []
    errors: list[str] = []
    upper = text.upper()
    for marker in PLACEHOLDER_MARKERS:
        if marker.upper() in upper:
            errors.append(f"{rel}: unresolved placeholder marker {marker!r}")
    return errors


def check_tabs(path: Path, text: str, root: Path) -> list[str]:
    if "\t" in text:
        return [f"{path.relative_to(root)}: contains a literal tab character"]
    return []


CHECKS = (check_local_links, check_final_newline, check_placeholders, check_tabs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = markdown_files(root)
    if not files:
        print(f"check_docs: no Markdown files found under {root}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for check in CHECKS:
            errors.extend(check(path, text, root))

    if errors:
        print(f"check_docs: {len(errors)} problem(s) in {len(files)} Markdown file(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"check_docs: {len(files)} Markdown files OK "
          f"(links, final newlines, placeholders, tabs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
