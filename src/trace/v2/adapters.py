"""Text-first ingress adapters.

Adapters only normalize material into parser text.  The original ingress string
is retained as a private attachment by :class:`TraceService` before this step.
Binary PDF/file adapters belong at the connector boundary and must hand the
service extracted text plus the original object reference.
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser


class UnsupportedAdapter(ValueError):
    pass


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and tag.lower() in {"p", "br", "li", "div", "section", "article", "h1", "h2", "h3", "h4", "pre"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


def adapt_text(text: str, adapter: str) -> str:
    """Return deterministic parser text for supported text-first adapters."""

    normalized_adapter = (adapter or "text").lower()
    if normalized_adapter in {"text", "markdown", "code", "transcript", "url", "adapter_payload", "upload", "cli-text"}:
        return text
    if normalized_adapter in {"html", "text/html"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        parser.close()
        return unescape("".join(parser.parts))
    if normalized_adapter in {"pdf", "application/pdf"}:
        raise UnsupportedAdapter("PDF adapters must provide extracted text and retain the original PDF as an attachment")
    raise UnsupportedAdapter(f"unsupported Trace V2 adapter: {adapter}")


# Infrastructure adapters are imported here as named exports for deployments
# that historically imported all connector types from ``v2.adapters``.  Their
# vendor SDKs remain lazy and are not imported until an adapter is instantiated.
from .production import (  # noqa: E402  (kept below text-adapter definitions)
    InMemoryCoordinationStore,
    NatsJetStreamPublisher,
    OpenSearchLexicalIndex,
    PostgresEventStore,
    QdrantDenseIndex,
    RedisCoordinationStore,
    S3ObjectStore,
)
