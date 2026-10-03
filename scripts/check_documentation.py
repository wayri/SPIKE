#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check repository Markdown for deterministic, locally verifiable defects."""

from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit


MOJIBAKE_PATTERNS = (
    (re.compile(r"\ufffd"), "Unicode replacement character"),
    (re.compile(r"Ã[\u0080-\u00bf]"), "likely double-decoded UTF-8"),
    (re.compile(r"Â[\u0080-\u00bf]"), "likely stray UTF-8 lead byte"),
    (re.compile(r"â(?:€|€™|€œ|€�|€“|€”|€¦|„|†|‡)"), "likely corrupted punctuation"),
    (re.compile(r"(?:ðŸ|ï¿½)"), "likely corrupted UTF-8"),
)

MARKDOWN_DESTINATION_START = re.compile(r"\]\(\s*", re.MULTILINE)
HTML_IMAGE = re.compile(
    r"<img\b[^>]*?\bsrc\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE | re.DOTALL,
)
ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)[ \t]*#*[ \t]*$")
SETEXT_HEADING = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
INLINE_CODE = re.compile(r"(`+)(.*?)\1")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
REMOTE_SCHEMES = {"data", "ftp", "http", "https", "mailto", "tel"}


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _parse_document(text: str) -> tuple[str, list[tuple[int, int, str]], list[str]]:
    """Return searchable text, headings, and fence errors."""
    visible_lines: list[str] = []
    headings: list[tuple[int, int, str]] = []
    errors: list[str] = []
    open_fence: tuple[str, int, int] | None = None
    previous_visible = ""

    for line_number, line in enumerate(text.splitlines(), 1):
        fence_match = FENCE.match(line)
        if open_fence is not None:
            marker, length, start_line = open_fence
            if fence_match:
                candidate = fence_match.group(1)
                remainder = fence_match.group(2)
                if candidate[0] == marker and len(candidate) >= length and not remainder.strip():
                    open_fence = None
            visible_lines.append("")
            previous_visible = ""
            continue
        if fence_match:
            candidate = fence_match.group(1)
            open_fence = (candidate[0], len(candidate), line_number)
            visible_lines.append("")
            previous_visible = ""
            continue

        heading_match = ATX_HEADING.match(line)
        if heading_match:
            headings.append((line_number, len(heading_match.group(1)), heading_match.group(2).strip()))
        else:
            setext_match = SETEXT_HEADING.match(line)
            if setext_match and previous_visible.strip():
                headings.append((line_number - 1, 1 if setext_match.group(1)[0] == "=" else 2, previous_visible.strip()))

        cleaned = INLINE_CODE.sub("", line)
        visible_lines.append(cleaned)
        previous_visible = line

    if open_fence is not None:
        errors.append(f"line {open_fence[2]}: fenced code block is not closed")
    return "\n".join(visible_lines), headings, errors


def _heading_slug(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", title)
    title = title.replace("`", "").replace("*", "")
    title = title.strip().lower().replace(" ", "-")
    return "".join(
        character
        for character in title
        if character in "-_" or unicodedata.category(character)[0] in {"L", "M", "N"}
    )


def _heading_anchors(headings: list[tuple[int, int, str]]) -> set[str]:
    counts: dict[str, int] = {}
    anchors: set[str] = set()
    for _, _, title in headings:
        base = _heading_slug(title)
        count = counts.get(base, 0)
        candidate = base if count == 0 else f"{base}-{count}"
        while candidate in anchors:
            count += 1
            candidate = f"{base}-{count}"
        counts[base] = count + 1
        anchors.add(candidate)
    return anchors


def _local_target(target: str) -> tuple[str, str] | None:
    target = html.unescape(target.strip().strip("<>"))
    if target.startswith("//"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme.lower() in REMOTE_SCHEMES or parsed.netloc:
        return None
    # Treat other URI schemes as external; a one-letter scheme is a Windows drive.
    if parsed.scheme and not (len(parsed.scheme) == 1 and parsed.path.startswith(("/", "\\"))):
        return None
    return unquote(parsed.path), unquote(parsed.fragment)


def _markdown_targets(text: str) -> list[tuple[int, str]]:
    """Extract inline Markdown destinations, including balanced parentheses."""
    targets: list[tuple[int, str]] = []
    # Looking for every `](` delimiter also finds the outer destination in a
    # linked image such as `[![badge](image.svg)](target)`.
    for match in MARKDOWN_DESTINATION_START.finditer(text):
        start = match.end()
        if start >= len(text):
            continue
        if text[start] == "<":
            end = text.find(">", start + 1)
            if end != -1:
                targets.append((_line_number(text, match.start()), text[start : end + 1]))
            continue
        depth = 0
        escaped = False
        end = start
        while end < len(text):
            character = text[end]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif character.isspace() and depth == 0:
                break
            end += 1
        if end > start:
            targets.append((_line_number(text, match.start()), text[start:end].replace("\\)", ")")))
    return targets


def check_file(path: Path, root: Path) -> list[str]:
    label = _display_path(path, root)
    try:
        raw = path.read_bytes()
    except OSError as error:
        return [f"{label}: cannot read file: {error}"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        return [f"{label}:{error.start}: file is not valid UTF-8 ({error.reason})"]
    if text.startswith("\ufeff"):
        text = text[1:]

    errors: list[str] = []
    for pattern, description in MOJIBAKE_PATTERNS:
        for match in pattern.finditer(text):
            errors.append(
                f"{label}:{_line_number(text, match.start())}: {description}: {match.group(0)!r}"
            )

    visible = HTML_COMMENT.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)
    searchable, headings, structure_errors = _parse_document(visible)
    errors.extend(f"{label}:{error}" for error in structure_errors)
    if not headings and path.name.lower() == "readme.md":
        errors.append(f"{label}: README must contain a level 1 title")
    if headings:
        first_line, first_level, _ = headings[0]
        if first_level != 1:
            errors.append(f"{label}:{first_line}: first heading must be level 1, found level {first_level}")
        for (previous_line, previous_level, _), (line, level, _) in zip(headings, headings[1:]):
            if level > previous_level + 1:
                errors.append(
                    f"{label}:{line}: heading level jumps from {previous_level} to {level} "
                    f"(after line {previous_line})"
                )

    searchable = HTML_COMMENT.sub("", searchable)
    anchors = _heading_anchors(headings)
    targets = _markdown_targets(searchable)
    for match in HTML_IMAGE.finditer(searchable):
        target = match.group("double") or match.group("single") or match.group("bare") or ""
        targets.append((_line_number(searchable, match.start()), target))

    for line_number, target in targets:
        try:
            local = _local_target(target)
        except ValueError:
            errors.append(f"{label}:{line_number}: malformed link target: {target}")
            continue
        if local is None:
            continue
        target_path, fragment = local
        if not target_path:
            if fragment and fragment not in anchors:
                errors.append(f"{label}:{line_number}: heading anchor does not exist: #{fragment}")
            continue
        candidate = (root / target_path.lstrip("/\\")) if target_path.startswith(("/", "\\")) else (path.parent / target_path)
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            errors.append(f"{label}:{line_number}: local target is outside repository root: {target_path}")
            continue
        if not candidate.exists():
            errors.append(f"{label}:{line_number}: local target does not exist: {target_path}")
            continue
        if fragment and candidate.resolve() == path.resolve() and fragment not in anchors:
            errors.append(f"{label}:{line_number}: heading anchor does not exist: #{fragment}")
    return errors


def check_documentation(root: Path, paths: list[Path] | None = None) -> list[str]:
    root = root.resolve()
    requested = paths or [Path("README.md")]
    errors: list[str] = []
    for requested_path in requested:
        path = requested_path if requested_path.is_absolute() else root / requested_path
        try:
            path.resolve().relative_to(root)
        except ValueError:
            errors.append(f"{requested_path}: path is outside repository root")
            continue
        errors.extend(check_file(path, root))
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("paths", nargs="*", type=Path, help="Markdown files (default: README.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    errors = check_documentation(args.root, args.paths)
    if errors:
        print("SPIKE documentation check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    checked = len(args.paths) if args.paths else 1
    print(f"SPIKE documentation check passed ({checked} file{'s' if checked != 1 else ''}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
