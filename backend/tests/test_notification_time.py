from types import SimpleNamespace

import pytest

from app.services.notification import channels


@pytest.mark.parametrize("timestamp", ["2026-09-29T12:00:00Z", "2026-09-29T12:00:00", "2026-09-29T14:00:00+02:00"])
def test_same_instant_is_localized_once_in_all_channels(monkeypatch, timestamp):
    monkeypatch.setattr(channels, "get_settings", lambda: SimpleNamespace(NOTIFICATION_TIMEZONE="Africa/Maputo"))
    for recovery in (False, True):
        content = channels.build_notification_content("Test", "Message", "CRITICAL", {"occurred_at": timestamp, "recovery": recovery})
        for key in ("plain", "html", "whatsapp"):
            assert "14:00 (UTC+02:00)" in content[key]


@pytest.mark.parametrize("timestamp,expected", [("2026-01-10T23:30:00Z", "11 Jan 2026 · 00:30 (UTC+01:00)"), ("2026-07-10T23:30:00Z", "11 Jul 2026 · 01:30 (UTC+02:00)")])
def test_dst_and_date_rollover(monkeypatch, timestamp, expected):
    monkeypatch.setattr(channels, "get_settings", lambda: SimpleNamespace(NOTIFICATION_TIMEZONE="Europe/Paris"))
    assert channels.notification_time(timestamp) == expected
