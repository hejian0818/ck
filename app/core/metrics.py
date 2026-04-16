"""In-memory application metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Collect simple in-memory counters and histograms."""

    def __init__(self) -> None:
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._histograms: defaultdict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1) -> None:
        """Increment a counter metric."""

        self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        """Record a histogram observation."""

        self._histograms[name].append(value)

    def get_counter(self, name: str) -> int:
        """Return the current counter value."""

        return self._counters[name]

    def get_histogram_stats(self, name: str) -> dict[str, float | int]:
        """Return descriptive statistics for a histogram metric."""

        values = sorted(self._histograms[name])
        if not values:
            return {
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "p50": 0.0,
                "p99": 0.0,
                "count": 0,
            }

        count = len(values)
        return {
            "min": values[0],
            "max": values[-1],
            "avg": sum(values) / count,
            "p50": _percentile(values, 0.50),
            "p99": _percentile(values, 0.99),
            "count": count,
        }

    def snapshot(self) -> dict[str, Any]:
        """Return all collected metrics."""

        return {
            "counters": dict(self._counters),
            "histograms": {
                name: self.get_histogram_stats(name)
                for name in sorted(self._histograms)
            },
        }

    def prometheus_text(self) -> str:
        """Return metrics in a Prometheus-compatible text exposition format."""

        lines: list[str] = []
        for name in sorted(self._counters):
            metric_name = _prometheus_name(name)
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {self._counters[name]}")

        for name in sorted(self._histograms):
            stats = self.get_histogram_stats(name)
            metric_name = _prometheus_name(name)
            lines.append(f"# TYPE {metric_name} summary")
            lines.append(f'{metric_name}_count {stats["count"]}')
            lines.append(f'{metric_name}_sum {sum(self._histograms[name])}')
            lines.append(f'{metric_name}{{quantile="0.5"}} {stats["p50"]}')
            lines.append(f'{metric_name}{{quantile="0.99"}} {stats["p99"]}')
        return "\n".join(lines) + ("\n" if lines else "")

    def reset(self) -> None:
        """Clear all metrics."""

        self._counters.clear()
        self._histograms.clear()


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int(round((len(values) - 1) * quantile))))
    return values[index]


def _prometheus_name(name: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in name)


metrics = MetricsCollector()
