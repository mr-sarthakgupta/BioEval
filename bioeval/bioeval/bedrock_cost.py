"""Track and log AWS Bedrock token usage/cost for BioEval agents."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_BEDROCK_SONNET_46_PRICING = {
    "input": 3.0 / 1_000_000,
    "output": 15.0 / 1_000_000,
    "cache_write_5m": 3.75 / 1_000_000,
    "cache_write_1h": 6.0 / 1_000_000,
    "cache_read": 0.30 / 1_000_000,
}

_DEFAULT_PRICING = _BEDROCK_SONNET_46_PRICING

_MODEL_PRICING: dict[str, dict[str, float]] = {
    "us.anthropic.claude-sonnet-4-6": _BEDROCK_SONNET_46_PRICING,
    "anthropic.claude-sonnet-4-6": _BEDROCK_SONNET_46_PRICING,
    "us.anthropic.claude-sonnet-4-5-v2": _BEDROCK_SONNET_46_PRICING,
}


def _get_pricing(model: str) -> dict[str, float]:
    for key, pricing in _MODEL_PRICING.items():
        if key in model:
            return pricing
    return _DEFAULT_PRICING


def _cache_write_price(pricing: dict[str, float]) -> float:
    ttl = os.environ.get("BEDROCK_PROMPT_CACHE_TTL", "1h").strip().lower()
    if ttl == "1h":
        return pricing.get("cache_write_1h", 6.0 / 1_000_000)
    return pricing.get("cache_write_5m", 3.75 / 1_000_000)


def compute_call_cost(usage: dict[str, Any], model: str) -> tuple[float, dict[str, int]]:
    """Return (call_cost_usd, normalized_usage) from a Bedrock Converse usage block."""
    input_tokens = int(usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("outputTokens") or 0)
    cache_read_tokens = int(usage.get("cacheReadInputTokens") or 0)
    cache_write_tokens = int(usage.get("cacheWriteInputTokens") or 0)
    normalized = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
    }
    pricing = _get_pricing(model)
    regular_input = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
    call_cost = (
        regular_input * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_read_tokens * pricing["cache_read"]
        + cache_write_tokens * _cache_write_price(pricing)
    )
    return call_cost, normalized


def resolve_log_dir() -> Path:
    for env_name in ("BIOEVAL_LOG_DIR", "BIOEVAL_SUBMIT_DIR"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return Path(raw)
    return Path("/submit")


@dataclass
class BedrockCostTracker:
    component: str
    model: str
    log_dir: Path = field(default_factory=resolve_log_dir)

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost: float = 0.0
    total_calls: int = 0
    _start_time: float = field(default_factory=time.monotonic)

    def record(self, usage: dict[str, Any]) -> float:
        call_cost, normalized = compute_call_cost(usage, self.model)
        self.total_input_tokens += normalized["input_tokens"]
        self.total_output_tokens += normalized["output_tokens"]
        self.total_cache_read_tokens += normalized["cache_read_tokens"]
        self.total_cache_write_tokens += normalized["cache_write_tokens"]
        self.total_cost += call_cost
        self.total_calls += 1

        line = (
            f"[cost] {self.component} LLM call #{self.total_calls}: "
            f"in={normalized['input_tokens']} out={normalized['output_tokens']} "
            f"cache_r={normalized['cache_read_tokens']} cache_w={normalized['cache_write_tokens']} "
            f"call=${call_cost:.4f} total=${self.total_cost:.4f}"
        )
        self._emit(line)
        return call_cost

    def summary_text(self) -> str:
        elapsed = time.monotonic() - self._start_time
        return (
            f"{'=' * 50}\n"
            f"  LLM Cost Summary ({self.component})\n"
            f"{'=' * 50}\n"
            f"  Model:                {self.model}\n"
            f"  Total API calls:      {self.total_calls}\n"
            f"  Input tokens:         {self.total_input_tokens:,}\n"
            f"  Output tokens:        {self.total_output_tokens:,}\n"
            f"  Cache read tokens:    {self.total_cache_read_tokens:,}\n"
            f"  Cache write tokens:   {self.total_cache_write_tokens:,}\n"
            f"  Total cost:           ${self.total_cost:.4f}\n"
            f"  Elapsed:              {elapsed:.1f}s\n"
            f"{'=' * 50}"
        )

    def summary_dict(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self._start_time
        return {
            "component": self.component,
            "model": self.model,
            "total_calls": self.total_calls,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "cache_read_tokens": self.total_cache_read_tokens,
            "cache_write_tokens": self.total_cache_write_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "elapsed_seconds": round(elapsed, 3),
        }

    def finalize(self) -> None:
        if self.total_calls == 0:
            return
        summary = self.summary_text()
        for line in summary.splitlines():
            self._emit(line)
        self._write_json()

    def _log_path(self) -> Path:
        safe = self.component.replace(" ", "_").replace("/", "-").lower()
        return self.log_dir / f"{safe}_bedrock_cost.log"

    def _json_path(self) -> Path:
        safe = self.component.replace(" ", "_").replace("/", "-").lower()
        return self.log_dir / f"{safe}_bedrock_cost.json"

    def _emit(self, line: str) -> None:
        print(line, file=sys.stderr, flush=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with self._log_path().open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _write_json(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._json_path().write_text(
            json.dumps(self.summary_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


_trackers: dict[str, BedrockCostTracker] = {}


def get_cost_tracker(*, component: str, model: str, log_dir: Path | None = None) -> BedrockCostTracker:
    key = f"{component}:{model}"
    if key not in _trackers:
        _trackers[key] = BedrockCostTracker(
            component=component,
            model=model,
            log_dir=log_dir or resolve_log_dir(),
        )
    return _trackers[key]


def record_bedrock_usage(
    usage: dict[str, Any],
    *,
    component: str,
    model: str,
    log_dir: Path | None = None,
) -> float:
    return get_cost_tracker(component=component, model=model, log_dir=log_dir).record(usage)


def finalize_cost_tracker(*, component: str, model: str) -> None:
    key = f"{component}:{model}"
    tracker = _trackers.get(key)
    if tracker is not None:
        tracker.finalize()

