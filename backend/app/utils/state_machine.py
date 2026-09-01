from typing import Dict, Tuple
from app.config import get_settings

settings = get_settings()


class StateTracker:
    """
    Prevents false positives by requiring consecutive probe results
    before transitioning state (e.g. 3 consecutive failures for DOWN, 2 for UP).
    """

    def __init__(
        self,
        failures_to_down: int = settings.FAILURES_TO_DOWN,
        successes_to_up: int = settings.SUCCESSES_TO_UP,
    ):
        self.failures_to_down = failures_to_down
        self.successes_to_up = successes_to_up
        # Key: (target_type, target_id) -> (consecutive_failures, consecutive_successes, current_state)
        self._states: Dict[Tuple[str, int], Dict] = {}

    def get_state(self, target_type: str, target_id: int) -> str:
        key = (target_type, target_id)
        if key not in self._states:
            return "UNKNOWN"
        return self._states[key]["state"]

    def update(self, target_type: str, target_id: int, is_success: bool, initial_state: str = "UNKNOWN") -> Tuple[str, bool]:
        """
        Updates the tracker with probe result.
        Returns: (new_state, state_changed_flag)
        """
        key = (target_type, target_id)
        if key not in self._states:
            self._states[key] = {
                "consecutive_failures": 0,
                "consecutive_successes": 0,
                "state": initial_state,
            }

        tracker = self._states[key]
        old_state = tracker["state"]

        if is_success:
            tracker["consecutive_successes"] += 1
            tracker["consecutive_failures"] = 0
            if tracker["consecutive_successes"] >= self.successes_to_up or old_state == "UNKNOWN":
                tracker["state"] = "UP"
        else:
            tracker["consecutive_failures"] += 1
            tracker["consecutive_successes"] = 0
            if tracker["consecutive_failures"] >= self.failures_to_down:
                tracker["state"] = "DOWN"

        new_state = tracker["state"]
        state_changed = (old_state != new_state)
        return new_state, state_changed


state_tracker = StateTracker()
