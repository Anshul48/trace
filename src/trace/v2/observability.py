"""Dependency-light metrics and optional OpenTelemetry hooks."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator


class MetricsRegistry:
    """Prometheus-compatible counters/histograms without a hard dependency."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._observations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)

    @staticmethod
    def _key(name: str, labels: dict[str, Any] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted((key, str(value)) for key, value in (labels or {}).items()))

    def inc(self, name: str, value: float = 1.0, *, labels: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def observe(self, name: str, value: float, *, labels: dict[str, Any] | None = None) -> None:
        with self._lock:
            values = self._observations[self._key(name, labels)]
            values.append(float(value))
            if len(values) > 10_000:
                del values[: len(values) - 10_000]

    @contextmanager
    def timer(self, name: str, *, labels: dict[str, Any] | None = None) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - started, labels=labels)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = {f"{name}{_labels(labels)}": value for (name, labels), value in self._counters.items()}
            observations = {
                f"{name}{_labels(labels)}": {
                    "count": len(values),
                    "sum": sum(values),
                    "p95": _percentile(values, 0.95),
                }
                for (name, labels), values in self._observations.items()
            }
        return {"counters": counters, "observations": observations}

    def prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}{_labels(labels)} {value}")
            for (name, labels), values in sorted(self._observations.items()):
                lines.append(f"{name}_count{_labels(labels)} {len(values)}")
                lines.append(f"{name}_sum{_labels(labels)} {sum(values)}")
                lines.append(f"{name}_p95{_labels(labels)} {_percentile(values, 0.95)}")
        return "\n".join(lines) + ("\n" if lines else "")


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    encoded = ",".join(f'{key}="{value.replace(chr(34), chr(92) + chr(34))}"' for key, value in labels)
    return "{" + encoded + "}"


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


@contextmanager
def telemetry_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    """Use OpenTelemetry when installed, otherwise remain a no-op."""

    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return
    tracer = trace.get_tracer("trace.v2")
    with tracer.start_as_current_span(name, attributes={key: str(value) for key, value in (attributes or {}).items()}):
        yield
