# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared limiter failures are visible without logging counter subjects."""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
from types import SimpleNamespace

import pytest

from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from services.auth import rate_limit, rate_limit_logging
from test_credential_throttle import FakeRedis


class FaultyRedis(FakeRedis):
    def __init__(self, **failures):
        super().__init__()
        self.failures = failures
        self.calls = []

    def _result(self, operation):
        self.calls.append(operation)
        failure = self.failures.get(operation)
        if failure == "error":
            try:
                raise ValueError("private-inner-canary")
            except ValueError as cause:
                raise ConnectionError("redis://private-user:private-password@private-host/0") from cause
        if failure == "invalid":
            return "private-invalid-count-canary"
        if failure == "refused":
            return False
        return None

    def get(self, key):
        result = self._result("read")
        return super().get(key) if result is None else result

    def incr(self, key):
        result = self._result("increment")
        return super().incr(key) if result is None else result

    def expire(self, key, seconds):
        result = self._result("expiry")
        return super().expire(key, seconds) if result is None else result


@pytest.fixture
def records(monkeypatch):
    rate_limit.reset_auth_rate_limits_for_tests()
    captured = []
    handler = logging.Handler()
    handler.emit = captured.append
    logger = logging.Logger("credential-limiter-backend", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(rate_limit_logging, "log", logger)
    yield captured
    rate_limit.reset_auth_rate_limits_for_tests()


def _events(records, event):
    return [record for record in records if record.msg == "CREDENTIAL_RATE_LIMIT_BACKEND_" + event]


def _assert_private(records, subjects=()):
    for record in records:
        assert not record.exc_info and not record.stack_info
        assert set(_extra_fields(record)) <= {
            "backend",
            "fallback",
            "namespace",
            "operation",
            "error_type",
            "failure_count",
            "duration_ms",
            "reason",
        }
        rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
        for private in (
            "private-inner-canary",
            "private-user",
            "private-password",
            "private-host",
            "private-invalid-count-canary",
            "darklab:auth-rate:",
            *subjects,
            *(rate_limit._safe_key(subject) for subject in subjects),
        ):
            assert private not in rendered
        assert json.loads(GELFFormatter().format(record))["_backend"] in {"redis", "process_local"}


@pytest.mark.parametrize("namespace", ["issue-ip", "failure-ip", "failure-lookup"])
@pytest.mark.parametrize(
    "operation,failure,error_type",
    [
        ("read", "error", "ConnectionError"),
        ("read", "invalid", "ValueError"),
        ("increment", "error", "ConnectionError"),
        ("increment", "invalid", "ValueError"),
        ("expiry", "error", "ConnectionError"),
        ("expiry", "refused", "RuntimeError"),
    ],
)
def test_counter_faults_emit_one_transition_and_keep_local_fallback(records, namespace, operation, failure, error_type):
    redis = FaultyRedis(**{operation: failure})
    subjects = [f"private-subject-{index}" for index in range(4)]
    for subject in subjects:
        if operation == "read":
            assert rate_limit._read(namespace, subject, 60, 100.0, redis) == 0
        else:
            assert rate_limit._increment(namespace, subject, 60, 100.0, redis) == 1
    warnings = _events(records, "DEGRADED")
    assert len(warnings) == 1 and warnings[0].levelno == logging.WARNING
    assert warnings[0].namespace == namespace and warnings[0].operation == operation
    assert warnings[0].error_type == error_type and warnings[0].fallback == "process_local"
    assert rate_limit_logging._DEGRADED[namespace].failure_count == 4
    assert not _events(records, "RECOVERED")
    selected = _events(records, "SELECTED")
    assert len(selected) == 4
    assert all(record.backend == "process_local" and record.reason == "redis_unavailable" for record in selected)
    _assert_private(records, subjects)


def test_public_limits_keep_enforcing_process_local_allowances_during_outage(records):
    redis = FaultyRedis(read="error", increment="error")
    ip, lookup = "private-client-ip", "private-lookup-id"
    for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE):
        assert rate_limit.check_credential_redemption(ip, lookup, redis_client=redis, now=100).allowed
        rate_limit.check_failed_redemption(ip, lookup, redis_client=redis, now=100)
    denied = rate_limit.check_credential_redemption(ip, lookup, redis_client=redis, now=100)
    assert not denied.allowed and denied.policy_code == "failed_credential_lookup"
    for _ in range(rate_limit.ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR):
        assert rate_limit.check_anonymous_issuance(ip, redis_client=redis, now=100).allowed
    assert not rate_limit.check_anonymous_issuance(ip, redis_client=redis, now=100).allowed
    assert {record.namespace for record in _events(records, "DEGRADED")} == {"failure-ip", "failure-lookup", "issue-ip"}
    assert len(_events(records, "DEGRADED")) == 3
    _assert_private(records, [ip, lookup])


def test_recovery_waits_for_every_failed_operation_and_reports_one_outage(records, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit_logging, "time", SimpleNamespace(monotonic=lambda: now[0]))
    redis = FaultyRedis(read="error", increment="error")
    rate_limit._read("failure-ip", "private-client", 60, 100, redis)
    rate_limit._increment("failure-ip", "private-client", 60, 100, redis)
    redis.failures = {"increment": "error"}
    rate_limit._read("failure-ip", "private-client", 60, 100, redis)
    assert not _events(records, "RECOVERED")
    # INCR succeeds next, but its required expiry still fails: no premature recovery.
    redis.failures = {"expiry": "error"}
    rate_limit._increment("failure-ip", "private-client", 60, 100, redis)
    assert not _events(records, "RECOVERED")
    redis.failures.clear()
    rate_limit._increment("failure-ip", "private-client", 60, 100, redis)
    assert not _events(records, "RECOVERED")  # No expiry call when the existing count is 2.
    now[0] += 7.5
    rate_limit._increment("failure-ip", "private-new-client", 60, 100, redis)
    recovered = _events(records, "RECOVERED")
    assert len(recovered) == 1 and recovered[0].levelno == logging.INFO
    assert recovered[0].failure_count == 3 and recovered[0].duration_ms == 7500
    assert not rate_limit_logging._DEGRADED
    rate_limit._read("failure-ip", "private-client", 60, 100, redis)
    assert len(_events(records, "RECOVERED")) == 1
    _assert_private(records, ["private-client", "private-new-client"])


def test_concurrent_failures_share_one_bounded_namespace_transition(records):
    redis = FaultyRedis(increment="error")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda index: rate_limit._increment("issue-ip", f"private-{index}", 60, 100, redis), range(100)))
    assert results == [1] * 100
    assert len(_events(records, "DEGRADED")) == 1
    assert len(rate_limit_logging._DEGRADED) == 1
    assert rate_limit_logging._DEGRADED["issue-ip"].operations == {"increment"}
    assert rate_limit_logging._DEGRADED["issue-ip"].failure_count == 100
    redis.failures.clear()
    rate_limit._increment("issue-ip", "private-recovered", 60, 100, redis)
    assert len(_events(records, "RECOVERED")) == 1
    redis.failures["increment"] = "error"
    rate_limit._increment("issue-ip", "private-next-outage", 60, 100, redis)
    assert len(_events(records, "DEGRADED")) == 2


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR])
def test_intentional_local_backend_and_disabled_limits_do_not_report_degradation(records, level):
    rate_limit_logging.log.setLevel(level)
    rate_limit.check_credential_redemption("private-client", now=100)
    rate_limit.check_anonymous_issuance("private-client", now=100)
    redis = FaultyRedis(read="error", increment="error")
    rate_limit.check_credential_redemption("private-client", redis_client=redis, enabled=False)
    rate_limit.check_anonymous_issuance("private-client", redis_client=redis, enabled=False)
    rate_limit.check_failed_redemption("private-client", redis_client=redis, enabled=False)
    assert not redis.calls and not rate_limit_logging._DEGRADED
    assert not _events(records, "DEGRADED") and not _events(records, "RECOVERED")
    assert len(_events(records, "SELECTED")) == (2 if level == logging.DEBUG else 0)
    assert all(record.reason == "redis_not_configured" for record in _events(records, "SELECTED"))
    _assert_private(records, ["private-client"])


def test_unknown_diagnostic_names_cannot_create_subject_cardinality(records):
    for index in range(100):
        rate_limit_logging.backend_failed(
            f"private-namespace-{index}", f"private-operation-{index}", ValueError("private-inner-canary")
        )
    assert set(rate_limit_logging._DEGRADED) == {"unknown"}
    assert rate_limit_logging._DEGRADED["unknown"].operations == {"unknown"}
    assert len(_events(records, "DEGRADED")) == 1
    _assert_private(records, ["private-namespace", "private-operation"])
