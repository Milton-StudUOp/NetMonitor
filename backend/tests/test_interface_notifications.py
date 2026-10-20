from app.schemas.platform import NotificationRuleInput
from app.services.metric_alerts import _interface_name, _interface_state
from app.services.notification.dispatcher import _event_type


def test_interface_state_accepts_snmp_and_remote_provider_shapes():
    assert _interface_state({"oper_status": "down"}) == "DOWN"
    assert _interface_state({"status": "up"}) == "UP"
    assert _interface_state({}) == "UNKNOWN"


def test_interface_alert_notification_events_have_distinct_transitions():
    title = "Interface down: uplink0 on core-switch"
    assert _event_type(title, recovery=False) == "INTERFACE_DOWN"
    assert _event_type(title, recovery=True) == "INTERFACE_UP"
    assert _interface_name({"description": "WAN uplink"}) == "WAN uplink"


def test_interface_notification_rule_is_accepted():
    rule = NotificationRuleInput(
        name="Interface incidents",
        event_type="INTERFACE_DOWN",
        severity="CRITICAL",
        channels=["EMAIL"],
    )
    assert rule.event_type == "INTERFACE_DOWN"
