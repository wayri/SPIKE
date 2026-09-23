"""Build offline help from the actual CLI parsers and immutable error registry.

Run from the repository root; no solver execution or network access is needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parser_pages(parser, prefix, summary=""):
    yield {"command": prefix, "summary": summary or parser.description or prefix,
           "usage": parser.format_help()}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            descriptions = {item.dest: item.help for item in action._choices_actions}
            for name, child in action.choices.items():
                yield from parser_pages(child, f"{prefix} {name}", descriptions.get(name, ""))


def build():
    from python.spike_core.cli import build_parser
    from python.spikes.cli import _parser
    from python.spike_core.errors import ERROR_CATALOG

    errors = []
    for code, entry in sorted(ERROR_CATALOG.items()):
        errors.append({"code": code, "title": entry.title, "message": entry.default_message,
                       "action": entry.user_action, "recoverable": entry.recoverable,
                       "retryable": entry.retryable, "domain": entry.code.domain.value,
                       "classification": entry.code.classification.value})
    return {"errors": errors, "commands": [*parser_pages(build_parser(), "spike"),
                                            *parser_pages(_parser(), "spikes")]}


if __name__ == "__main__":
    content = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    path = ROOT / "app/src/helpReference.generated.json"
    if "--check" in sys.argv:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit("Help reference is stale. Run python scripts/generate_help_reference.py")
    else:
        path.write_text(content, encoding="utf-8")
    print(f"Help CLI/error reference {'checked' if '--check' in sys.argv else 'generated'}")
