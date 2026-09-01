"""Dependency-free metrics and tracing primitives."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock


class MetricsRegistry:
    """Store counters and latency samples and export Prometheus text format."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counters: defaultdict[str, float] = defaultdict(float)
        self._samples: defaultdict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._samples[name].append(value)

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, (time.perf_counter() - started) * 1000)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, value in sorted(self._counters.items()):
                lines.extend((f"# TYPE {name} counter", f"{name} {value}"))
            for name, samples in sorted(self._samples.items()):
                lines.append(f"# TYPE {name} summary")
                lines.append(f"{name}_count {len(samples)}")
                lines.append(f"{name}_sum {sum(samples)}")
        return "\n".join(lines) + "\n"

    def clear(self) -> None:
        with self._lock:
            self._counters.clear()
            self._samples.clear()


metrics = MetricsRegistry()
