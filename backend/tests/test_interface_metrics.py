from datetime import datetime, timedelta, timezone

from app.services.interface_metrics import enrich_interface_rates, selected_interfaces


def test_interface_selection_keeps_only_configured_indexes():
    rows = [{"index": 1}, {"index": 2}]
    assert selected_interfaces(rows, [2]) == [{"index": 2}]


def test_interface_rates_require_two_samples_and_use_counter_delta():
    now = datetime.now(timezone.utc)
    first = enrich_interface_rates([{"index": 1, "bytes_received": 100, "bytes_sent": 200, "speed_bps": 1000}], [], now, None)
    assert "in_bps" not in first[0]
    second = enrich_interface_rates([{"index": 1, "bytes_received": 300, "bytes_sent": 500, "speed_bps": 1000}], first, now + timedelta(seconds=10), now)
    assert second[0]["in_bps"] == 160
    assert second[0]["out_bps"] == 240
    assert second[0]["utilization_percent"] == 40
