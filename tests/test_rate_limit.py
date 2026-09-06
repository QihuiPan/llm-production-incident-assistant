import pytest

from api.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_releases_capacity_after_window() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)

    assert limiter.check("visitor", now=100).remaining == 1
    assert limiter.check("visitor", now=110).remaining == 0
    blocked = limiter.check("visitor", now=120)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 40
    assert limiter.check("visitor", now=161).allowed is True


def test_sliding_window_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="positive"):
        SlidingWindowRateLimiter(max_requests=0, window_seconds=60)
