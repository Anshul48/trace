"""Deterministic, text-first atomization with source-offset preservation."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AtomDraft:
    content: str
    start: int
    end: int
    ordinal: int
    parser_location: str


_PARAGRAPH = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)
_BULLET = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def normalize_text(text: str) -> str:
    """Normalize line endings only; the resulting text is the stored evidence text."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_bullets(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Return non-bullet runs and each bullet independently, preserving offsets."""

    spans: list[tuple[int, int]] = []
    lines = list(re.finditer(r"[^\n]+(?:\n|\Z)", text[start:end]))
    nonbullet_start: int | None = None
    nonbullet_end: int | None = None
    for line in lines:
        line_start = start + line.start()
        line_end = start + line.end()
        stripped = text[line_start:line_end].strip()
        if not stripped:
            continue
        if _BULLET.match(stripped):
            if nonbullet_start is not None and nonbullet_end is not None:
                spans.append(_trimmed_span(text, nonbullet_start, nonbullet_end))
                nonbullet_start = nonbullet_end = None
            spans.append(_trimmed_span(text, line_start, line_end))
        else:
            if nonbullet_start is None:
                nonbullet_start = line_start
            nonbullet_end = line_end
    if nonbullet_start is not None and nonbullet_end is not None:
        spans.append(_trimmed_span(text, nonbullet_start, nonbullet_end))
    return [(left, right) for left, right in spans if left < right]


def _split_long(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    if end - start <= max_chars:
        return [(start, end)]
    segment = text[start:end]
    boundaries = [match.end() for match in _SENTENCE_END.finditer(segment)]
    spans: list[tuple[int, int]] = []
    cursor = 0
    while len(segment) - cursor > max_chars:
        limit = cursor + max_chars
        eligible = [point for point in boundaries if cursor < point <= limit]
        cut = eligible[-1] if eligible else limit
        left, right = _trimmed_span(text, start + cursor, start + cut)
        if left < right:
            spans.append((left, right))
        cursor = cut
        while cursor < len(segment) and segment[cursor].isspace():
            cursor += 1
    left, right = _trimmed_span(text, start + cursor, end)
    if left < right:
        spans.append((left, right))
    return spans


def atomize(text: str, *, max_chars: int = 1_200) -> list[AtomDraft]:
    """Atomize paragraphs first, bullets independently, then exceptionally long text.

    ``start`` and ``end`` point into the normalized source text held in the
    attachment, so an original context can be reconstructed without a document
    table becoming authoritative.
    """

    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    normalized = normalize_text(text)
    spans: list[tuple[int, int]] = []
    for paragraph in _PARAGRAPH.finditer(normalized):
        start, end = _trimmed_span(normalized, paragraph.start(), paragraph.end())
        if start >= end:
            continue
        for item_start, item_end in _split_bullets(normalized, start, end):
            spans.extend(_split_long(normalized, item_start, item_end, max_chars))

    return [
        AtomDraft(
            content=normalized[start:end],
            start=start,
            end=end,
            ordinal=ordinal,
            parser_location=f"char:{start}-{end}",
        )
        for ordinal, (start, end) in enumerate(spans)
    ]
