from api.tracing import MemoryTraceRecorder


def test_trace_dashboard_aggregates_latency_cost_tokens_and_failures() -> None:
    traces = MemoryTraceRecorder()
    traces.record(
        "llm.generate",
        100,
        attributes={
            "cost_usd": 0.02,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_hit": True,
        },
    )
    traces.record("tool.search", 300, status="error")
    summary = traces.summary()
    assert summary.trace_count == 2
    assert summary.p50_latency_ms == 100
    assert summary.p95_latency_ms == 300
    assert summary.llm_cost_usd == 0.02
    assert summary.token_count == 15
    assert summary.cache_hits == 1
    assert summary.failures == 1
