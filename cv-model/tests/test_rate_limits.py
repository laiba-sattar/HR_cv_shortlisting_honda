"""
How a rate limit is read decides whether a candidate makes the shortlist.

Two failures live here, both of which dropped real candidates:

  - Waiting too little. The provider says "try again in 19.5s"; the old code
    waited 1s, then 2s, then gave up, and the CV vanished from the ranking.
  - Reading the duration wrong. "23m25.296s" parsed as 23 *seconds* turns a
    spent daily quota into something that looks worth retrying, so a ranking
    stalls and still fails.
"""

from __future__ import annotations

import pytest

from cv_ranker.llm import QuotaExhausted, _parse_duration, _rate_limit_wait


@pytest.mark.parametrize("text, seconds", [
    ("19.5225s", 19.5225),
    ("250ms", 0.25),
    ("7.545s", 7.545),
    ("23m25.296s", 23 * 60 + 25.296),      # the one that was misread
    ("1h2m3s", 3723.0),
    ("2m", 120.0),
    ("45", 45.0),                           # bare number means seconds
])
def test_durations_parse(text, seconds):
    assert _parse_duration(text) == pytest.approx(seconds)


def test_unparseable_duration_is_none():
    assert _parse_duration("soon") is None


def test_non_rate_limit_errors_are_not_treated_as_rate_limits():
    """A 400 or a dropped connection must keep the ordinary short backoff."""
    assert _rate_limit_wait(Exception("Error code: 400 - invalid request")) is None
    assert _rate_limit_wait(Exception("Connection error.")) is None


def test_per_minute_limit_waits_the_stated_time():
    err = Exception(
        "Error code: 429 - Rate limit reached ... on tokens per minute (TPM): "
        "Limit 8000, Used 3422, Requested 7181. Please try again in 19.5225s."
    )
    wait = _rate_limit_wait(err)
    assert wait is not None
    assert 19.5 < wait < 25, "must wait roughly what the provider asked for"


def test_rate_limit_without_a_stated_delay_still_waits():
    assert _rate_limit_wait(Exception("429 Too Many Requests")) == 20.0


def test_daily_quota_is_reported_not_retried():
    """A daily quota will not clear today — say so instead of stalling."""
    err = Exception(
        "Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` on "
        "tokens per day (TPD): Limit 200000, Used 199334, Requested 3919. "
        "Please try again in 23m25.296s."
    )
    with pytest.raises(QuotaExhausted) as excinfo:
        _rate_limit_wait(err)

    message = str(excinfo.value)
    assert "Daily" in message
    assert "resets tomorrow" in message
    assert "ollama" in message.lower(), "the message should name a way forward"
