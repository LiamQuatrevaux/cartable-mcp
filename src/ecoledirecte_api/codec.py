# SPDX-FileCopyrightText: 2025 Giga77
# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Decoding helpers for Ecole Directe payloads.

Ecole Directe stores most free text (homework, messages, post-its, form
questions, ...) as base64-encoded HTML.  The MCP server decodes it once so
agents receive readable text instead of opaque blobs.
"""

from __future__ import annotations

import base64
import binascii
import html
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

# Only these keys are candidates for base64 decoding.  Applying the heuristic
# to every string would corrupt identifiers that happen to look like base64.
DECODABLE_KEYS = frozenset(
    {
        "contenu",
        "content",
        "resume",
        "question",
        "enonce",
        "description",
        "message",
        "commentaire",
        "reponse",
        "texte",
    }
)

_B64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "section",
        "article",
    }
)


class _TextExtractor(HTMLParser):
    """Small, dependency-free HTML to text converter."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if tag == "li":
            self._parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(f"&#{name};")

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(value: str) -> str:
    """Convert a small HTML fragment to plain text."""
    if "<" not in value and "&" not in value:
        return value.strip()
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = html.unescape(parser.text())
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def try_b64(value: str) -> str | None:
    """Return the decoded UTF-8 text if ``value`` looks like base64."""
    candidate = value.strip()
    if len(candidate) < 8 or len(candidate) % 4 != 0:
        return None
    if not _B64_RE.match(candidate):
        return None
    try:
        raw = base64.b64decode(candidate, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text or _CONTROL_RE.search(text):
        return None
    return text


def decode_text(value: str) -> str:
    """Decode base64/HTML free text, leaving ordinary strings untouched."""
    decoded = try_b64(value)
    if decoded is not None:
        return html_to_text(decoded)
    if "<" in value and ">" in value:
        return html_to_text(value)
    return value


def decode_payload(value: Any, key: str | None = None) -> Any:
    """Recursively decode base64/HTML fields of an API payload."""
    if isinstance(value, Mapping):
        return {
            str(item_key): decode_payload(item, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [decode_payload(item) for item in value]
    if isinstance(value, str) and key in DECODABLE_KEYS:
        return decode_text(value)
    return value


def data_of(payload: Any) -> Any:
    """Return the ``data`` member of an API envelope when present."""
    if isinstance(payload, Mapping) and "data" in payload:
        return payload["data"]
    return payload


def clean(payload: Any) -> Any:
    """Unwrap an API envelope and decode its free-text fields."""
    return decode_payload(data_of(payload))
