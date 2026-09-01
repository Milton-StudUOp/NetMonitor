import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from app.api.platform import create_rule
from app.models.platform import NotificationRule
from app.services.notification.dispatcher import _rule_matches
from app.schemas.platform import NotificationIntegrationInput, NotificationRuleInput
from app.services.notification.channels import (
    NotificationConfigurationError, build_notification_content, recipient_targets, validate_integration,
)


def test_email_configuration_requires_valid_transport_and_addresses():
    config = {
        "smtp_server": "smtp.example.com", "smtp_port": 587,
        "from_address": "alerts@example.com", "recipients": ["ops@example.com"],
        "tls": True, "ssl": False,
    }
    validate_integration("EMAIL", config, {})

    with pytest.raises(NotificationConfigurationError, match="either STARTTLS or implicit TLS"):
        validate_integration("EMAIL", {**config, "ssl": True}, {})

    with pytest.raises(NotificationConfigurationError, match="valid email"):
        validate_integration("EMAIL", {**config, "recipients": ["invalid"]}, {})


def test_provider_configuration_reports_missing_fields():
    with pytest.raises(NotificationConfigurationError, match="bot token, at least one Chat ID"):
        validate_integration("TELEGRAM", {"chat_id": ""}, {})

    with pytest.raises(NotificationConfigurationError, match="API URL, API token, at least one recipient"):
        validate_integration("WHATSAPP", {}, {})


def test_multiple_recipient_targets_are_supported_and_deduplicated():
    assert recipient_targets("TELEGRAM", {"chat_ids": ["123", "-100456", "123"]}, ["789"]) == ["123", "-100456", "789"]
    assert recipient_targets("WHATSAPP", {"recipients": ["25884111", "25885222"]}, ["25884111"]) == ["25884111", "25885222"]
    assert recipient_targets("EMAIL", {"recipients": ["ops@example.com"]}, ["noc@example.com"]) == ["ops@example.com", "noc@example.com"]
    assert recipient_targets("TELEGRAM", {"chat_id": "legacy"}) == ["legacy"]
    assert recipient_targets("WHATSAPP", {"recipient": "legacy"}) == ["legacy"]


def test_notification_rule_normalizes_and_rejects_unsupported_values():
    rule = NotificationRuleInput(
        name="Critical devices", event_type="device_down", severity="critical",
        channels=["email", "EMAIL"], recipients=[" ops@example.com ", "ops@example.com"],
    )
    assert rule.event_type == "DEVICE_DOWN"
    assert rule.channels == ["EMAIL"]
    assert rule.recipients == ["ops@example.com"]

    with pytest.raises(ValidationError):
        NotificationRuleInput(name="Invalid", event_type="UNKNOWN", severity="CRITICAL", channels=["EMAIL"])


def test_integration_schema_rejects_cross_provider_fields():
    with pytest.raises(ValidationError, match="unsupported fields"):
        NotificationIntegrationInput(
            provider="TELEGRAM", name="Telegram", config={"smtp_server": "wrong"}, secrets={}
        )


def test_professional_notification_content_contains_incident_context():
    content = build_notification_content(
        "Core router unavailable",
        "The device did not respond to ICMP probes.",
        "CRITICAL",
        {
            "alert_id": 42, "event_type": "DEVICE_DOWN", "target": "Core Router (10.0.0.1)",
            "root_cause": "No ICMP response", "occurred_at": "2026-09-01T19:30:00+00:00",
        },
    )
    assert "[ACTIVE] [Critical]" in content["subject"]
    assert "NM-000042" in content["plain"]
    assert "Core Router (10.0.0.1)" in content["plain"]
    assert "Probable cause" in content["plain"]
    assert "<!doctype html>" in content["html"]


def test_recovery_content_is_distinct_and_html_escaped():
    content = build_notification_content(
        "Router <recovered>", "Connectivity is stable again.", "WARNING",
        {"alert_id": 9, "event_type": "DEVICE_UP", "target": "Router & Gateway", "recovery": True},
    )
    assert "[RECOVERED]" in content["subject"]
    assert "✅ NETMONITOR RECOVERED" in content["plain"]
    assert "Router &lt;recovered&gt;" in content["html"]
    assert "Router &amp; Gateway" in content["html"]


def test_recovery_rules_match_without_original_incident_severity():
    explicit_recovery = SimpleNamespace(
        source=None, event_type="DEVICE_UP", severity="INFORMATION", notify_recovery=True,
    )
    original_incident = SimpleNamespace(
        source=None, event_type="DEVICE_DOWN", severity="CRITICAL", notify_recovery=True,
    )
    disabled_recovery = SimpleNamespace(
        source=None, event_type="DEVICE_UP", severity="INFORMATION", notify_recovery=False,
    )
    assert _rule_matches(explicit_recovery, "DEVICE_UP", "DEVICE_DOWN", "CRITICAL", True, "Router recovered")
    assert _rule_matches(original_incident, "DEVICE_UP", "DEVICE_DOWN", "CRITICAL", True, "Router recovered")
    assert not _rule_matches(disabled_recovery, "DEVICE_UP", "DEVICE_DOWN", "CRITICAL", True, "Router recovered")


def test_rule_creation_materializes_response_before_session_teardown():
    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class Session:
        def __init__(self):
            self.rule = None

        async def execute(self, _query):
            return EmptyResult()

        def add(self, item):
            if isinstance(item, NotificationRule):
                self.rule = item

        async def flush(self):
            self.rule.id = 7

        async def refresh(self, item):
            item.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            item.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def scenario():
        data = NotificationRuleInput(
            name="Operations", event_type="DEVICE_DOWN", severity="CRITICAL", channels=["EMAIL"]
        )
        created = await create_rule(data, Session())
        assert created.created_at is not None
        assert created.updated_at is not None
        assert created.id == 7

    asyncio.run(scenario())
