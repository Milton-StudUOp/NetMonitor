from app.services.windows_monitoring_engine import service_state_transition


def test_service_failure_is_down_on_first_failed_check():
    state, failures, successes = service_state_transition(
        current="UP",
        healthy=False,
        failures=0,
        successes=2,
        failure_threshold=3,
        recovery_threshold=2,
    )

    assert state == "DOWN"
    assert failures == 1
    assert successes == 0

