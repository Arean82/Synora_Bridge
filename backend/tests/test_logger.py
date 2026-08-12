"""Regression tests for the audit/job logging services.

Covers the production crash where push jobs produced a dict payload whose
``data`` value is a *list* of records; ``log_audit`` called ``.values()`` on it
and raised ``AttributeError: 'list' object has no attribute 'values'``, so the
audit log was never written.
"""
import pytest

from apps.core.models import AuditLog
from apps.core.services.logger import log_audit


@pytest.mark.django_db
class TestLogAuditPayloadShapes:
    """log_audit must tolerate every payload shape and count records correctly."""

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"data": [{"id": 1}, {"id": 2}, {"id": 3}]}, 3),  # push-job shape (regression)
            ({"data": {"a": 1, "b": 2}}, 2),  # dict-shaped data
            ([{"a": 1}, {"a": 2}], 2),  # bare list payload
            ({"foo": "bar"}, 1),  # dict without a data key
            ("scalar-payload", 1),  # scalar payload
            (None, 1),  # empty payload
        ],
    )
    def test_record_count(self, payload, expected):
        log_audit(
            mode="PUSH",
            caller="test",
            payload=payload,
            endpoint="https://example.test",
            status="SUCCESS",
        )
        record = AuditLog.objects.latest("id")
        assert record.record_count == expected


@pytest.mark.django_db
def test_log_audit_never_raises_for_non_json_payload():
    """Payloads with non-serializable values (datetimes) must still write an
    audit row (stored as str) — never raise and never print a traceback."""
    from datetime import datetime, timezone

    payload = {"data": [{"id": 1, "seen_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}]}
    log_audit(
        mode="PULL_REST",
        caller="test",
        payload=payload,
        endpoint="https://example.test/source",
        status="SUCCESS",
    )
    record = AuditLog.objects.latest("id")
    assert record.record_count == 1
    assert isinstance(record.payload_json, str)  # fell back to str()
    assert "seen_at" in record.payload_json


@pytest.mark.django_db
def test_log_audit_writes_audit_row_for_list_data():
    """The exact production shape must persist a real AuditLog row."""
    payload = {"data": [{"name": "Acme", "id": 42}]}
    log_audit(
        mode="PUSH",
        caller="Job-1",
        payload=payload,
        endpoint="https://example.test/post",
        status="SUCCESS",
    )
    record = AuditLog.objects.latest("id")
    assert record.mode == "PUSH"
    assert record.caller == "Job-1"
    assert record.record_count == 1
    assert record.endpoint == "https://example.test/post"
    assert record.payload_json == payload
